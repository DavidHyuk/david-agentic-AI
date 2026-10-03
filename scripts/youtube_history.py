#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Read today's YouTube watch history for the existing English podcast feed.

Sign in once with ``connect`` in a desktop terminal using the same YouTube
account/channel as the phone app. A private Chromium data directory preserves
that login; no password or browser session is printed. ``notify`` refreshes the
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
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

TZ = ZoneInfo('America/Los_Angeles')
DEFAULT_DATA_DIR = Path('/home/david/.hermes/data/youtube-history')
DEFAULT_BROWSER_DIR = Path('/home/david/snap/chromium/common/hermes-youtube-history')
DEFAULT_CHANNEL = 'English Goal Podcast'
HISTORY_URL = 'https://www.youtube.com/feed/history?hl=en&gl=US'

# Extract only visible history rows, never the whole page or account data.
HISTORY_SCRIPT = r"""() => {
  const sections = [...document.querySelectorAll('ytd-item-section-renderer')];
  return sections.map(section => ({
    heading: (section.querySelector('#header')?.innerText || '').trim(),
    videos: [...section.querySelectorAll('ytd-video-renderer, yt-lockup-view-model')].map(row => {
      const title = row.querySelector('a#video-title, a.yt-lockup-metadata-view-model__title');
      const channel = row.querySelector('ytd-channel-name a, .yt-lockup-metadata-view-model__metadata a');
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


def normalize_sections(sections: list[dict], channel: str) -> list[dict]:
    """Select today's deduplicated canonical links from an explicit channel.

    Unknown page headings fail closed. History records indicate an appearance
    in watch history, not a completed listen or a measured viewing duration.
    """
    if not isinstance(sections, list) or not sections:
        raise HistoryError('시청 기록 페이지 구조를 확인할 수 없습니다. 연결을 확인해 주세요.')
    headings = [str(s.get('heading', '')).strip().lower() for s in sections]
    if not any(h in ('today', 'yesterday', '오늘', '어제') or
               re.search(r'\b20\d{2}\b|\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b', h)
               for h in headings):
        raise HistoryError('시청 날짜를 확인할 수 없습니다. 과거 영상을 오늘 기록으로 보내지 않습니다.')
    videos, seen = [], set()
    for section, heading in zip(sections, headings):
        if heading not in ('today', '오늘'):
            continue
        for raw in section.get('videos', []):
            if channel_key(str(raw.get('channel', ''))) != channel_key(channel):
                continue
            url = urlsplit(str(raw.get('url', '')))
            video_id = parse_qs(url.query).get('v', [''])[0]
            if url.scheme != 'https' or url.hostname not in ('www.youtube.com', 'youtube.com') or url.path != '/watch':
                continue
            if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id) or video_id in seen:
                continue
            title = ' '.join(str(raw.get('title', '')).split())
            if not title:
                continue
            seen.add(video_id)
            videos.append({'video_id': video_id, 'title': title[:160],
                           'channel': str(raw['channel']),
                           'url': 'https://www.youtube.com/watch?v=' + video_id})
    return videos


def collect_history(browser_dir: Path, executable: str, *, headed: bool = False) -> list[dict]:
    if headed and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        raise HistoryError('최초 연결은 데스크톱 터미널에서 connect를 실행해 직접 로그인해 주세요.')
    try:
        from playwright.sync_api import sync_playwright, Error as PlaywrightError
    except ImportError as exc:
        raise HistoryError('Playwright가 필요합니다: python3 -m pip install -r requirements.txt') from exc
    browser_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    browser_dir.chmod(0o700)
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(browser_dir), executable_path=executable, headless=not headed,
                locale='en-US', timezone_id='America/Los_Angeles',
                args=['--no-first-run', '--no-default-browser-check'],
                ignore_default_args=['--enable-automation'],
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(HISTORY_URL, wait_until='domcontentloaded', timeout=45_000)
                if headed:
                    print('휴대폰과 같은 YouTube 계정/채널로 로그인한 뒤 이 터미널에서 Enter를 누르세요.', file=sys.stderr, flush=True)
                    input()
                    page.goto(HISTORY_URL, wait_until='domcontentloaded', timeout=45_000)
                page.wait_for_function('() => window.ytInitialData && window.ytcfg', timeout=30_000)
                logged_in = page.evaluate("() => window.ytcfg.get('LOGGED_IN') === true")
                if not logged_in:
                    raise HistoryError('YouTube 로그인이 필요합니다. 데스크톱 터미널에서 youtube_history.py connect를 실행해 주세요.')
                page.wait_for_selector('ytd-item-section-renderer, ytd-message-renderer', timeout=20_000)
                previous = None
                for _ in range(20):
                    sections = page.evaluate(HISTORY_SCRIPT)
                    if not sections:
                        message = page.locator('ytd-message-renderer').all_text_contents()
                        if any('this list has no videos' in text.lower() or 'watch history is empty' in text.lower() for text in message):
                            return [{'heading': 'Today', 'videos': []}]
                    today_count = sum(len(s['videos']) for s in sections if s['heading'].strip().lower() in ('today', '오늘'))
                    # Stop once the visible history reaches a prior day.
                    if any(s['heading'] and s['heading'].strip().lower() not in ('today', '오늘') for s in sections):
                        return sections
                    if previous == today_count:
                        return sections
                    previous = today_count
                    page.evaluate('window.scrollTo(0, document.documentElement.scrollHeight)')
                    page.wait_for_timeout(1200)
                raise HistoryError('오늘 기록이 수집 한도를 넘었습니다. 일부 기록만 보내지 않고 다음 실행에서 재시도합니다.')
            finally:
                context.close()
    except HistoryError:
        raise
    except PlaywrightError as exc:
        raise HistoryError('YouTube 기록을 읽지 못했습니다. 브라우저 연결/로그인을 확인해 주세요. 이전 기록은 보존됩니다.') from exc


def refresh(data_dir: Path, browser_dir: Path, executable: str, channel: str,
            *, collector=collect_history, headed=False, now=None) -> dict:
    supplied_now = now is not None
    now = now or datetime.now(TZ)
    before = now.astimezone(TZ).date().isoformat()
    sections = collector(browser_dir, executable, headed=headed)
    after = datetime.now(TZ).date().isoformat() if not supplied_now else before
    if after != before:
        raise HistoryError('수집 도중 날짜가 바뀌었습니다. 다음 실행에서 재시도합니다.')
    videos = normalize_sections(sections, channel)
    snapshot = {'version': 1, 'date': before, 'synced_at': now.isoformat(),
                'channel_filter': channel, 'videos': videos}
    save_json(data_dir / 'snapshot.json', snapshot)
    return snapshot


def render_digest(snapshot: dict, *, today: str | None = None) -> str:
    today = today or datetime.now(TZ).date().isoformat()
    if snapshot.get('date') != today:
        raise HistoryError('오늘 날짜의 시청 기록이 아닙니다.')
    videos = snapshot.get('videos', [])
    if not videos:
        return '[SILENT]'
    lines = ['🎧 오늘 본 영어 팟캐스트', today, '']
    included = 0
    for video in videos:
        item = f"{included + 1}. {video['title']}\n{video['url']}\n"
        if len('\n'.join(lines)) + len(item) > 3300:
            break
        lines.append(item)
        included += 1
    if included < len(videos):
        lines.append(f'총 {len(videos)}편 중 최근 {included}편입니다.')
    lines.append('YouTube 시청 기록 기준이며, 끝까지 시청했는지는 확인하지 않습니다.')
    return '\n'.join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('YOUTUBE_HISTORY_DATA_DIR', str(DEFAULT_DATA_DIR))))
    parser.add_argument('--browser-dir', type=Path, default=Path(os.environ.get('YOUTUBE_HISTORY_BROWSER_DIR', str(DEFAULT_BROWSER_DIR))))
    parser.add_argument('--browser-executable', default=os.environ.get('HERMES_CHROMIUM_EXECUTABLE', '/snap/bin/chromium'))
    parser.add_argument('--channel', default=DEFAULT_CHANNEL)
    parser.add_argument('command', choices=['connect', 'sync', 'notify', 'status'])
    args = parser.parse_args(argv)
    try:
        if not channel_key(args.channel):
            raise HistoryError('대상 채널 이름이 필요합니다.')
        if args.command == 'status':
            path = args.data_dir / 'snapshot.json'
            snapshot = json.loads(path.read_text()) if path.exists() else {}
            print(json.dumps({'browser_initialized': (args.browser_dir / 'Default' / 'Preferences').is_file(),
                              'date': snapshot.get('date'), 'synced_at': snapshot.get('synced_at'),
                              'video_count': len(snapshot.get('videos', []))}, ensure_ascii=False))
            return 0
        args.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (args.data_dir / '.lock').open('w') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise HistoryError('YouTube 계정 연결 또는 기록 수집이 이미 진행 중입니다. 완료 후 재시도해 주세요.') from exc
            snapshot = refresh(args.data_dir, args.browser_dir, args.browser_executable,
                               args.channel, headed=args.command == 'connect')
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
        print('YouTube 시청 기록을 가져오지 못했습니다. 같은 계정으로 youtube_history.py connect를 실행해 연결을 확인해 주세요.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
