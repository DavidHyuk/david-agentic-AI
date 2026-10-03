# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Verify Ubuntu desktop package selection and integrity before extraction."""
import hashlib
from io import BytesIO

import pytest
import install_youtube_history_desktop as installer


def test_package_index_selects_required_records_without_description_continuations():
    records = installer.package_records('Package: xvfb\nFilename: pool/x.deb\n'
                                       'SHA256: abc\nDescription: first\n continued: text\n\n'
                                       'Package: unrelated\nFilename: pool/other.deb\n')
    assert set(records) == {'xvfb'}
    assert 'continued' not in records['xvfb']


@pytest.mark.parametrize('valid', [True, False])
def test_downloaded_package_must_match_repository_checksum(monkeypatch, valid):
    payload = b'package fixture'
    monkeypatch.setattr(installer.urllib.request, 'urlopen', lambda *a, **kw: BytesIO(payload))
    record = {'Filename': 'pool/main/x/x11vnc.deb',
              'SHA256': hashlib.sha256(payload if valid else b'other').hexdigest()}
    if valid:
        assert installer.fetch_package(record) == ('x11vnc.deb', payload)
    else:
        with pytest.raises(ValueError, match='integrity'):
            installer.fetch_package(record)


def test_package_path_cannot_escape_official_repository(monkeypatch):
    monkeypatch.setattr(installer.urllib.request, 'urlopen',
                        lambda *a, **kw: pytest.fail('Invalid path must not be fetched.'))
    with pytest.raises(ValueError, match='path'):
        installer.fetch_package({'Filename': 'pool/../../secret', 'SHA256': ''})
