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


def test_normalize_history_keeps_only_read_only_progress_fields():
    snapshot = ls.normalize_history(history_data(), 'david_choi')
    assert snapshot['username'] == 'david_choi'
    assert snapshot['total_solved'] == 12
    assert snapshot['solved_by_difficulty'] == {'easy': 5, 'medium': 6, 'hard': 1}
    assert snapshot['recent_accepted'] == [{
        'title': 'Two Sum', 'slug': 'two-sum', 'accepted_at': '2026-09-14T12:00:00+00:00',
    }]
    assert 'session' not in snapshot


def test_sync_writes_an_owner_only_snapshot_without_session(tmp_path, monkeypatch):
    session_path = tmp_path / 'leetcode_session.json'
    snapshot_path = tmp_path / 'leetcode_history.json'
    ls.save_private_json(session_path, connection())
    monkeypatch.setattr(ls, 'graphql', lambda *args, **kwargs: history_data())

    snapshot = ls.sync(session_path, snapshot_path, limit=10)

    persisted = json.loads(snapshot_path.read_text())
    assert persisted == snapshot
    assert 'session' not in snapshot_path.read_text()
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
    ls.save_private_json(snapshot_path, ls.normalize_history(history_data(), 'david_choi'))

    status = ls.public_status(session_path, snapshot_path)

    assert status['linked']['username'] == 'david_choi'
    assert 'session' not in json.dumps(status)
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
