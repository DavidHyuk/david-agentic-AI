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
    assert yh.main(['--data-dir', str(tmp_path), 'notify']) == 1
    output = capsys.readouterr()
    assert output.out == ''
    assert 'login required' in output.err
