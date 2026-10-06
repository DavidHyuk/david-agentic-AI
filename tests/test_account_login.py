# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Verify fixed account routing, private metadata and reversible reconnects."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import account_login as login
import chatgpt_archive
import leetcode_browser_login
import youtube_browser_login


def inactive(command, **kwargs):
    return SimpleNamespace(returncode=1)


def test_room_accounts_reuse_credential_owners_and_never_expose_private_values(tmp_path):
    root = tmp_path / 'data/chatgpt'
    root.mkdir(parents=True)
    (root / 'browser-status.json').write_text(json.dumps({'browser_status': 'closed',
        'authenticated_at': '2026-10-05T01:00:00+00:00', 'email': 'PRIVATE', 'cookies': 'PRIVATE'}))
    english = tmp_path / 'data/english'
    english.mkdir()
    (english / 'kakao-skill-url.txt').write_text('https://example.com/kakao/PRIVATE')
    coding = login.connections(tmp_path, 'coding', inactive)
    assert [row['service'] for row in coding['accounts']] == ['leetcode', 'chatgpt']
    assert coding['accounts'][1]['status'] == 'verified'
    assert login.connections(tmp_path, 'hq', inactive)['accounts'][0] == coding['accounts'][1]
    assert [row['service'] for row in login.connections(tmp_path, 'podcast', inactive)['accounts']] == ['youtube']
    status = login.connections(tmp_path, 'english', inactive)
    assert status['accounts'][0]['skill_url_available']
    assert 'PRIVATE' not in json.dumps([coding, status])
    assert login.connections(tmp_path, '../../', inactive) == {'accounts': []}


@pytest.mark.parametrize('service', ['chatgpt', 'youtube'])
def test_start_uses_fixed_existing_helper_and_reuses_active_window(tmp_path, service):
    runtime = tmp_path / 'venvs/youtube-history/bin/python'
    runtime.parent.mkdir(parents=True)
    runtime.touch()
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1 if command[0] == 'systemctl' else 0)
    result = login.start_login(tmp_path, service, runner)
    launch = next(command for command in calls if command[0] == 'systemd-run')
    assert '--collect' in launch and '--property=RuntimeMaxSec=25min' in launch
    assert '--unit=' + login.UNITS[service] in launch
    assert str(runtime) in launch and '--timeout' in launch
    assert '--request-export' not in launch
    if service == 'chatgpt':
        assert '--close-after-login' in launch
        assert '--data-dir' in launch and str(tmp_path / 'data/chatgpt') in launch
    path = login.status_path(tmp_path, service)
    assert path.stat().st_mode & 0o777 == 0o600
    assert result['service'] == service
    login.save_json(path, {'browser_status' if service == 'chatgpt' else 'status': 'awaiting_login'})
    def active(command, **kwargs):
        assert command[0] == 'systemctl'
        return SimpleNamespace(returncode=0)
    assert login.start_login(tmp_path, service, active)['url'] == login.login_url(service)


def test_unknown_service_cannot_launch_arbitrary_commands(tmp_path):
    with pytest.raises(ValueError):
        login.start_login(tmp_path, 'untrusted; command', lambda *a, **k: pytest.fail('command ran'))


def test_failed_start_restores_prior_verified_status(tmp_path):
    runtime = tmp_path / 'venvs/youtube-history/bin/python'
    runtime.parent.mkdir(parents=True)
    runtime.touch()
    path = login.status_path(tmp_path, 'chatgpt')
    prior = {'browser_status': 'closed', 'authenticated_at': 'verified'}
    login.save_json(path, prior)
    with pytest.raises(ValueError, match='Could not start'):
        login.start_login(tmp_path, 'chatgpt', inactive)
    assert login.read_json(path) == prior


def test_private_kakao_url_requires_explicit_setup_and_valid_https_endpoint(tmp_path):
    path = tmp_path / 'data/english/kakao-skill-url.txt'
    path.parent.mkdir(parents=True)
    path.write_text('https://example.com/kakao/private-setup-value')
    assert login.kakao_url(tmp_path) == {'url': path.read_text()}
    for invalid in ['javascript:alert(1)', 'https://user:pass@example.com/kakao/path',
                    'https://example.com/unrelated', 'https://example.com/kakao/path?secret=value']:
        path.write_text(invalid)
        with pytest.raises(ValueError, match='invalid'):
            login.kakao_url(tmp_path)


def test_login_desktops_have_distinct_displays_ports_and_profiles():
    leetcode = leetcode_browser_login.desktop_commands(Path('/runtime'), Path('/auth'))
    chatgpt = chatgpt_archive.desktop_commands(Path('/runtime'), Path('/chatgpt'), Path('/chrome'))
    youtube = youtube_browser_login.desktop_commands(Path('/runtime'), Path('/youtube'), Path('/chrome'), ':97')
    assert len({commands[0][1] for commands in (leetcode, chatgpt, youtube)}) == 3
    assert len(set(login.PORTS.values())) == 3
    assert '--user-data-dir=/chatgpt/browser' in chatgpt[3]
    assert '--user-data-dir=/youtube/login-browser' in youtube[3]


def test_chatgpt_sync_error_does_not_imply_expired_login(tmp_path):
    root = tmp_path / 'data/chatgpt'
    login.save_json(root / 'browser-status.json', {'browser_status': 'closed',
                                                 'authenticated_at': '2026-10-04T01:00:00+00:00'})
    login.save_json(root / 'daily-sync.json', {'status': 'error', 'last_attempt_at': '2026-10-05T01:00:00+00:00',
                                             'error': 'Project vector rebuild failed; prior sources retained.'})
    assert login.connection(tmp_path, 'chatgpt', inactive)['status'] == 'sync_error'
    login.save_json(root / 'daily-sync.json', {'status': 'error', 'last_attempt_at': '2026-10-05T01:00:00+00:00',
                                             'error': 'ChatGPT login needs owner attention; prior sources retained.'})
    assert login.connection(tmp_path, 'chatgpt', inactive)['status'] == 'reconnect'


def test_failed_manual_login_cannot_reuse_old_auth_timestamp_as_success(tmp_path):
    path = login.status_path(tmp_path, 'chatgpt')
    login.save_json(path, {'browser_status': 'closed', 'authenticated_at': '2026-10-04T01:00:00+00:00',
                          'login_requested_at': '2026-10-05T01:00:00+00:00'})
    assert login.connection(tmp_path, 'chatgpt', inactive)['status'] == 'reconnect'
