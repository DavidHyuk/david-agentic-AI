# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Check dated watch-history selection and failure-safe evening delivery."""
from datetime import datetime
import json

import pytest
import youtube_history as yh


def video(video_id='abcdefghijk', channel='English Goal Podcast', **changes):
    return {'title': 'A real watched episode', 'channel': channel,
            'url': 'https://www.youtube.com/watch?v=' + video_id, **changes}


def test_only_today_exact_channel_canonical_deduplicated_links():
    rows = [{'heading': 'Today', 'videos': [video(), video(), video('bbbbbbbbbbb', 'Other Podcast'),
                                           video('ccccccccccc', url='https://evil.example/watch?v=ccccccccccc'),
                                           video('invalid')]},
            {'heading': 'Yesterday', 'videos': [video('ddddddddddd')]}]
    result = yh.normalize_sections(rows, yh.DEFAULT_CHANNEL)
    assert len(result) == 1
    assert result[0]['url'] == 'https://www.youtube.com/watch?v=abcdefghijk'


def test_yesterday_only_is_not_sent_as_today():
    assert yh.normalize_sections([{'heading': 'Yesterday', 'videos': [video()]}], yh.DEFAULT_CHANNEL) == []
    assert yh.render_digest({'date': '2026-10-03', 'videos': []}, today='2026-10-03') == '[SILENT]'


@pytest.mark.parametrize('sections', [[], [{'heading': 'Unexpected heading', 'videos': [video()]}]])
def test_unknown_history_layout_fails_closed(sections):
    with pytest.raises(yh.HistoryError):
        yh.normalize_sections(sections, yh.DEFAULT_CHANNEL)


def test_refresh_preserves_prior_snapshot_when_collection_fails(tmp_path):
    path = tmp_path / 'snapshot.json'
    path.write_text('{"date": "2026-10-02"}')
    def unavailable(*args, **kwargs):
        raise yh.HistoryError('unavailable')
    with pytest.raises(yh.HistoryError):
        yh.refresh(tmp_path, tmp_path / 'browser', '/browser', yh.DEFAULT_CHANNEL, collector=unavailable)
    assert json.loads(path.read_text()) == {'date': '2026-10-02'}


def test_refresh_dates_snapshot_and_writes_private_data(tmp_path):
    now = datetime(2026, 10, 3, 18, tzinfo=yh.TZ)
    snapshot = yh.refresh(tmp_path, tmp_path / 'browser', '/browser', yh.DEFAULT_CHANNEL,
                          collector=lambda *a, **kw: [{'heading': 'Today', 'videos': [video()]}], now=now)
    assert snapshot['date'] == '2026-10-03'
    assert (tmp_path / 'snapshot.json').stat().st_mode & 0o777 == 0o600
    digest = yh.render_digest(snapshot, today='2026-10-03')
    assert 'https://www.youtube.com/watch?v=abcdefghijk' in digest
    assert 'A real watched episode' in digest
    assert '끝까지 시청' in digest


def test_stale_digest_rejected_and_long_message_bounded():
    with pytest.raises(yh.HistoryError):
        yh.render_digest({'date': '2026-10-02', 'videos': [video()]}, today='2026-10-03')
    digest = yh.render_digest({'date': '2026-10-03', 'videos': [
        {'title': 'a' * 160, 'url': 'https://www.youtube.com/watch?v=abcdefghijk'} for _ in range(100)]}, today='2026-10-03')
    assert len(digest) < 4000
    assert '총 100편 중 최근' in digest


def test_notify_failure_never_reads_previous_snapshot(tmp_path, monkeypatch, capsys):
    (tmp_path / 'snapshot.json').write_text('{"date":"2026-10-03","videos":[{"title":"stale"}]}')
    def fail(*a, **kw):
        raise yh.HistoryError('login required')
    monkeypatch.setattr(yh, 'refresh', fail)
    monkeypatch.setattr(yh, 'is_connected', lambda *args: True)
    assert yh.main(['--data-dir', str(tmp_path), 'notify']) == 1
    output = capsys.readouterr()
    assert output.out == ''
    assert 'login required' in output.err


def cookies_text(*rows):
    return '# Netscape HTTP Cookie File\n' + '\n'.join(rows) + '\n'


def test_cookie_import_selects_live_youtube_credentials_and_http_only():
    text = cookies_text(
        '#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t2000000000\tSID\tprivate-session',
        '.google.com\tTRUE\t/\tTRUE\t2000000000\tSID\tgoogle-secret',
        'youtube.com.evil.example\tTRUE\t/\tTRUE\t2000000000\tSID\tunrelated',
        '.youtube.com\tTRUE\t/\tTRUE\t100\tSAPISID\texpired',
        '.youtube.com\tTRUE\t/\tTRUE\t0\tPREF\tpreference',
    )
    imported = yh.parse_cookies(text, now=1000)
    assert [cookie['name'] for cookie in imported] == ['SID', 'PREF']
    assert imported[0]['httpOnly'] is True
    assert imported[1]['expires'] == -1
    assert 'google-secret' not in json.dumps(imported)


@pytest.mark.parametrize('text', [
    'invalid secret-value',
    cookies_text('.youtube.com\tTRUE\t/\tTRUE\t2000000000\tPREF\tsecret-value'),
    cookies_text('.youtube.com\tTRUE\t/\tTRUE\tinvalid\tSID\tsecret-value'),
])
def test_invalid_cookie_inputs_never_echo_values(text):
    with pytest.raises(yh.HistoryError) as error:
        yh.parse_cookies(text, now=1000)
    assert 'secret-value' not in str(error.value)


def test_unlinked_notify_is_silent_without_browser_launch(tmp_path, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail('An unlinked scheduled job must not launch Chromium.')
    monkeypatch.setattr(yh, 'refresh', forbidden)
    assert yh.main(['--data-dir', str(tmp_path), 'notify']) == 0
    assert capsys.readouterr().out == '[SILENT]\n'


def test_connect_stdin_works_without_display_and_marks_only_verified_connection(tmp_path, monkeypatch, capsys):
    import io
    monkeypatch.delenv('DISPLAY', raising=False)
    monkeypatch.delenv('WAYLAND_DISPLAY', raising=False)
    monkeypatch.setattr(yh.sys, 'stdin', io.StringIO(cookies_text(
        '.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tprivate-session')))
    browser_dir = tmp_path / 'browser'
    def refreshed(*args, **kwargs):
        assert kwargs['cookies'][0]['name'] == 'SID'
        (browser_dir / 'Default').mkdir(parents=True)
        return {'synced_at': '2026-10-03T18:00:00-07:00', 'videos': []}
    monkeypatch.setattr(yh, 'refresh', refreshed)
    assert yh.main(['--data-dir', str(tmp_path), '--browser-dir', str(browser_dir),
                    'connect', '--cookies-stdin']) == 0
    assert yh.is_connected(tmp_path, browser_dir)
    assert 'private-session' not in capsys.readouterr().out
    assert (tmp_path / 'connection.json').stat().st_mode & 0o777 == 0o600


def test_failed_reconnection_clears_verified_marker_and_preserves_snapshot(tmp_path, monkeypatch, capsys):
    import io
    browser_dir = tmp_path / 'browser'
    (browser_dir / 'Default').mkdir(parents=True)
    yh.save_json(tmp_path / 'connection.json', {'version': 1, 'verified_at': 'old',
                                             'browser_dir': str(browser_dir.resolve())})
    (tmp_path / 'snapshot.json').write_text('{"date":"2026-10-02"}')
    monkeypatch.setattr(yh.sys, 'stdin', io.StringIO(cookies_text(
        '.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tprivate-session')))
    def failed(*args, **kwargs):
        raise yh.HistoryError('login rejected')
    monkeypatch.setattr(yh, 'refresh', failed)
    assert yh.main(['--data-dir', str(tmp_path), '--browser-dir', str(browser_dir),
                    'connect', '--cookies-stdin']) == 1
    assert not yh.is_connected(tmp_path, browser_dir)
    assert json.loads((tmp_path / 'snapshot.json').read_text())['date'] == '2026-10-02'
    assert 'private-session' not in str(capsys.readouterr())
