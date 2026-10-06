# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Read-only LeetCode session linking and history snapshot tests."""
import json
import os
import stat

import pytest

import leetcode_sync as ls


def connection():
    return {'version': 1, 'username': 'david_choi', 'session': 'a' * 32,
            'csrf_token': '', 'linked_at': '2026-09-14T12:00:00+00:00'}


def history_data():
    return {'matchedUser': {
        'submitStatsGlobal': {'acSubmissionNum': [
            {'difficulty': 'All', 'count': 12, 'submissions': 20},
            {'difficulty': 'Easy', 'count': 5, 'submissions': 8},
            {'difficulty': 'Medium', 'count': 6, 'submissions': 10},
            {'difficulty': 'Hard', 'count': 1, 'submissions': 2},
        ]},
    }, 'recentAcSubmissionList': [
        {'title': 'Two Sum', 'titleSlug': 'two-sum', 'timestamp': '1789387200'},
    ]}


def recent_submissions_data():
    return {'recentSubmissionList': [
        {'id': '101', 'title': 'Two Sum', 'titleSlug': 'two-sum',
         'timestamp': '1789387200', 'statusDisplay': 'Accepted', 'lang': 'python3'},
        {'id': '100', 'title': 'Two Sum', 'titleSlug': 'two-sum',
         'timestamp': '1789387100', 'statusDisplay': 'Wrong Answer', 'lang': 'python3'},
    ]}


def submission_details_data():
    return {'submissionDetails': {
        'code': 'class Solution:\n    pass\n', 'timestamp': '1789387200', 'statusCode': 10,
        'lang': {'name': 'python3', 'verboseName': 'Python3'},
        'question': {'title': 'Two Sum', 'titleSlug': 'two-sum'},
    }}


def test_normalize_history_keeps_only_read_only_progress_fields():
    snapshot = ls.normalize_history(history_data(), 'david_choi')
    assert snapshot['username'] == 'david_choi'
    assert snapshot['total_solved'] == 12
    assert snapshot['solved_by_difficulty'] == {'easy': 5, 'medium': 6, 'hard': 1}
    assert snapshot['recent_accepted'] == [{
        'title': 'Two Sum', 'slug': 'two-sum', 'accepted_at': '2026-09-14T12:00:00+00:00',
    }]
    assert 'session' not in snapshot


def test_accepted_submission_candidates_keep_latest_accepted_source_per_problem():
    candidates = ls.accepted_submission_candidates(recent_submissions_data())

    assert candidates == [{
        'submission_id': 101, 'title': 'Two Sum', 'slug': 'two-sum',
        'accepted_at': '2026-09-14T12:00:00+00:00', 'language': 'python3',
    }]


def test_fetch_accepted_solutions_keeps_only_verified_accepted_code(monkeypatch):
    monkeypatch.setattr(ls, 'graphql', lambda query, *_args: (
        submission_details_data() if query == ls.SUBMISSION_DETAILS_QUERY else recent_submissions_data()
    ))

    solutions = ls.fetch_accepted_solutions(connection(), recent_submissions_data())

    assert solutions == [{
        'title': 'Two Sum', 'slug': 'two-sum',
        'accepted_at': '2026-09-14T12:00:00+00:00', 'language': 'Python3',
        'code': 'class Solution:\n    pass\n',
    }]


def test_sync_writes_an_owner_only_snapshot_without_session(tmp_path, monkeypatch):
    session_path = tmp_path / 'leetcode_session.json'
    snapshot_path = tmp_path / 'leetcode_history.json'
    ls.save_private_json(session_path, connection())
    def fake_graphql(query, *_args, **_kwargs):
        if query == ls.USER_STATUS_QUERY:
            return {'userStatus': {'username': 'david_choi'}}
        if query == ls.HISTORY_QUERY:
            return history_data()
        if query == ls.RECENT_SUBMISSIONS_QUERY:
            return recent_submissions_data()
        if query == ls.SUBMISSION_DETAILS_QUERY:
            return submission_details_data()
        pytest.fail('unexpected query')

    monkeypatch.setattr(ls, 'graphql', fake_graphql)

    snapshot = ls.sync(session_path, snapshot_path, limit=10)

    persisted = json.loads(snapshot_path.read_text())
    assert persisted == snapshot
    assert 'session' not in snapshot_path.read_text()
    assert snapshot['accepted_solutions'][0]['code'] == 'class Solution:\n    pass\n'
    assert stat.S_IMODE(snapshot_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(snapshot_path.parent.stat().st_mode) == 0o700


def test_connect_uses_environment_session_without_printing_it(tmp_path, monkeypatch, capsys):
    session_path = tmp_path / 'session.json'
    snapshot_path = tmp_path / 'history.json'
    monkeypatch.setenv('LEETCODE_SESSION', 'x' * 32)
    monkeypatch.setattr(ls, 'verify_connection', lambda value: value['username'])

    assert ls.main(['--session-file', str(session_path), '--snapshot-file', str(snapshot_path),
                    'connect', '--username', 'david_choi']) == 0

    output = capsys.readouterr().out
    assert 'x' * 32 not in output
    assert json.loads(session_path.read_text())['session'] == 'x' * 32
    assert stat.S_IMODE(session_path.stat().st_mode) == 0o600


def test_headless_login_prompts_without_storing_or_printing_password(tmp_path, monkeypatch, capsys):
    session_path = tmp_path / 'session.json'
    snapshot_path = tmp_path / 'history.json'
    monkeypatch.setattr(ls.sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr('builtins.input', lambda prompt: 'david@example.com')
    monkeypatch.setattr(ls.getpass, 'getpass', lambda prompt: 'not-persisted-password')
    monkeypatch.setattr(ls, 'login_with_browser', lambda cdp, username, login, password: {
        'session': 'y' * 32, 'csrf_token': 'csrf-value',
    })
    monkeypatch.setattr(ls, 'verify_connection', lambda value: value['username'])

    assert ls.main(['--session-file', str(session_path), '--snapshot-file', str(snapshot_path),
                    'login', '--username', 'david_choi']) == 0

    output = capsys.readouterr().out
    saved = json.loads(session_path.read_text())
    assert 'not-persisted-password' not in output
    assert 'not-persisted-password' not in session_path.read_text()
    assert saved['session'] == 'y' * 32
    assert saved['csrf_token'] == 'csrf-value'


def test_headed_login_uses_manual_browser_session_without_terminal_password(tmp_path, monkeypatch):
    session_path = tmp_path / 'session.json'
    snapshot_path = tmp_path / 'history.json'
    called = {}
    monkeypatch.setattr(ls, 'login_in_headed_browser', lambda username, executable, timeout, parent: (
        called.update(username=username, executable=executable, timeout=timeout, parent=parent)
        or {'session': 'z' * 32, 'csrf_token': ''}
    ))
    monkeypatch.setattr(ls, 'verify_connection', lambda value: value['username'])

    assert ls.main(['--session-file', str(session_path), '--snapshot-file', str(snapshot_path),
                    'login', '--username', 'david_choi', '--headed', '--timeout-seconds', '120']) == 0

    assert called == {'username': 'david_choi', 'executable': '/snap/bin/chromium',
                      'timeout': 120, 'parent': tmp_path}
    assert json.loads(session_path.read_text())['session'] == 'z' * 32


def test_headed_login_rejects_an_unbounded_wait_before_opening_browser(tmp_path, monkeypatch):
    monkeypatch.setenv('DISPLAY', ':0')
    with pytest.raises(ls.LeetCodeSyncError, match='between 30 and 900'):
        ls.login_in_headed_browser('david_choi', '/snap/bin/chromium', 901, tmp_path)


def test_cookie_value_selects_only_the_requested_cookie():
    cookies = [{'name': 'csrftoken', 'value': 'csrf'}, {'name': 'LEETCODE_SESSION', 'value': 'session'}]
    assert ls._cookie_value(cookies, 'LEETCODE_SESSION') == 'session'
    assert ls._cookie_value(cookies, 'missing') == ''


def test_headed_login_verifies_the_issued_csrf_cookie(tmp_path, monkeypatch):
    from contextlib import contextmanager
    import sys
    from types import SimpleNamespace
    monkeypatch.setenv('DISPLAY', ':98')
    executable = tmp_path / 'chrome'
    executable.write_text('browser fixture')
    executable.chmod(0o700)
    cookies = [{'name': 'LEETCODE_SESSION', 'value': 's' * 32},
               {'name': 'csrftoken', 'value': 'issued-csrf'}]
    page = SimpleNamespace(goto=lambda *a, **k: None)
    closed = []
    context = SimpleNamespace(pages=[page], cookies=lambda _: cookies,
                              close=lambda: closed.append(True))
    @contextmanager
    def playwright():
        yield SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=lambda *a, **k: context))
    monkeypatch.setitem(sys.modules, 'playwright.sync_api', SimpleNamespace(
        Error=RuntimeError, sync_playwright=playwright))
    candidates = []
    monkeypatch.setattr(ls, 'verify_connection', lambda candidate: candidates.append(candidate) or 'david')
    result = ls.login_in_headed_browser('david', str(executable), 60, tmp_path)
    assert candidates[0]['csrf_token'] == 'issued-csrf'
    assert result['csrf_token'] == 'issued-csrf'
    assert closed == [True]
    assert not list(tmp_path.glob('leetcode-login-*'))


@pytest.mark.parametrize(('page_text', 'expected'), [
    ('Your username or password is incorrect.', 'rejected the login ID or password'),
    ('Just a moment... Cloudflare 보안 확인 수행 중', 'Cloudflare blocked the headless browser'),
    ('Please complete the CAPTCHA to continue.', 'requires CAPTCHA verification'),
    ('Enter your two-factor verification code.', 'requires MFA verification'),
])
def test_login_failure_reason_is_specific(page_text, expected):
    assert expected in ls.login_failure_reason(page_text)


def test_status_never_exposes_saved_session(tmp_path):
    session_path = tmp_path / 'session.json'
    snapshot_path = tmp_path / 'history.json'
    ls.save_private_json(session_path, connection())
    snapshot = ls.normalize_history(history_data(), 'david_choi')
    snapshot['accepted_solutions'] = [{'slug': 'two-sum', 'code': 'private submitted source'}]
    ls.save_private_json(snapshot_path, snapshot)

    status = ls.public_status(session_path, snapshot_path)

    assert status['linked']['username'] == 'david_choi'
    assert 'session' not in json.dumps(status)
    assert 'private submitted source' not in json.dumps(status)
    assert status['snapshot']['total_solved'] == 12


def test_bad_session_is_rejected_without_network():
    with pytest.raises(ls.LeetCodeSyncError, match='malformed'):
        ls.validate_session('too-short')
    with pytest.raises(ls.LeetCodeSyncError, match='username'):
        ls.validate_username('bad user')


def test_graphql_failure_hides_cookie_value(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError('network error')

    monkeypatch.setattr(ls, 'urlopen', fail)
    token = 'secret-cookie-value-that-must-not-appear'
    with pytest.raises(ls.LeetCodeSyncError) as error:
        ls.graphql('query { x }', {}, {**connection(), 'session': token})
    assert token not in str(error.value)


def test_disconnect_removes_only_session(tmp_path):
    session_path = tmp_path / 'session.json'
    snapshot_path = tmp_path / 'history.json'
    ls.save_private_json(session_path, connection())
    ls.save_private_json(snapshot_path, ls.normalize_history(history_data(), 'david_choi'))

    assert ls.main(['--session-file', str(session_path), '--snapshot-file', str(snapshot_path),
                    'disconnect']) == 0

    assert not session_path.exists()
    assert snapshot_path.exists()


def test_cookie_rotation_ignores_deleted_and_unrelated_cookies():
    fresh = 'fresh-session-' + 'x' * 32
    assert ls.response_cookie_updates([
        'LEETCODE_SESSION=; Max-Age=0; Domain=.leetcode.com',
        'csrftoken=csrf-issued; Domain=.leetcode.com',
        f'LEETCODE_SESSION={fresh}; Domain=.leetcode.com; Max-Age=1209600',
        'unrelated=private', 'csrftoken=wrong-site; Domain=other.example']) == {
            'session': fresh, 'csrf_token': 'csrf-issued'}


@pytest.mark.parametrize('authenticated', [True, False])
def test_source_sync_persists_only_server_rotations_verified_for_the_same_owner(tmp_path, monkeypatch, authenticated):
    session, snapshot = tmp_path / 'session.json', tmp_path / 'history.json'
    original = connection()
    ls.save_private_json(session, original)
    calls = []
    def request(query, variables, linked):
        calls.append(query)
        if query == ls.HISTORY_QUERY:
            linked['session'] = 'rotated-server-session-' + 'x' * 32
            linked['csrf_token'] = 'issued-csrf'
            return history_data()
        assert query == ls.USER_STATUS_QUERY
        return {'userStatus': {'username': original['username'] if authenticated else None}}
    monkeypatch.setattr(ls, 'graphql', request)
    ls.sync(session, snapshot, stats_only=True)
    saved = json.loads(session.read_text())
    assert (saved['session'] != original['session']) is authenticated
    assert saved['linked_at'] == original['linked_at']
    assert len(calls) == 2
    assert session.stat().st_mode & 0o777 == 0o600


def test_graphql_applies_only_cookies_from_a_successful_response(monkeypatch):
    import io
    from email.message import Message
    headers = Message()
    headers.add_header('Set-Cookie', 'LEETCODE_SESSION=' + 'r' * 32 + '; Domain=.leetcode.com')
    class Response(io.BytesIO):
        pass
    response = Response(json.dumps({'data': {'userStatus': {'username': 'david_choi'}}}).encode())
    response.headers = headers
    monkeypatch.setattr(ls, 'urlopen', lambda *_args, **_kwargs: response)
    linked = connection()
    assert ls.graphql(ls.USER_STATUS_QUERY, {}, linked)['userStatus']['username'] == 'david_choi'
    assert linked['session'] == 'r' * 32


def test_stats_only_updates_account_total_and_preserves_private_source(tmp_path, monkeypatch):
    session, snapshot = tmp_path / 'session.json', tmp_path / 'history.json'
    ls.save_private_json(session, connection())
    source = [{'slug': 'two-sum', 'code': 'saved implementation'}]
    ls.save_private_json(snapshot, {'username': 'david_choi', 'accepted_solutions': source})
    calls = []
    def request(query, *_args):
        calls.append(query)
        return history_data()
    monkeypatch.setattr(ls, 'graphql', request)
    result = ls.sync(session, snapshot, stats_only=True)
    assert result['total_solved'] == 12
    assert result['accepted_solutions'] == source
    assert calls == [ls.HISTORY_QUERY]


def test_solution_endpoint_failure_does_not_block_account_progress(tmp_path, monkeypatch):
    session, snapshot = tmp_path / 'session.json', tmp_path / 'history.json'
    ls.save_private_json(session, connection())
    def request(query, *_args):
        if query == ls.HISTORY_QUERY:
            return history_data()
        raise ls.LeetCodeSyncError('Private source endpoint unavailable')
    monkeypatch.setattr(ls, 'graphql', request)
    result = ls.sync(session, snapshot)
    assert json.loads(snapshot.read_text())['total_solved'] == 12
    assert result['solution_sync_error']
    assert result['solution_sync_status'] == 'error'


def test_failed_account_refresh_preserves_snapshot(tmp_path, monkeypatch):
    session, snapshot = tmp_path / 'session.json', tmp_path / 'history.json'
    ls.save_private_json(session, connection())
    ls.save_private_json(snapshot, {'total_solved': 9})
    before = snapshot.read_bytes()
    def request(*_args):
        raise ls.LeetCodeSyncError('Unavailable')
    monkeypatch.setattr(ls, 'graphql', request)
    with pytest.raises(ls.LeetCodeSyncError):
        ls.sync(session, snapshot, stats_only=True)
    assert snapshot.read_bytes() == before


def test_stats_only_never_carries_source_from_another_account(tmp_path, monkeypatch):
    session, snapshot = tmp_path / 'session.json', tmp_path / 'history.json'
    ls.save_private_json(session, connection())
    ls.save_private_json(snapshot, {'username': 'someone_else', 'accepted_solutions': [{'code': 'private'}]})
    monkeypatch.setattr(ls, 'graphql', lambda *_args: history_data())
    assert 'accepted_solutions' not in ls.sync(session, snapshot, stats_only=True)


def test_incremental_download_reuses_unchanged_source_but_fetches_new_accept(monkeypatch):
    saved = [{'slug': 'two-sum', 'accepted_at': '2026-09-14T12:00:00+00:00', 'code': 'original'}]
    monkeypatch.setattr(ls, 'graphql', lambda *_args: pytest.fail('Unchanged source downloaded again'))
    assert ls.fetch_accepted_solutions(connection(), recent_submissions_data(), saved) == saved
    saved[0]['accepted_at'] = '2026-09-13T12:00:00+00:00'
    monkeypatch.setattr(ls, 'graphql', lambda *_args: submission_details_data())
    assert ls.fetch_accepted_solutions(connection(), recent_submissions_data(), saved)[0]['code'] != 'original'


def test_sync_retains_older_downloads_outside_recent_list(tmp_path, monkeypatch):
    session, snapshot = tmp_path / 'session.json', tmp_path / 'history.json'
    ls.save_private_json(session, connection())
    older = {'slug': 'old-problem', 'accepted_at': '2026-09-01T00:00:00+00:00', 'code': 'older source'}
    ls.save_private_json(snapshot, {'username': 'david_choi', 'accepted_solutions': [older]})
    def request(query, *_args):
        return {ls.USER_STATUS_QUERY: {'userStatus': {'username': 'david_choi'}},
                ls.HISTORY_QUERY: history_data(), ls.RECENT_SUBMISSIONS_QUERY: recent_submissions_data(),
                ls.SUBMISSION_DETAILS_QUERY: submission_details_data()}[query]
    monkeypatch.setattr(ls, 'graphql', request)
    result = ls.sync(session, snapshot, missing_only=True)
    assert {row['slug'] for row in result['accepted_solutions']} == {'old-problem', 'two-sum'}
    assert result['solutions_synced_at']
    assert result['solution_sync_status'] == 'ok'


def test_expired_session_reports_source_failure_while_retaining_counts(tmp_path, monkeypatch):
    session, snapshot = tmp_path / 'session.json', tmp_path / 'history.json'
    ls.save_private_json(session, connection())
    monkeypatch.setattr(ls, 'graphql', lambda query, *_args:
                        history_data() if query == ls.HISTORY_QUERY else {'userStatus': None})
    result = ls.sync(session, snapshot)
    assert result['total_solved'] == 12
    assert 'Log in again' in result['solution_sync_error']
    assert result['solution_sync_status'] == 'reauth_required'


def test_reauthenticated_sync_downloads_missing_code_and_clears_auth_failure(tmp_path, monkeypatch):
    session, snapshot = tmp_path / 'session.json', tmp_path / 'history.json'
    ls.save_private_json(session, connection())
    ls.save_private_json(snapshot, {'username': 'david_choi', 'solution_sync_status': 'reauth_required',
        'solution_sync_error': 'Log in again', 'accepted_solutions': []})
    responses = {ls.USER_STATUS_QUERY: {'userStatus': {'username': 'david_choi'}},
                 ls.HISTORY_QUERY: history_data(), ls.RECENT_SUBMISSIONS_QUERY: recent_submissions_data(),
                 ls.SUBMISSION_DETAILS_QUERY: submission_details_data()}
    monkeypatch.setattr(ls, 'graphql', lambda query, *_: responses[query])
    result = ls.sync(session, snapshot, missing_only=True)
    assert result['solution_sync_status'] == 'ok'
    assert 'solution_sync_error' not in result
    assert result['accepted_solutions'][0]['code'] == submission_details_data()['submissionDetails']['code']
    assert 'session' not in result


def test_headed_login_waits_for_verified_account_after_prelogin_cookie(tmp_path, monkeypatch):
    from contextlib import contextmanager
    import sys
    from types import SimpleNamespace
    monkeypatch.setenv('DISPLAY', ':98')
    executable = tmp_path / 'chrome'
    executable.write_text('fixture')
    executable.chmod(0o700)
    sessions = iter(['prelogin', 'actual-login'])
    waits, checked, closed = [], [], []
    page = SimpleNamespace(goto=lambda *a, **k: None, wait_for_timeout=lambda ms: waits.append(ms))
    context = SimpleNamespace(pages=[page], cookies=lambda _: [
        {'name': 'LEETCODE_SESSION', 'value': next(sessions)}, {'name': 'csrftoken', 'value': 'csrf'}],
        close=lambda: closed.append(True))
    @contextmanager
    def playwright():
        yield SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=lambda *a, **k: context))
    monkeypatch.setitem(sys.modules, 'playwright.sync_api', SimpleNamespace(Error=RuntimeError, sync_playwright=playwright))
    def verify(candidate):
        checked.append(candidate['session'])
        if candidate['session'] == 'prelogin':
            raise ls.LeetCodeSyncError('Not signed in yet')
        return 'david'
    monkeypatch.setattr(ls, 'verify_connection', verify)
    assert ls.login_in_headed_browser('david', str(executable), 60, tmp_path)['session'] == 'actual-login'
    assert checked == ['prelogin', 'actual-login'] and waits == [500] and closed == [True]
    assert not list(tmp_path.glob('leetcode-login-*'))
