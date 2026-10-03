#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Read the latest watched YouTube podcast for the existing English podcast feed.

Import YouTube-only Netscape cookies with ``connect --cookies-stdin`` over SSH
from the signed-in personal computer using the phone app’s account/channel.
A private Chromium data directory preserves that login; no password or browser session is printed. ``notify`` refreshes the
history and emits a deterministic Korean link digest for Hermes cron delivery.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

TZ = ZoneInfo('America/Los_Angeles')
DEFAULT_DATA_DIR = Path('/home/david/.hermes/data/youtube-history')
DEFAULT_BROWSER_DIR = DEFAULT_DATA_DIR / 'browser'
DEFAULT_BROWSER_CACHE = Path('/home/david/.hermes/venvs/youtube-history/browsers')
DEFAULT_CHANNEL = 'English Goal Podcast'
DEFAULT_CHANNELS = (DEFAULT_CHANNEL, 'Daily English Podcast')
HISTORY_URL = 'https://www.youtube.com/feed/history?hl=en&gl=US'

# Extract only visible history rows, never the whole page or account data.
HISTORY_SCRIPT = r"""() => {
  const sections = [...document.querySelectorAll('ytd-item-section-renderer')];
  return sections.map(section => ({
    heading: (section.querySelector('#header')?.innerText || '').trim(),
    videos: [...section.querySelectorAll('ytd-video-renderer, yt-lockup-view-model')].map(row => {
      const title = row.querySelector('a#video-title, a.ytLockupMetadataViewModelTitle, a.yt-lockup-metadata-view-model__title');
      const channel = row.querySelector('ytd-channel-name a, .ytLockupMetadataViewModelMetadata .ytContentMetadataViewModelMetadataText, .yt-lockup-metadata-view-model__metadata a');
      return {title: (title?.textContent || '').trim(), url: title?.href || '',
              channel: (channel?.textContent || '').trim()};
    })
  }));
}"""


class HistoryError(ValueError):
    """Safe-to-display history collection failure."""


def save_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def channel_key(value: str) -> str:
    return re.sub(r'[^a-z0-9]', '', value.lower())


def channel_names(channel: str | list[str] | tuple[str, ...]) -> list[str]:
    """Validate explicit channel names, keeping their display labels and order."""
    names = [channel] if isinstance(channel, str) else list(channel)
    if not names or any(not channel_key(name) for name in names):
        raise HistoryError('대상 채널 이름이 필요합니다.')
    return list(dict.fromkeys(name.strip() for name in names))


def normalize_sections(sections: list[dict], channel: str | list[str] | tuple[str, ...]) -> list[dict]:
    """Select the latest video matching a channel or the Podcast title keyword.

    Unknown page headings fail closed. History records indicate an appearance
    in watch history, not a completed listen or a measured viewing duration.
    """
    if not isinstance(sections, list) or not sections:
        raise HistoryError('시청 기록 페이지 구조를 확인할 수 없습니다. 연결을 확인해 주세요.')
    headings = [str(s.get('heading', '')).strip().lower() for s in sections]
    if not any(h in ('today', 'yesterday', '오늘', '어제') or
               re.search(r'\b20\d{2}\b|\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b', h)
               for h in headings):
        raise HistoryError('시청 기록 페이지 구조를 확인할 수 없습니다. 연결을 확인해 주세요.')
    allowed = {channel_key(name) for name in channel_names(channel)}
    for section in sections:
        for raw in section.get('videos', []):
            title = ' '.join(str(raw.get('title', '')).split())
            if not title:
                continue
            if (channel_key(str(raw.get('channel', ''))) not in allowed
                    and 'podcast' not in title.casefold()):
                continue
            url = urlsplit(str(raw.get('url', '')))
            video_id = parse_qs(url.query).get('v', [''])[0]
            if url.scheme != 'https' or url.hostname not in ('www.youtube.com', 'youtube.com') or url.path != '/watch':
                continue
            if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
                continue
            return [{'video_id': video_id, 'title': title[:160],
                     'channel': str(raw.get('channel', '')),
                     'history_heading': str(section.get('heading', '')).strip(),
                     'url': 'https://www.youtube.com/watch?v=' + video_id}]
    return []



def normalize_cookie_expiry(value: int) -> int:
    """Convert Chromium's 1601-epoch microseconds to Unix seconds when present."""
    value = int(value)
    if value >= 11644473600000000:
        value = value // 1000000 - 11644473600
    if value > 253402300799 or value < -1:
        raise ValueError('Unsupported cookie expiry format.')
    return value


def parse_cookies(text: str, *, now: float | None = None) -> list[dict]:
    """Read Netscape cookies, retaining live YouTube credentials only.

    Never include source lines or credential values in errors. Google and all
    unrelated domains are discarded even if a full-browser export was supplied.
    """
    now = time.time() if now is None else now
    if len(text) > 5_000_000 or not text.startswith(('# Netscape HTTP Cookie File', '# HTTP Cookie File')):
        raise HistoryError('Netscape 형식의 YouTube 쿠키 파일이 필요합니다.')
    cookies = []
    for raw in text.splitlines()[1:]:
        http_only = raw.startswith('#HttpOnly_')
        line = raw[len('#HttpOnly_'):] if http_only else raw
        if not line.strip() or (line.startswith('#') and not http_only):
            continue
        fields = line.split('\t')
        if len(fields) != 7:
            raise HistoryError('쿠키 파일 형식이 올바르지 않습니다. 맥북에서 다시 내보내 주세요.')
        domain, subdomains, path, secure, expiry, name, value = fields
        host = domain.lstrip('.').lower()
        if host != 'youtube.com' and not host.endswith('.youtube.com'):
            continue
        if subdomains not in ('TRUE', 'FALSE') or secure not in ('TRUE', 'FALSE') or not path.startswith('/'):
            raise HistoryError('YouTube 쿠키 형식이 올바르지 않습니다.')
        try:
            expires = normalize_cookie_expiry(int(expiry or 0))
        except ValueError as exc:
            raise HistoryError('YouTube 쿠키 유효기간이 올바르지 않습니다.') from exc
        if expires and expires <= now:
            continue
        if not name or not value or re.search(r'[\s\x00-\x1f\x7f]', name) or re.search(r'[\x00-\x1f\x7f]', value):
            raise HistoryError('YouTube 쿠키 형식이 올바르지 않습니다.')
        cookies.append({'name': name, 'value': value, 'domain': domain.lower(),
                        'path': path, 'secure': secure == 'TRUE', 'httpOnly': http_only,
                        'expires': expires if expires else -1})
    auth_names = {'SID', 'SAPISID', '__Secure-1PSID', '__Secure-3PSID'}
    if not any(cookie['name'] in auth_names for cookie in cookies):
        raise HistoryError('유효한 YouTube 로그인 쿠키가 없습니다. 맥북에서 같은 계정으로 로그인한 후 다시 내보내 주세요.')
    return cookies


def verified_browser_record(data_dir: Path, browser_dir: Path, filename: str) -> bool:
    """Distinguish verified login from a fully collected history connection."""
    path = data_dir / filename
    if not path.exists():
        return False
    connection = json.loads(path.read_text())
    return (connection.get('version') == 1 and bool(connection.get('verified_at'))
            and connection.get('browser_dir') == str(browser_dir.resolve())
            and (browser_dir / 'Default').is_dir())


def is_connected(data_dir: Path, browser_dir: Path) -> bool:
    return verified_browser_record(data_dir, browser_dir, 'connection.json')


def is_authenticated(data_dir: Path, browser_dir: Path) -> bool:
    return verified_browser_record(data_dir, browser_dir, 'authentication.json') or is_connected(data_dir, browser_dir)


def load_saved_cookies(path: Path) -> list[dict]:
    """Validate a private saved session without echoing any credential values."""
    try:
        document = json.loads(path.read_text())
        if document.get('version') != 1 or not isinstance(document.get('cookies'), list):
            raise ValueError('invalid session')
        rows = ['# Netscape HTTP Cookie File']
        for cookie in document['cookies']:
            domain = cookie['domain']
            prefix = '#HttpOnly_' if cookie.get('httpOnly') else ''
            expires = cookie.get('expires', -1)
            rows.append('\t'.join((prefix + domain,
                                    'TRUE' if domain.startswith('.') else 'FALSE',
                                    cookie['path'], 'TRUE' if cookie['secure'] else 'FALSE',
                                    str(int(expires)) if expires > 0 else '0',
                                    cookie['name'], cookie['value'])))
        return parse_cookies('\n'.join(rows) + '\n')
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise HistoryError('저장된 YouTube 세션이 없거나 유효하지 않습니다. 맥북의 쿠키를 SSH로 다시 전달해 주세요.') from exc


def describe_browser_error(stage: str, error: Exception) -> str:
    """Expose only fixed stages and whitelisted network codes, never raw errors."""
    stages = {'launch': '브라우저 실행', 'cookies': '쿠키 적용',
              'navigate': 'YouTube 페이지 접속', 'bootstrap': 'YouTube 페이지 초기화',
              'render': '시청 기록 표시', 'collect': '시청 기록 수집'}
    label = stages.get(stage, '브라우저 처리')
    allowed_codes = {'ERR_ACCESS_DENIED', 'ERR_NETWORK_ACCESS_DENIED',
                     'ERR_CONNECTION_RESET', 'ERR_CONNECTION_REFUSED',
                     'ERR_CONNECTION_CLOSED', 'ERR_TIMED_OUT',
                     'ERR_NAME_NOT_RESOLVED', 'ERR_INTERNET_DISCONNECTED',
                     'ERR_PROXY_CONNECTION_FAILED', 'ERR_TUNNEL_CONNECTION_FAILED',
                     'ERR_CERT_AUTHORITY_INVALID', 'ERR_CERT_DATE_INVALID',
                     'ERR_CERT_COMMON_NAME_INVALID', 'ERR_ABORTED',
                     'ERR_HTTP2_PROTOCOL_ERROR'}
    match = re.search(r'net::(ERR_[A-Z_]+)\b', str(error))
    if match and match.group(1) in allowed_codes:
        detail = match.group(1)
    elif type(error).__name__ == 'TimeoutError':
        detail = '시간 초과'
    else:
        detail = '브라우저 오류'
    return f'{label} 실패 ({detail}). 이전 기록은 보존됩니다.'


def collect_history(browser_dir: Path, executable: str, *, cookies: list[dict] | None = None,
                    session_path: Path | None = None,
                    channel: str | list[str] | tuple[str, ...] = DEFAULT_CHANNELS) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright, Error as PlaywrightError
    except ImportError as exc:
        raise HistoryError('Playwright가 없는 Python으로 실행됐습니다. /home/david/.hermes/venvs/youtube-history/bin/python으로 실행해 주세요.') from exc
    browser_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    browser_dir.chmod(0o700)
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(DEFAULT_BROWSER_CACHE))
    stage = 'launch'
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(browser_dir), executable_path=executable or None, headless=True,
                locale='en-US', timezone_id='America/Los_Angeles',
                args=['--no-first-run', '--no-default-browser-check'],
                ignore_default_args=['--enable-automation'],
            )
            try:
                stage = 'cookies'
                if cookies is None and session_path is not None and session_path.exists():
                    existing = context.cookies('https://www.youtube.com')
                    auth_names = {'SID', 'SAPISID', '__Secure-1PSID', '__Secure-3PSID'}
                    if not any(c['name'] in auth_names for c in existing):
                        cookies = load_saved_cookies(session_path)
                if cookies is not None:
                    context.clear_cookies()
                    context.add_cookies(cookies)
                page = context.pages[0] if context.pages else context.new_page()
                stage = 'navigate'
                response = page.goto(HISTORY_URL, wait_until='domcontentloaded', timeout=45_000)
                if response is not None and response.status >= 400:
                    raise HistoryError(f'YouTube 페이지 접속 실패 (HTTP {response.status}). 이전 기록은 보존됩니다.')
                stage = 'bootstrap'
                page.wait_for_function('() => window.ytInitialData && window.ytcfg', timeout=30_000)
                logged_in = page.evaluate("() => window.ytcfg.get('LOGGED_IN') === true")
                if not logged_in:
                    if session_path is not None:
                        (session_path.parent / 'authentication.json').unlink(missing_ok=True)
                        (session_path.parent / 'connection.json').unlink(missing_ok=True)
                    raise HistoryError('YouTube 로그인이 필요합니다. 맥북에서 쿠키를 다시 내보내고 SSH로 connect --cookies-stdin을 실행해 주세요.')
                if session_path is not None:
                    save_json(session_path, {'version': 1, 'cookies': context.cookies('https://www.youtube.com')})
                    save_json(session_path.parent / 'authentication.json', {
                        'version': 1, 'verified_at': datetime.now(TZ).isoformat(),
                        'browser_dir': str(browser_dir.resolve()),
                    })
                stage = 'render'
                page.wait_for_selector('ytd-item-section-renderer, ytd-message-renderer', timeout=20_000)
                stage = 'collect'
                def finish(sections):
                    if session_path is not None:
                        refreshed = context.cookies('https://www.youtube.com')
                        save_json(session_path, {'version': 1, 'cookies': refreshed})
                    return sections
                previous = None
                for _ in range(20):
                    sections = page.evaluate(HISTORY_SCRIPT)
                    if not sections:
                        message = page.locator('ytd-message-renderer').all_text_contents()
                        if any('this list has no videos' in text.lower() or 'watch history is empty' in text.lower() for text in message):
                            return finish([{'heading': 'Today', 'videos': []}])
                    # YouTube orders history newest first; older days remain eligible.
                    rows = [video for section in sections for video in section['videos']]
                    readable = sum(bool(str(video.get('title', '')).strip()) for video in rows)
                    if rows and readable <= len(rows) * 0.1:
                        raise HistoryError('YouTube 로그인은 확인됐지만 영상 제목을 읽지 못했습니다. 저장된 세션은 유지되며 쿠키 재전송은 필요하지 않습니다.')
                    if sections and normalize_sections(sections, channel):
                        return finish(sections)
                    count = sum(len(s['videos']) for s in sections)
                    if previous == count:
                        return finish(sections)
                    previous = count
                    page.evaluate('window.scrollTo(0, document.documentElement.scrollHeight)')
                    page.wait_for_timeout(1200)
                raise HistoryError('YouTube 로그인은 완료됐습니다. 시청 기록을 20회 검색했지만 조건에 맞는 팟캐스트를 찾지 못했습니다. 저장된 쿠키를 다시 보내지 않아도 됩니다.')
            finally:
                context.close()
    except HistoryError:
        raise
    except PlaywrightError as exc:
        raise HistoryError(describe_browser_error(stage, exc)) from exc


def refresh(data_dir: Path, browser_dir: Path, executable: str,
            channel: str | list[str] | tuple[str, ...],
            *, collector=collect_history, cookies=None, now=None) -> dict:
    supplied_now = now is not None
    now = now or datetime.now(TZ)
    before = now.astimezone(TZ).date().isoformat()
    sections = collector(browser_dir, executable, cookies=cookies,
                         session_path=data_dir / 'session.json', channel=channel)
    after = datetime.now(TZ).date().isoformat() if not supplied_now else before
    if after != before:
        raise HistoryError('수집 도중 날짜가 바뀌었습니다. 다음 실행에서 재시도합니다.')
    videos = normalize_sections(sections, channel)
    names = channel_names(channel)
    snapshot = {'version': 1, 'date': before, 'synced_at': now.isoformat(),
                'channel_filter': ', '.join(names), 'channels': names,
                'title_keyword': 'Podcast',
                'selection': 'latest', 'videos': videos}
    save_json(data_dir / 'snapshot.json', snapshot)
    return snapshot


def render_digest(snapshot: dict, *, today: str | None = None) -> str:
    today = today or datetime.now(TZ).date().isoformat()
    if snapshot.get('date') != today:
        raise HistoryError('오늘 새로 수집한 시청 기록이 아닙니다.')
    videos = snapshot.get('videos', [])
    if not videos:
        return '[SILENT]'
    video = videos[0]
    return '\n'.join(['🎧 가장 최근에 본 영어 팟캐스트', '',
                      video['title'][:160], video['url'], '',
                      'YouTube 시청 기록 기준입니다.'])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('YOUTUBE_HISTORY_DATA_DIR', str(DEFAULT_DATA_DIR))))
    parser.add_argument('--browser-dir', type=Path, default=Path(os.environ.get('YOUTUBE_HISTORY_BROWSER_DIR', str(DEFAULT_BROWSER_DIR))))
    parser.add_argument('--browser-executable', default=os.environ.get('YOUTUBE_HISTORY_BROWSER_EXECUTABLE', ''),
                        help='optional external browser; default is the installed Playwright headless shell')
    parser.add_argument('--channel', action='append',
                        help='watched channel name; repeat to override defaults; Podcast titles also match')
    parser.add_argument('command', choices=['connect', 'sync', 'notify', 'status'])
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--cookies-file', type=Path, help='private Netscape cookie export; no cookie values in arguments')
    source.add_argument('--saved-cookies', action='store_true', help='retry connecting with the owner-only saved session')
    source.add_argument('--cookies-stdin', action='store_true', help='read a YouTube cookie export through an SSH stdin pipe')
    args = parser.parse_args(argv)
    try:
        channels = channel_names(args.channel if args.channel is not None else DEFAULT_CHANNELS)
        if args.command != 'connect' and (args.cookies_file or args.cookies_stdin or args.saved_cookies):
            raise HistoryError('쿠키 입력 옵션은 connect 명령에만 사용할 수 있습니다.')
        if args.command == 'status':
            path = args.data_dir / 'snapshot.json'
            snapshot = json.loads(path.read_text()) if path.exists() else {}
            print(json.dumps({'connected': is_connected(args.data_dir, args.browser_dir),
                              'authenticated': is_authenticated(args.data_dir, args.browser_dir),
                              'session_saved': (args.data_dir / 'session.json').is_file(),
                              'browser_initialized': (args.browser_dir / 'Default' / 'Preferences').is_file(),
                              'date': snapshot.get('date'), 'synced_at': snapshot.get('synced_at'),
                              'video_count': len(snapshot.get('videos', []))}, ensure_ascii=False))
            return 0
        if args.command == 'notify' and not is_authenticated(args.data_dir, args.browser_dir):
            print('[SILENT]')
            return 0
        if args.command == 'sync' and not is_authenticated(args.data_dir, args.browser_dir):
            raise HistoryError('맥북에서 내보낸 쿠키로 connect --cookies-stdin을 먼저 실행해 주세요.')
        cookies = None
        if args.command == 'connect':
            if not (args.cookies_file or args.cookies_stdin or args.saved_cookies):
                raise HistoryError('서버 GUI는 필요 없습니다. connect --cookies-stdin 또는 --cookies-file로 맥북의 YouTube 쿠키를 전달해 주세요.')
            if args.saved_cookies:
                cookies = load_saved_cookies(args.data_dir / 'session.json')
            else:
                text = args.cookies_file.read_text() if args.cookies_file else sys.stdin.read(5_000_001)
                cookies = parse_cookies(text)
        args.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (args.data_dir / '.lock').open('w') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise HistoryError('YouTube 계정 연결 또는 기록 수집이 이미 진행 중입니다. 완료 후 재시도해 주세요.') from exc
            if args.command == 'connect':
                (args.data_dir / 'connection.json').unlink(missing_ok=True)
                (args.data_dir / 'authentication.json').unlink(missing_ok=True)
                save_json(args.data_dir / 'session.json', {'version': 1, 'cookies': cookies})
            snapshot = refresh(args.data_dir, args.browser_dir, args.browser_executable,
                               channels, cookies=cookies)
            save_json(args.data_dir / 'connection.json', {
                'version': 1, 'verified_at': snapshot['synced_at'],
                'browser_dir': str(args.browser_dir.resolve()),
            })
        if args.command == 'notify':
            print(render_digest(snapshot))
        else:
            print(json.dumps(snapshot, ensure_ascii=False))
        return 0
    except HistoryError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, ValueError, EOFError):
        # Raw Playwright/OS exceptions may contain page/account data or paths.
        print('YouTube 기록 처리 중 오류가 발생했습니다. 저장된 세션은 유지됩니다. 서버에서 connect --saved-cookies로 확인해 주세요.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
