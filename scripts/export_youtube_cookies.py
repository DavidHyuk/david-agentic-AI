#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Export only YouTube cookies on the personal laptop for SSH server linking.

Run on the MacBook, never on the DGX: python3 export_youtube_cookies.py.
Requires yt-dlp in this Python environment. The output is an owner-only Netscape
cookie file; no values are logged. Chrome is the default; Firefox is supported.
"""
from __future__ import annotations

import argparse
from copy import copy
from http.cookiejar import MozillaCookieJar
import os
from pathlib import Path
import sys
import tempfile


class QuietLogger:
    """Suppress browser extraction diagnostics that might contain private data."""
    def debug(self, *args, **kwargs):
        pass

    info = warning = error = debug



def normalize_cookie_expiry(value: int) -> int:
    """Convert Chromium's 1601-epoch microseconds to Unix seconds when present."""
    value = int(value)
    if value >= 11644473600000000:
        value = value // 1000000 - 11644473600
    if value > 253402300799 or value < -1:
        raise ValueError('Unsupported cookie expiry format.')
    return value


def save_youtube_cookies(cookies, target: Path) -> int:
    """Atomically save live YouTube cookies, excluding every unrelated domain."""
    target = target.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.youtube-cookies-', dir=target.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        jar = MozillaCookieJar(str(temporary))
        for cookie in cookies:
            host = cookie.domain.lstrip('.').lower()
            if host != 'youtube.com' and not host.endswith('.youtube.com'):
                continue
            normalized = copy(cookie)
            if normalized.expires is not None:
                normalized.expires = normalize_cookie_expiry(normalized.expires)
            if not normalized.is_expired():
                jar.set_cookie(normalized)
        if not any(c.name in {'SID', 'SAPISID', '__Secure-1PSID', '__Secure-3PSID'} for c in jar):
            raise ValueError('No signed-in YouTube cookies found.')
        jar.save(ignore_discard=True, ignore_expires=False)
        temporary.chmod(0o600)
        temporary.replace(target)
        return len(jar)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', choices=['chrome', 'firefox', 'edge', 'brave'], default='chrome')
    parser.add_argument('--profile', help='optional browser profile name or directory')
    parser.add_argument('--output', type=Path, default=Path.home() / 'youtube-cookies.txt')
    args = parser.parse_args(argv)
    try:
        from yt_dlp.cookies import extract_cookies_from_browser
        cookies = extract_cookies_from_browser(args.browser, args.profile, logger=QuietLogger())
        count = save_youtube_cookies(cookies, args.output)
        print(f'Saved {count} YouTube cookies to {args.output.expanduser()}; transfer through SSH, not chat.')
        return 0
    except ImportError:
        print('Install yt-dlp in this Python environment first.', file=sys.stderr)
    except Exception:
        print('Could not export signed-in YouTube cookies. Sign in to YouTube using the phone account; verify browser/profile access.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
