# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Exercise isolated reconnection and authenticated source refresh boundaries."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import leetcode_browser_login as login


def test_desktop_reuses_runtime_without_exposing_ports_or_sharing_browser_profile():
    commands = login.desktop_commands(Path('/runtime'), Path('/private/xauth'))
    assert commands[0][commands[0].index('-auth') + 1] == '/private/xauth'
    assert '-nolisten' in commands[0] and 'tcp' in commands[0]
    assert commands[1][commands[1].index('-listen') + 1] == '127.0.0.1'
    assert '127.0.0.1:18782' in commands[2] and '127.0.0.1:15903' in commands[2]
    assert all('youtube.com' not in ' '.join(command) for command in commands)


def test_status_has_private_permissions_and_atomic_replacement(tmp_path):
    path = tmp_path / 'private/status.json'
    login.save_status(path, 'awaiting_login', web_port=18782)
    login.save_status(path, 'connected')
    assert json.loads(path.read_text()) == {'status': 'connected'}
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize('status', ['reauth_required', 'error', None])
def test_refresh_requires_private_source_access_before_inference(tmp_path, status):
    root = tmp_path / 'data/interview'
    root.mkdir(parents=True)
    (root / 'leetcode_history.json').write_text(json.dumps({'solution_sync_status': status}))
    calls = []
    with pytest.raises(RuntimeError, match='private submission access'):
        login.refresh_sources(tmp_path, runner=lambda command, **_: calls.append(command))
    assert len(calls) == 1
    assert calls[0][-2:] == ['sync', '--missing-only']


def test_fresh_source_triggers_cached_review_preparation(tmp_path):
    root = tmp_path / 'data/interview'
    root.mkdir(parents=True)
    (root / 'leetcode_history.json').write_text(json.dumps({
        'solution_sync_status': 'ok', 'accepted_solutions': [{'code': 'actual'}]}))
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        assert kwargs['env']['HERMES_HOME'] == str(tmp_path)
        return SimpleNamespace(returncode=0)
    assert login.refresh_sources(tmp_path, runner) == {'downloaded_solution_count': 1,
                                                      'reviews_prepared': True}
    assert calls[1][-1] == 'prepare'


def test_login_timeout_is_bounded_before_starting_any_component(tmp_path):
    with pytest.raises(SystemExit):
        login.main(['--home', str(tmp_path), '--username', 'david', '--timeout', '901'])
    assert not (tmp_path / 'data').exists()


def test_duplicate_login_does_not_change_existing_status(tmp_path, monkeypatch):
    import fcntl
    root = tmp_path / 'data/interview'
    root.mkdir(parents=True)
    status = root / 'leetcode-login-status.json'
    login.save_status(status, 'awaiting_login')
    monkeypatch.setattr(login, 'reconnect', lambda *_: pytest.fail('Duplicate browser'))
    with (root / '.leetcode-login.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        assert login.main(['--home', str(tmp_path), '--username', 'david']) == 1
    assert json.loads(status.read_text())['status'] == 'awaiting_login'


def test_background_start_survives_request_and_reuses_active_window(tmp_path):
    status_path = tmp_path / 'data/interview/leetcode-login-status.json'
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        if command[0] == 'systemctl':
            return SimpleNamespace(returncode=1)
        login.save_status(status_path, 'awaiting_login', session='PRIVATE')
        return SimpleNamespace(returncode=0)
    result = login.start_login(tmp_path, Path('/runtime'), 'david', 900, runner)
    assert result == {'status': 'awaiting_login', 'url': login.LOGIN_URL}
    assert calls[1][:5] == ['systemd-run', '--user', '--unit=hermes-leetcode-login', '--collect', '--property=RuntimeMaxSec=55min']
    assert '--home' in calls[1] and '--username' in calls[1]
    calls.clear()
    def active(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0)
    assert login.start_login(tmp_path, Path('/runtime'), 'david', 900, active) == result
    assert len(calls) == 1
    assert 'PRIVATE' not in json.dumps(result)


def test_background_start_reports_launch_failure_without_credentials(tmp_path):
    def runner(command, **kwargs):
        return SimpleNamespace(returncode=1, stderr=b'potentially-private')
    with pytest.raises(RuntimeError, match='Could not start'):
        login.start_login(tmp_path, Path('/runtime'), 'david', 900, runner)
    assert json.loads((tmp_path / 'data/interview/leetcode-login-status.json').read_text())['status'] == 'failed'
