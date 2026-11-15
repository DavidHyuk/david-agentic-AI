# Author: David Choi (bestshoot21@gmail.com)
"""Check bounded credential-based recovery without exposing or replacing secrets."""
import json
from pathlib import Path
import shlex
import subprocess
from types import SimpleNamespace

import pytest

import leetcode_sync as ls
from test_leetcode_sync import connection, history_data, recent_submissions_data, submission_details_data


@pytest.fixture
def login_home(tmp_path, monkeypatch):
    monkeypatch.setattr(ls, 'default_home', lambda: tmp_path)
    monkeypatch.setenv('LEETCODE_LOGIN', 'private-login@example.com')
    monkeypatch.setenv('LEETCODE_PASSWORD', 'private-password-$() #!')
    return tmp_path


def worker(monkeypatch, *, failed=False, owner='david_choi', timeout=False):
    calls, killed = [], []

    class Worker:
        pid = 123456

        def __init__(self, command, **options):
            calls.append((command, options))
            self.command, self.waits = command, 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def wait(self, **kwargs):
            self.waits += 1
            if timeout and self.waits == 1:
                raise subprocess.TimeoutExpired(self.command, kwargs['timeout'])
            if not failed and not timeout:
                path = Path(self.command[self.command.index('--session-file') + 1])
                ls.save_private_json(path, {**connection(), 'username': owner, 'session': 'fresh' * 8})
            return 1 if failed else 0

    monkeypatch.setattr(ls.subprocess, 'Popen', Worker)
    monkeypatch.setattr(ls.os, 'killpg', lambda pid, sig: killed.append((pid, sig)))
    return calls, killed


def test_private_login_file_is_literal_and_environment_takes_precedence(login_home, monkeypatch):
    path = login_home / 'leetcode-login.env'
    password = 'literal $(touch /tmp/never-execute) # space \' quote'
    path.write_text('LEETCODE_LOGIN=file-user\nLEETCODE_PASSWORD=' + shlex.quote(password) + '\n')
    path.chmod(0o600)
    monkeypatch.delenv('LEETCODE_PASSWORD')
    values = ls.login_environment(login_home)
    assert values == {'LEETCODE_LOGIN': 'private-login@example.com', 'LEETCODE_PASSWORD': password}
    monkeypatch.setenv('LEETCODE_PASSWORD', '')
    assert ls.login_environment(login_home)['LEETCODE_PASSWORD'] == ''


@pytest.mark.parametrize('value', ['unquoted private value', "'unterminated-private-secret"])
def test_invalid_login_file_does_not_echo_credentials(login_home, monkeypatch, value):
    monkeypatch.delenv('LEETCODE_PASSWORD')
    path = login_home / 'leetcode-login.env'
    path.write_text('LEETCODE_PASSWORD=' + value)
    path.chmod(0o600)
    with pytest.raises(ls.LeetCodeSyncError) as error:
        ls.login_environment(login_home)
    assert 'private' not in str(error.value)


def test_shared_login_file_is_rejected(login_home):
    path = login_home / 'leetcode-login.env'
    path.write_text('LEETCODE_PASSWORD=private-value')
    path.chmod(0o644)
    with pytest.raises(ls.LeetCodeSyncError, match='permissions to 600'):
        ls.login_environment(login_home)


def test_sync_recovers_once_then_fetches_actual_code_without_losing_saved_sources(login_home, monkeypatch):
    session, snapshot = login_home / 'session.json', login_home / 'history.json'
    ls.save_private_json(session, connection())
    ls.save_private_json(snapshot, {'username': 'david_choi', 'accepted_solutions': [
        {'slug': 'saved-problem', 'code': 'saved source', 'accepted_at': '2026-01-01'}]})
    calls, _ = worker(monkeypatch)

    def graphql(query, variables, candidate):
        if query == ls.USER_STATUS_QUERY:
            return {'userStatus': {'username': 'david_choi' if candidate['session'] == 'fresh' * 8 else None}}
        return {ls.HISTORY_QUERY: history_data(), ls.RECENT_SUBMISSIONS_QUERY: recent_submissions_data(),
                ls.SUBMISSION_DETAILS_QUERY: submission_details_data()}[query]

    monkeypatch.setattr(ls, 'graphql', graphql)
    result = ls.sync(session, snapshot, missing_only=True)
    assert result['solution_sync_status'] == 'ok'
    assert {row['slug'] for row in result['accepted_solutions']} == {'saved-problem', 'two-sum'}
    assert ls.load_connection(session)['session'] == 'fresh' * 8
    assert len(calls) == 1
    command, options = calls[0]
    assert '--environment' in command and 'private-password' not in ' '.join(command)
    assert Path(command[command.index('--snapshot-file') + 1]).parent != snapshot.parent
    assert options['stdout'] == options['stderr'] == subprocess.DEVNULL
    assert options['start_new_session'] is True
    assert not [path for path in login_home.glob('leetcode-auto-*') if path.is_dir()]
    assert 'private-password' not in snapshot.read_text() + session.read_text()
    assert json.loads((login_home / 'leetcode-auto-login.json').read_text())['status'] == 'ok'


@pytest.mark.parametrize('failure', ['password', 'wrong_owner', 'timeout'])
def test_failed_recovery_preserves_session_and_has_an_hour_cooldown(login_home, monkeypatch, failure):
    session = login_home / 'session.json'
    ls.save_private_json(session, connection())
    original = session.read_text()
    calls, killed = worker(monkeypatch, failed=failure == 'password',
                           owner='other_user' if failure == 'wrong_owner' else 'david_choi',
                           timeout=failure == 'timeout')
    with pytest.raises(ls.LeetCodeAuthError, match='complete login in the Jun workbench'):
        ls.recover_connection(session, connection())
    assert session.read_text() == original
    assert ls.recover_connection(session, connection()) is False
    assert len(calls) == 1
    assert bool(killed) is (failure == 'timeout')
    assert not [path for path in login_home.glob('leetcode-auto-*') if path.is_dir()]
    assert json.loads((login_home / 'leetcode-auto-login.json').read_text())['status'] == 'failed'


def test_recovery_verifies_the_issued_session_even_when_worker_reports_success(login_home, monkeypatch):
    session = login_home / 'session.json'
    ls.save_private_json(session, connection())
    worker(monkeypatch)
    monkeypatch.setattr(ls, 'verify_connection', lambda _: (_ for _ in ()).throw(ls.LeetCodeAuthError('rejected')))
    with pytest.raises(ls.LeetCodeAuthError):
        ls.recover_connection(session, connection())
    assert ls.load_connection(session)['session'] == connection()['session']


@pytest.mark.parametrize('stats_only', [True, False])
def test_stats_refresh_or_missing_credentials_never_attempt_login(login_home, monkeypatch, stats_only):
    monkeypatch.delenv('LEETCODE_PASSWORD')
    session, snapshot = login_home / 'session.json', login_home / 'history.json'
    ls.save_private_json(session, connection())
    monkeypatch.setattr(ls.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('Login is not enabled'))
    monkeypatch.setattr(ls, 'graphql', lambda query, *_: history_data() if query == ls.HISTORY_QUERY else {'userStatus': {}})
    result = ls.sync(session, snapshot, stats_only=stats_only)
    assert result.get('solution_sync_status') == (None if stats_only else 'reauth_required')


def test_environment_login_cli_avoids_prompts_and_password_output(login_home, monkeypatch, capsys):
    session, snapshot = login_home / 'session.json', login_home / 'history.json'
    monkeypatch.setattr(ls.getpass, 'getpass', lambda *_: pytest.fail('No terminal prompt'))
    monkeypatch.setattr(ls, 'login_automatically', lambda username, login, password: {
        'session': 'fresh' * 8, 'csrf_token': ''})
    monkeypatch.setattr(ls, 'verify_connection', lambda candidate: candidate['username'])
    assert ls.main(['--session-file', str(session), '--snapshot-file', str(snapshot),
                    'login', '--environment', '--username', 'david_choi']) == 0
    captured = capsys.readouterr()
    assert 'private-password' not in captured.out + captured.err + session.read_text()


@pytest.mark.parametrize('page_url', ['https://accounts.google.com/', 'https://leetcode.com/accounts/login/'])
def test_challenges_and_external_redirects_stop_before_entering_password(monkeypatch, page_url):
    closed = []
    field = SimpleNamespace(first=None, count=lambda: 0, inner_text=lambda **_: 'Verify you are human CAPTCHA')
    field.first = field
    page = SimpleNamespace(url=page_url, title=lambda: 'LeetCode', goto=lambda *a, **k: None, locator=lambda _: field,
                           close=lambda: closed.append(True))
    context = SimpleNamespace(cookies=lambda _: [], new_page=lambda: page)
    with pytest.raises(ls.LeetCodeSyncError, match='another site|CAPTCHA'):
        ls.login_in_context(context, 'david_choi', 'private-login', 'private-password')
    assert closed == [True]


def test_expired_browser_cookie_does_not_abort_a_fresh_form_login(monkeypatch):
    state, filled, closed = {'submitted': False}, [], []

    def verify(candidate):
        if candidate['session'] == 'expired' * 8:
            raise ls.LeetCodeAuthError('Expired')
        return candidate['username']

    monkeypatch.setattr(ls, 'verify_connection', verify)

    class Field:
        def __init__(self, selector):
            self.selector, self.first = selector, self

        def count(self):
            if 'submit' in self.selector:
                # Current LeetCode uses type="button" with id="signin_btn".
                return int('#signin_btn' in self.selector)
            return 1

        def fill(self, value, **kwargs):
            filled.append(value)

        def click(self, **kwargs):
            state['submitted'] = True

    page = SimpleNamespace(url='https://leetcode.com/accounts/login/', goto=lambda *a, **k: None,
                           locator=Field, close=lambda: closed.append(True))
    context = SimpleNamespace(new_page=lambda: page, cookies=lambda _: [
        {'name': 'LEETCODE_SESSION', 'value': ('fresh' if state['submitted'] else 'expired') * 8}])
    assert ls.login_in_context(context, 'david_choi', 'login-id', 'private-password')['session'] == 'fresh' * 8
    assert filled == ['login-id', 'private-password'] and closed == [True]


def test_automatic_browser_diagnostics_cannot_echo_passwords(login_home, monkeypatch):
    from contextlib import contextmanager
    import sys

    def launch(**kwargs):
        assert kwargs['headless'] is True
        raise RuntimeError('private-password in a browser diagnostic')

    @contextmanager
    def playwright():
        yield SimpleNamespace(chromium=SimpleNamespace(launch=launch))

    monkeypatch.setitem(sys.modules, 'playwright.sync_api', SimpleNamespace(
        Error=RuntimeError, sync_playwright=playwright))
    with pytest.raises(ls.LeetCodeSyncError) as error:
        ls.login_automatically('david_choi', 'login-id', 'private-password')
    assert 'private-password' not in str(error.value)


def test_recovery_becomes_eligible_again_after_an_hour(login_home, monkeypatch):
    session = login_home / 'session.json'
    ls.save_private_json(session, connection())
    ls.save_private_json(login_home / 'leetcode-auto-login.json', {
        'last_attempt_at': '2020-01-01T00:00:00+00:00', 'status': 'failed'})
    calls, _ = worker(monkeypatch)
    monkeypatch.setattr(ls, 'verify_connection', lambda candidate: candidate['username'])
    assert ls.recover_connection(session, connection()) is True
    assert len(calls) == 1
