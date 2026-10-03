# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Check server-side interactive login isolation and session reuse verification."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import youtube_browser_login as login


def test_cookie_transfer_keeps_youtube_attributes_and_excludes_other_domains():
    cookie = {'domain': '.youtube.com', 'name': 'SID', 'value': 'private',
              'secure': True, 'httpOnly': True, 'sameSite': 'None', 'expires': -1}
    result = login.youtube_cookies([cookie, {'domain': '.google.com', 'value': 'other'},
                                   {'domain': 'youtube.com.evil.example', 'name': 'SID'}])
    assert result == [cookie]
    assert result[0] is not cookie


def test_unsigned_browser_payload_is_rejected_without_exposing_values():
    with pytest.raises(ValueError) as error:
        login.youtube_cookies([{'domain': '.youtube.com', 'name': 'PREF', 'value': 'private'}])
    assert 'private' not in str(error.value)


def test_login_dispatches_navigation_from_initial_blank_page_before_url_filter():
    class Page:
        url = 'about:blank'
        def wait_for_timeout(self, delay):
            self.url = 'https://www.youtube.com/feed/history'
        def evaluate(self, script):
            return True
    cookies = [{'domain': '.youtube.com', 'name': 'SID', 'value': 'private-session'}]
    context = SimpleNamespace(pages=[Page()], cookies=lambda: cookies)
    assert login.await_authenticated_cookies(context, [], 60) == cookies


def test_unfinished_login_expires_without_reading_or_saving_credentials(monkeypatch):
    times = iter([0, 0, 61])
    monkeypatch.setattr(login.time, 'monotonic', lambda: next(times))
    page = SimpleNamespace(url='https://accounts.google.com/', wait_for_timeout=lambda *a: None)
    context = SimpleNamespace(pages=[page], cookies=lambda: pytest.fail('Login not yet verified.'))
    with pytest.raises(TimeoutError):
        login.await_authenticated_cookies(context, [], 60)


def test_temporary_desktop_binds_loopback_and_uses_separate_browser_profile():
    commands = login.desktop_commands(Path('/runtime'), Path('/private'), Path('/chrome'), ':97')
    assert '-nolisten' in commands[0] and 'tcp' in commands[0]
    assert commands[1][commands[1].index('-listen') + 1] == '127.0.0.1'
    assert '127.0.0.1:18780' in commands[2]
    assert '127.0.0.1:15901' in commands[2]
    assert '--remote-debugging-address=127.0.0.1' in commands[3]
    assert '--user-data-dir=/private/login-browser' in commands[3]
    assert '--enable-automation' not in commands[3]
    assert '--headless' not in commands[3]


@pytest.mark.parametrize('returncodes,expected,calls', [([0, 0], True, 2),
                                                     ([1], False, 1), ([0, 1], False, 2)])
def test_login_requires_initial_connection_and_independent_sync(returncodes, expected, calls):
    seen = []
    def runner(command, **kwargs):
        seen.append(command)
        assert kwargs['timeout'] == 150
        return SimpleNamespace(returncode=returncodes[len(seen) - 1])
    assert login.verify_session(Path('/history.py'), Path('/private'), runner=runner) is expected
    assert len(seen) == calls
    assert seen[0][-2:] == ['connect', '--saved-cookies']
    if calls == 2:
        assert seen[1][-1] == 'sync'


def test_saved_session_and_safe_status_are_owner_only(tmp_path):
    target = tmp_path / 'private' / 'session.json'
    login.save_private_json(target, {'version': 1, 'cookies': []})
    assert json.loads(target.read_text()) == {'version': 1, 'cookies': []}
    assert target.stat().st_mode & 0o777 == 0o600
    assert target.parent.stat().st_mode & 0o777 == 0o700
    assert list(target.parent.iterdir()) == [target]


def test_process_cleanup_escalates_if_component_does_not_exit():
    import subprocess
    calls = []
    class Process:
        def poll(self):
            return None
        def terminate(self):
            calls.append('terminate')
        def wait(self, timeout):
            if calls == ['terminate']:
                raise subprocess.TimeoutExpired('component', timeout)
            calls.append('wait')
        def kill(self):
            calls.append('kill')
    login.stop_process(Process())
    assert calls == ['terminate', 'kill', 'wait']


@pytest.mark.parametrize('verified', [True, False])
def test_cli_saves_session_but_claims_connected_only_after_reuse_verification(tmp_path, monkeypatch, capsys, verified):
    monkeypatch.setattr(login.signal, 'signal', lambda *a: None)
    monkeypatch.setattr(login, 'run_desktop', lambda *a: [{'domain': '.youtube.com', 'name': 'SID',
                                                       'value': 'private-session-value'}])
    monkeypatch.setattr(login, 'verify_session', lambda *a: verified)
    snapshot = tmp_path / 'snapshot.json'
    snapshot.write_text('existing history')
    assert login.main(['--data-dir', str(tmp_path)]) == (0 if verified else 1)
    state = json.loads((tmp_path / 'login-status.json').read_text())
    assert state['status'] == ('connected' if verified else 'failed')
    assert (tmp_path / 'session.json').stat().st_mode & 0o777 == 0o600
    assert snapshot.read_text() == 'existing history'
    assert 'private-session-value' not in str(capsys.readouterr())
