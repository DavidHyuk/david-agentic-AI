# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Validate laptop cookie exports without reading any real browser account."""
from http.cookiejar import Cookie

import pytest
import export_youtube_cookies as exporter
import youtube_history as history


def cookie(domain, name='SID', value='test-session', expires=None):
    return Cookie(0, name, value, None, False, domain, True, domain.startswith('.'),
                  '/', True, True, expires, expires is None, None, None, {}, False)


def test_export_import_roundtrip_filters_domains_and_uses_private_permissions(tmp_path):
    target = tmp_path / 'export.txt'
    count = exporter.save_youtube_cookies([
        cookie('.youtube.com'), cookie('.google.com', value='unrelated-private-value'),
        cookie('youtube.com.evil.example'), cookie('.youtube.com', name='OLD', expires=1),
    ], target)
    assert count == 1
    assert 'unrelated-private-value' not in target.read_text()
    assert target.stat().st_mode & 0o777 == 0o600
    assert history.parse_cookies(target.read_text())[0]['name'] == 'SID'


def test_unsigned_export_preserves_existing_file_and_removes_temporary(tmp_path):
    target = tmp_path / 'export.txt'
    target.write_text('preserved')
    with pytest.raises(ValueError):
        exporter.save_youtube_cookies([cookie('.youtube.com', name='PREF')], target)
    assert target.read_text() == 'preserved'
    assert list(tmp_path.iterdir()) == [target]


def test_export_normalizes_chromium_expiry_and_drops_expired_native_cookies(tmp_path):
    live = cookie('.youtube.com', expires=(2000000000 + 11644473600) * 1000000)
    expired = cookie('.youtube.com', name='OLD', expires=(1000 + 11644473600) * 1000000)
    target = tmp_path / 'export.txt'
    assert exporter.save_youtube_cookies([live, expired], target) == 1
    imported = history.parse_cookies(target.read_text())
    assert imported[0]['expires'] == 2000000000
    assert live.expires == (2000000000 + 11644473600) * 1000000
