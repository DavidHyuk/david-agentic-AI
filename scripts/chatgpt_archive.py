#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Connect a private ChatGPT browser, request an export, and search local chats.

Credentials are entered directly through SSH-forwarded noVNC. The existing
YouTube desktop runtime supplies binaries, but its profile and cookies are never
used. No account passwords, session tokens, or export links are printed.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
import zipfile

DEFAULT_DATA = Path.home() / '.hermes/data/chatgpt'
DEFAULT_RUNTIME = Path.home() / '.hermes/venvs/youtube-history'
WEB_PORT, VNC_PORT, CDP_PORT = 18781, 15902, 19324
MAX_EXPORT_BYTES = 512 * 1024 * 1024


class ArchiveError(ValueError):
    """An explicitly safe error message suitable for CLI output."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def save_json(path: Path, value) -> None:
    private_directory(path.parent)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.is_file() else {}


@contextmanager
def locked(data_dir: Path, name: str):
    private_directory(data_dir)
    with (data_dir / name).open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ArchiveError('Another ChatGPT operation is running.') from None
        yield


def conversation_messages(conversation: dict) -> list[dict]:
    """Read only the selected branch, preserving message roles and text parts."""
    mapping = conversation.get('mapping')
    if not isinstance(mapping, dict):
        raise ArchiveError('Conversation mapping is missing.')
    node_id = conversation.get('current_node')
    if node_id is None:
        # A nonbranching export can omit current_node. Never guess between leaves.
        parents = {node.get('parent') for node in mapping.values() if isinstance(node, dict)}
        leaves = [key for key in mapping if key not in parents]
        if len(leaves) != 1:
            raise ArchiveError('Conversation has no unambiguous selected branch.')
        node_id = leaves[0]
    nodes, seen = [], set()
    while node_id is not None:
        if not isinstance(node_id, str) or node_id in seen or node_id not in mapping:
            raise ArchiveError('Conversation branch is invalid.')
        seen.add(node_id)
        node = mapping[node_id]
        if not isinstance(node, dict):
            raise ArchiveError('Conversation node is invalid.')
        message = node.get('message')
        if message:
            role = (message.get('author') or {}).get('role')
            content = message.get('content') or {}
            # Exclude system/tool messages, hidden reasoning, and nontext assets.
            if role in ('user', 'assistant') and content.get('content_type') in ('text', 'multimodal_text'):
                parts = [part for part in content.get('parts', []) if isinstance(part, str)]
                text = '\n'.join(parts).strip()
                if (text and message.get('channel') != 'analysis'
                        and not (message.get('metadata') or {}).get('is_visually_hidden_from_conversation')):
                    nodes.append({'role': role, 'text': text, 'timestamp': message.get('create_time')})
        node_id = node.get('parent')
    return list(reversed(nodes))


def read_export(path: Path) -> list[dict]:
    """Read JSON directly or one conversations.json member without extracting ZIP."""
    if path.stat().st_size > MAX_EXPORT_BYTES:
        raise ArchiveError('Export exceeds the 512 MiB limit.')
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            members = [member for member in archive.infolist()
                       if member.filename == 'conversations.json']
            if len(members) != 1 or members[0].file_size > MAX_EXPORT_BYTES:
                raise ArchiveError('ZIP must contain exactly one bounded conversations.json.')
            with archive.open(members[0]) as stream:
                payload = stream.read(MAX_EXPORT_BYTES + 1)
    else:
        payload = path.read_bytes()
    if len(payload) > MAX_EXPORT_BYTES:
        raise ArchiveError('Conversation JSON exceeds the size limit.')
    conversations = json.loads(payload)
    if not isinstance(conversations, list):
        raise ArchiveError('Conversation export must be a list.')
    return conversations


def import_export(path: Path, data_dir: Path) -> dict:
    """Atomically replace the local snapshot only after validating the whole export."""
    conversations = read_export(path)
    rows, ids = [], set()
    for conversation in conversations:
        if not isinstance(conversation, dict):
            raise ArchiveError('Invalid conversation record.')
        identifier = conversation.get('id') or conversation.get('conversation_id')
        if not isinstance(identifier, str) or not identifier or identifier in ids:
            raise ArchiveError('Missing or duplicate conversation ID.')
        ids.add(identifier)
        messages = conversation_messages(conversation)
        title = conversation.get('title') or 'Untitled'
        if not isinstance(title, str):
            raise ArchiveError('Invalid conversation title.')
        rows.append((identifier, title, json.dumps(messages, ensure_ascii=False),
                     '\n'.join(message['text'] for message in messages)))
    with locked(data_dir, '.import.lock'):
        descriptor, filename = tempfile.mkstemp(dir=data_dir, suffix='.db')
        os.close(descriptor)
        temporary = Path(filename)
        try:
            with sqlite3.connect(temporary) as connection:
                connection.execute('CREATE TABLE conversations(id TEXT PRIMARY KEY, title TEXT, messages TEXT, text TEXT)')
                connection.executemany('INSERT INTO conversations VALUES(?,?,?,?)', rows)
                report = {'version': 1, 'imported_at': now(), 'conversation_count': len(rows),
                          'message_count': sum(len(json.loads(row[2])) for row in rows)}
                connection.execute('CREATE TABLE metadata(value TEXT)')
                connection.execute('INSERT INTO metadata VALUES(?)', (json.dumps(report),))
            temporary.replace(data_dir / 'archive.db')
        finally:
            temporary.unlink(missing_ok=True)
    return report


def archive_status(data_dir: Path) -> dict:
    result = {'browser_status': 'not_started', 'conversation_count': 0, 'message_count': 0}
    browser = load_json(data_dir / 'browser-status.json')
    for key in ('browser_status', 'authenticated_at', 'export_status', 'export_requested_at'):
        if key in browser:
            result[key] = browser[key]
    database = data_dir / 'archive.db'
    if database.is_file():
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
            result.update(json.loads(connection.execute('SELECT value FROM metadata').fetchone()[0]))
    return result


def import_downloads(data_dir: Path, seen: set[tuple]) -> dict | None:
    """Import completed ZIP downloads once; leave partial or unrelated files alone."""
    report = None
    for path in sorted((data_dir / 'downloads').glob('*.zip')):
        stat = path.stat()
        signature = (path.name, stat.st_size, stat.st_mtime_ns)
        if signature in seen or Path(str(path) + '.crdownload').exists():
            continue
        if not zipfile.is_zipfile(path):
            continue
        try:
            report = import_export(path, data_dir)
            path.chmod(0o600)
        except (ValueError, zipfile.BadZipFile):
            # An unrelated ZIP is never extracted or treated as conversation data.
            pass
        seen.add(signature)
    return report


def search_archive(data_dir: Path, query: str, limit: int) -> list[dict]:
    database = data_dir / 'archive.db'
    if not database.is_file():
        raise ArchiveError('No ChatGPT export has been imported yet.')
    words = query.casefold().split()
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
        results = []
        for identifier, title, text in connection.execute('SELECT id,title,text FROM conversations ORDER BY rowid DESC'):
            if all(word in (title + '\n' + text).casefold() for word in words):
                results.append({'id': identifier, 'title': title})
                if len(results) >= limit:
                    break
        return results


def show_conversation(data_dir: Path, identifier: str) -> dict:
    database = data_dir / 'archive.db'
    if not database.is_file():
        raise ArchiveError('No ChatGPT export has been imported yet.')
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
        row = connection.execute('SELECT title,messages FROM conversations WHERE id=?', (identifier,)).fetchone()
    if row is None:
        raise ArchiveError('Conversation not found.')
    return {'id': identifier, 'title': row[0], 'messages': json.loads(row[1])}


def desktop_commands(runtime: Path, data_dir: Path, executable: Path) -> list[list[str]]:
    desktop, authority = runtime / 'desktop', data_dir / 'login.xauth'
    return [
        [str(desktop / 'usr/bin/Xvfb'), ':98', '-screen', '0', '1366x900x24', '-nolisten', 'tcp', '-auth', str(authority)],
        [str(desktop / 'usr/bin/x11vnc'), '-display', ':98', '-auth', str(authority), '-listen', '127.0.0.1',
         '-rfbport', str(VNC_PORT), '-forever', '-shared', '-nopw', '-noxdamage', '-quiet'],
        [str(runtime / 'bin/python'), '-m', 'websockify', '--web', str(desktop / 'usr/share/novnc'),
         f'127.0.0.1:{WEB_PORT}', f'127.0.0.1:{VNC_PORT}'],
        [str(executable), '--no-first-run', '--no-default-browser-check', '--password-store=basic',
         '--disable-dev-shm-usage', '--disable-gpu', '--no-sandbox',
         '--user-data-dir=' + str(data_dir / 'browser'), '--remote-debugging-address=127.0.0.1',
         '--remote-debugging-port=' + str(CDP_PORT), '--window-size=1366,900', 'https://chatgpt.com/'],
    ]


def stop_process(process) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def wait_port(port: int, processes: list, timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(process.poll() is not None for process in processes):
            raise RuntimeError('Desktop component stopped.')
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.3):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError('Desktop component not ready.')


def profile_control(page):
    for selector in ('[data-testid="accounts-profile-button"]', '[data-testid="user-menu-button"]',
                     'button[aria-label="Open profile menu"]'):
        locator = page.locator(selector)
        if locator.count() == 1 and locator.is_visible():
            return locator
    return None


def is_authenticated(page) -> bool:
    return urlsplit(page.url).hostname == 'chatgpt.com' and profile_control(page) is not None


def click_named(page, roles: tuple[str, ...], pattern: str) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        for role in roles:
            locator = page.get_by_role(role, name=re.compile(pattern, re.I))
            if locator.count() == 1 and locator.is_visible():
                locator.click(timeout=5000)
                return
        page.wait_for_timeout(200)
    raise ArchiveError('ChatGPT settings control was not found; use the visible browser to continue.')


def request_export(page) -> str:
    """Use visible account settings; require a success notice before claiming sent."""
    if not is_authenticated(page):
        raise ArchiveError('Sign in directly in the browser first.')
    profile_control(page).click()
    click_named(page, ('menuitem', 'button'), r'^(Settings|설정)$')
    page.wait_for_timeout(1200)
    click_named(page, ('tab', 'button'), r'^(Data controls|데이터 제어|데이터 관리)$')
    page.wait_for_timeout(700)
    click_named(page, ('button',), r'^(Export|Export data|내보내기|데이터 내보내기)$')
    page.wait_for_timeout(500)
    click_named(page, ('button',), r'^(Confirm export|Confirm|내보내기 확인|내보내기 확정|확인)$')
    page.get_by_text(re.compile(r'export (requested|has been requested)|successfully requested|내보내기.*요청', re.I)).first.wait_for(timeout=10_000)
    return now()


def run_browser(runtime: Path, data_dir: Path, timeout: int, export: bool) -> None:
    from playwright.sync_api import sync_playwright
    executables = sorted((runtime / 'browsers').glob('chromium-*/chrome-linux*/chrome'))
    if not executables:
        raise ArchiveError('Install bootstrap/install_youtube_history_desktop.py first.')
    private_directory(data_dir / 'browser')
    private_directory(data_dir / 'downloads')
    env = os.environ.copy()
    env.update(DISPLAY=':98', LIBGL_ALWAYS_SOFTWARE='1', XAUTHORITY=str(data_dir / 'login.xauth'))
    libraries = sorted((runtime / 'desktop/usr/lib').glob('*-linux-gnu'))
    env['LD_LIBRARY_PATH'] = ':'.join(map(str, libraries)) + ':' + os.environ.get('LD_LIBRARY_PATH', '')
    for port in (VNC_PORT, WEB_PORT, CDP_PORT):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
    authority = data_dir / 'login.xauth'
    authority.touch(mode=0o600)
    authority.chmod(0o600)
    state = load_json(data_dir / 'browser-status.json')
    state.update(browser_status='starting', export_status='not_requested' if export else state.get('export_status', 'not_requested'))
    with ExitStack() as cleanup:
        cleanup.callback(authority.unlink, missing_ok=True)
        subprocess.run(['xauth', '-f', str(authority), 'add', ':98', 'MIT-MAGIC-COOKIE-1', secrets.token_hex(16)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes = []
        for index, command in enumerate(desktop_commands(runtime, data_dir, executables[-1])):
            process = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processes.append(process)
            cleanup.callback(stop_process, process)
            if index == 0:
                time.sleep(1)
            else:
                wait_port((VNC_PORT, WEB_PORT, CDP_PORT)[index - 1], processes)
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{CDP_PORT}')
            # Disconnect before terminating Chromium gracefully so the profile persists.
            context = browser.contexts[0]
            page = context.pages[0]
            session = context.new_cdp_session(page)
            session.send('Browser.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': str(data_dir / 'downloads')})
            state.update(browser_status='awaiting_login', started_at=now())
            save_json(data_dir / 'browser-status.json', state)
            print(f'ChatGPT browser ready: SSH-forward localhost:{WEB_PORT}; open /vnc.html.', flush=True)
            deadline, attempted = time.monotonic() + timeout, False
            seen_downloads = set()
            while time.monotonic() < deadline:
                if any(process.poll() is not None for process in processes):
                    raise RuntimeError('Desktop component stopped.')
                if not context.pages:
                    break
                page.wait_for_timeout(1500)
                report = import_downloads(data_dir, seen_downloads)
                if report:
                    print(f"Imported {report['conversation_count']} conversations into the private local archive.", flush=True)
                for candidate in context.pages:
                    try:
                        authenticated = is_authenticated(candidate)
                    except Exception:
                        continue
                    if authenticated and state['browser_status'] != 'authenticated':
                        state.update(browser_status='authenticated', authenticated_at=now())
                        save_json(data_dir / 'browser-status.json', state)
                        print('ChatGPT login confirmed. Session remains in the private browser profile.', flush=True)
                    if authenticated and export and not attempted:
                        attempted = True
                        # Persist the attempt before clicking. Never auto retry ambiguous submission.
                        state['export_status'] = 'requesting'
                        save_json(data_dir / 'browser-status.json', state)
                        try:
                            state['export_requested_at'] = request_export(candidate)
                            state['export_status'] = 'requested'
                            print('Export request confirmed. Waiting for the email/SMS download link.', flush=True)
                        except Exception:
                            state['export_status'] = 'needs_browser_review'
                            print('Export confirmation could not be verified. Continue in the visible browser.', flush=True)
                        save_json(data_dir / 'browser-status.json', state)
            state['browser_status'] = 'closed'
            save_json(data_dir / 'browser-status.json', state)


def validate_download_url(url: str) -> None:
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname not in ('chatgpt.com', 'data-export.openai.com')
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ArchiveError('Use an HTTPS ChatGPT or data-export.openai.com download link.')


def download_export(data_dir: Path, url: str) -> dict:
    """Download a user-provided official export link in the connected browser."""
    validate_download_url(url)
    from playwright.sync_api import sync_playwright, Error
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{CDP_PORT}')
        context = browser.contexts[0]
        page = context.new_page()
        try:
            with page.expect_download(timeout=60_000) as pending:
                try:
                    page.goto(url, wait_until='domcontentloaded', timeout=45_000)
                except Error:
                    # Chromium navigation aborts when a response becomes a download.
                    pass
            private_directory(data_dir / 'downloads')
            target = data_dir / 'downloads' / 'chatgpt-export.zip'
            pending.value.save_as(target)
            target.chmod(0o600)
            return import_export(target, data_dir)
        finally:
            page.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=DEFAULT_DATA)
    commands = parser.add_subparsers(dest='command', required=True)
    login = commands.add_parser('login')
    login.add_argument('--runtime-dir', type=Path, default=DEFAULT_RUNTIME)
    login.add_argument('--timeout', type=int, default=1800)
    login.add_argument('--request-export', action='store_true')
    commands.add_parser('status')
    importer = commands.add_parser('import')
    importer.add_argument('--file', type=Path, required=True)
    search = commands.add_parser('search')
    search.add_argument('query', nargs='?', default='')
    search.add_argument('--limit', type=int, default=20)
    show = commands.add_parser('show')
    show.add_argument('id')
    commands.add_parser('download', help='Read the private export URL from stdin; requires an open login browser.')
    args = parser.parse_args(argv)
    os.umask(0o077)
    def interrupted(*unused):
        raise KeyboardInterrupt
    try:
        if args.command == 'login':
            if not 60 <= args.timeout <= 3600:
                parser.error('--timeout must be between 60 and 3600 seconds')
            signal.signal(signal.SIGTERM, interrupted)
            with locked(args.data_dir, '.browser.lock'):
                try:
                    run_browser(args.runtime_dir, args.data_dir, args.timeout, args.request_export)
                finally:
                    state = load_json(args.data_dir / 'browser-status.json')
                    state['browser_status'] = 'closed'
                    save_json(args.data_dir / 'browser-status.json', state)
            return 0
        if args.command == 'import':
            result = import_export(args.file, args.data_dir)
        elif args.command == 'download':
            result = download_export(args.data_dir, sys.stdin.readline().strip())
        elif args.command == 'search':
            if not 1 <= args.limit <= 100:
                parser.error('--limit must be between 1 and 100')
            result = search_archive(args.data_dir, args.query, args.limit)
        elif args.command == 'show':
            result = show_conversation(args.data_dir, args.id)
        else:
            result = archive_status(args.data_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        print('ChatGPT browser stopped; private session retained.')
        return 130
    except Exception as exc:
        # Browser exceptions can contain signed URLs, page content or account details.
        message = str(exc) if isinstance(exc, ArchiveError) else type(exc).__name__
        print('ChatGPT operation failed: ' + message, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
