# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Check latest watched-podcast selection and failure-safe evening delivery."""
from datetime import datetime
import json

import pytest
import youtube_history as yh


def video(video_id='abcdefghijk', channel='English Goal Podcast', **changes):
    return {'title': 'A real watched episode', 'channel': channel,
            'url': 'https://www.youtube.com/watch?v=' + video_id, **changes}


def test_latest_exact_channel_canonical_link_wins_over_older_matches():
    rows = [{'heading': 'Today', 'videos': [video(), video(), video('bbbbbbbbbbb', 'Other Podcast'),
                                           video('ccccccccccc', url='https://evil.example/watch?v=ccccccccccc'),
                                           video('invalid')]},
            {'heading': 'Yesterday', 'videos': [video('ddddddddddd')]}]
    result = yh.normalize_sections(rows, yh.DEFAULT_CHANNEL)
    assert len(result) == 1
    assert result[0]['url'] == 'https://www.youtube.com/watch?v=abcdefghijk'


def test_yesterday_match_is_eligible_and_not_claimed_as_watched_today():
    videos = yh.normalize_sections([{'heading': 'Yesterday', 'videos': [video()]}], yh.DEFAULT_CHANNEL)
    assert len(videos) == 1
    assert videos[0]['history_heading'] == 'Yesterday'
    digest = yh.render_digest({'date': '2026-10-03', 'videos': videos}, today='2026-10-03')
    assert '가장 최근에 본' in digest
    assert '오늘 본' not in digest
    assert yh.render_digest({'date': '2026-10-03', 'videos': []}, today='2026-10-03') == '[SILENT]'


def test_skip_other_channels_and_invalid_links_to_find_latest_older_match():
    rows = [{'heading': 'Today', 'videos': [video(channel='Other Podcast'),
            video(url='https://www.youtube.com/shorts/abcdefghijk'), video(title='')]},
            {'heading': 'September 30, 2026', 'videos': [video('bbbbbbbbbbb'), video('ccccccccccc')]}]
    assert [item['video_id'] for item in yh.normalize_sections(rows, yh.DEFAULT_CHANNEL)] == ['bbbbbbbbbbb']


@pytest.mark.parametrize('newest_channel', yh.DEFAULT_CHANNELS)
def test_latest_video_across_both_channels_wins_without_channel_priority(newest_channel):
    other_channel = next(name for name in yh.DEFAULT_CHANNELS if name != newest_channel)
    rows = [{'heading': 'Today', 'videos': [video('bbbbbbbbbbb', newest_channel),
                                           video('ccccccccccc', other_channel)]}]
    assert yh.normalize_sections(rows, yh.DEFAULT_CHANNELS)[0]['video_id'] == 'bbbbbbbbbbb'


def test_english_title_on_unrelated_channel_is_not_a_podcast_match():
    rows = [{'heading': 'Today', 'videos': [video(channel='Technology News', title='Daily English Lesson')]}]
    assert yh.normalize_sections(rows, yh.DEFAULT_CHANNELS) == []


@pytest.mark.parametrize('title', ['English Podcast Episode', 'A PODCAST about science', 'My podcast'])
def test_podcast_title_matches_any_channel_before_an_older_known_channel(title):
    rows = [{'heading': 'Today', 'videos': [video('bbbbbbbbbbb', 'Another Channel', title=title)]},
            {'heading': 'Yesterday', 'videos': [video()]}]
    assert yh.normalize_sections(rows, yh.DEFAULT_CHANNELS)[0]['video_id'] == 'bbbbbbbbbbb'


@pytest.mark.parametrize('url', ['https://evil.example/watch?v=abcdefghijk',
                                'https://www.youtube.com/shorts/abcdefghijk'])
def test_podcast_title_does_not_allow_invalid_links_or_shorts(url):
    rows = [{'heading': 'Today', 'videos': [video(channel='Other', title='Podcast', url=url)]}]
    assert yh.normalize_sections(rows, yh.DEFAULT_CHANNELS) == []


@pytest.mark.parametrize('options,expected', [
    ([], list(yh.DEFAULT_CHANNELS)),
    (['--channel', 'Custom Podcast'], ['Custom Podcast']),
    (['--channel', 'First Podcast', '--channel', 'Second Podcast'], ['First Podcast', 'Second Podcast']),
])
def test_cli_passes_default_or_explicit_channels_to_refresh(tmp_path, monkeypatch, capsys, options, expected):
    monkeypatch.setattr(yh, 'is_connected', lambda *args: True)
    def refreshed(data_dir, browser_dir, executable, channels, **kwargs):
        assert channels == expected
        return {'date': '2026-10-03', 'videos': []}
    monkeypatch.setattr(yh, 'refresh', refreshed)
    assert yh.main(['--data-dir', str(tmp_path), *options, 'sync']) == 0
    assert capsys.readouterr().err == ''


def test_browser_search_continues_into_older_days_with_requested_channel(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import sys

    pages = [
        [{'heading': 'Today', 'videos': [video()]}],
        [{'heading': 'Today', 'videos': [video()]},
         {'heading': 'Yesterday', 'videos': [video('bbbbbbbbbbb')]}],
        [{'heading': 'Today', 'videos': [video()]},
         {'heading': 'Yesterday', 'videos': [video('bbbbbbbbbbb')]},
         {'heading': 'September 30, 2026', 'videos': [video('ccccccccccc', 'Requested Podcast')]}],
    ]
    class Page:
        index = 0
        def goto(self, *args, **kwargs):
            return SimpleNamespace(status=200)
        def wait_for_function(self, *args, **kwargs):
            pass
        def wait_for_selector(self, *args, **kwargs):
            pass
        def wait_for_timeout(self, *args):
            pass
        def evaluate(self, script):
            if script == yh.HISTORY_SCRIPT:
                return pages[self.index]
            if 'LOGGED_IN' in script:
                return True
            self.index += 1
    page = Page()
    context = SimpleNamespace(pages=[page], close=lambda: None)
    class Playwright:
        chromium = SimpleNamespace(launch_persistent_context=lambda *a, **kw: context)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    monkeypatch.setitem(sys.modules, 'playwright.sync_api', SimpleNamespace(
        sync_playwright=Playwright, Error=RuntimeError))
    sections = yh.collect_history(tmp_path / 'browser', '', channel='Requested Podcast')
    assert page.index == 2
    assert yh.normalize_sections(sections, 'Requested Podcast')[0]['video_id'] == 'ccccccccccc'


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
    assert snapshot['selection'] == 'latest'
    assert snapshot['channels'] == [yh.DEFAULT_CHANNEL]
    assert snapshot['title_keyword'] == 'Podcast'
    assert '가장 최근에 본' in digest


def test_stale_digest_rejected_and_long_message_bounded():
    with pytest.raises(yh.HistoryError):
        yh.render_digest({'date': '2026-10-02', 'videos': [video()]}, today='2026-10-03')
    digest = yh.render_digest({'date': '2026-10-03', 'videos': [
        {'title': 'a' * 160, 'url': 'https://www.youtube.com/watch?v=abcdefghijk'} for _ in range(100)]}, today='2026-10-03')
    assert len(digest) < 4000
    assert digest.count('https://www.youtube.com/watch?v=abcdefghijk') == 1


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
    assert (tmp_path / 'session.json').stat().st_mode & 0o777 == 0o600
    assert yh.load_saved_cookies(tmp_path / 'session.json')[0]['name'] == 'SID'
    assert json.loads((tmp_path / 'snapshot.json').read_text())['date'] == '2026-10-02'
    assert 'private-session' not in str(capsys.readouterr())


@pytest.mark.parametrize('stage, error, expected', [
    ('navigate', RuntimeError('net::ERR_ACCESS_DENIED secret-session-value'), 'YouTube 페이지 접속 실패 (ERR_ACCESS_DENIED)'),
    ('cookies', RuntimeError('Invalid cookie secret-session-value'), '쿠키 적용 실패 (브라우저 오류)'),
    ('bootstrap', TimeoutError('secret-session-value'), 'YouTube 페이지 초기화 실패 (시간 초과)'),
    ('secret-session-value', RuntimeError('net::ERR_SECRET_SESSION_VALUE'), '브라우저 처리 실패 (브라우저 오류)'),
])
def test_browser_diagnostics_show_only_safe_stage_and_known_codes(stage, error, expected):
    message = yh.describe_browser_error(stage, error)
    assert message.startswith(expected)
    assert 'secret-session-value' not in message
    assert 'ERR_SECRET_SESSION_VALUE' not in message


def test_saved_cookie_retry_needs_no_stdin(tmp_path, monkeypatch, capsys):
    browser_dir = tmp_path / 'browser'
    (browser_dir / 'Default').mkdir(parents=True)
    cookies = yh.parse_cookies(cookies_text('.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tprivate-session'))
    yh.save_json(tmp_path / 'session.json', {'version': 1, 'cookies': cookies})
    def refreshed(*args, **kwargs):
        assert kwargs['cookies'][0]['value'] == 'private-session'
        return {'synced_at': '2026-10-03T18:00:00-07:00', 'videos': []}
    class NoRead:
        def read(self, *args):
            pytest.fail('Saved-session retry must not read stdin.')
    monkeypatch.setattr(yh.sys, 'stdin', NoRead())
    monkeypatch.setattr(yh, 'refresh', refreshed)
    assert yh.main(['--data-dir', str(tmp_path), '--browser-dir', str(browser_dir),
                    'connect', '--saved-cookies']) == 0
    assert yh.is_connected(tmp_path, browser_dir)
    assert 'private-session' not in capsys.readouterr().out


def test_expired_saved_session_reports_safe_reconnect_error(tmp_path):
    yh.save_json(tmp_path / 'session.json', {'version': 1, 'cookies': [{
        'domain': '.youtube.com', 'path': '/', 'secure': True, 'expires': 1,
        'name': 'SID', 'value': 'expired-private-value',
    }]})
    with pytest.raises(yh.HistoryError) as error:
        yh.load_saved_cookies(tmp_path / 'session.json')
    assert 'expired-private-value' not in str(error.value)


@pytest.mark.parametrize('unix_time', [1800000000, 2000000000])
def test_chromium_expiry_is_converted_before_cookie_application(unix_time):
    chromium_time = (unix_time + 11644473600) * 1000000 + 123456
    text = cookies_text(f'.youtube.com\tTRUE\t/\tTRUE\t{chromium_time}\tSID\tprivate-session')
    assert yh.parse_cookies(text, now=1700000000)[0]['expires'] == unix_time


def test_expired_chromium_timestamp_is_not_treated_as_live():
    chromium_time = (1000 + 11644473600) * 1000000
    text = cookies_text(f'.youtube.com\tTRUE\t/\tTRUE\t{chromium_time}\tSID\tprivate-session')
    with pytest.raises(yh.HistoryError):
        yh.parse_cookies(text, now=1700000000)


def test_saved_native_chromium_expiry_is_normalized(tmp_path):
    yh.save_json(tmp_path / 'session.json', {'version': 1, 'cookies': [{
        'domain': '.youtube.com', 'path': '/', 'secure': True,
        'expires': (2000000000 + 11644473600) * 1000000,
        'name': 'SID', 'value': 'private-session',
    }]})
    assert yh.load_saved_cookies(tmp_path / 'session.json')[0]['expires'] == 2000000000
