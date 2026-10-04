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
from urllib.parse import urlsplit, urljoin
import zipfile

DEFAULT_DATA = Path.home() / '.hermes/data/chatgpt'
DEFAULT_RUNTIME = Path.home() / '.hermes/venvs/youtube-history'
WEB_PORT, VNC_PORT, CDP_PORT = 18781, 15902, 19324
MAX_EXPORT_BYTES = 512 * 1024 * 1024
CONVERSATION_PATH = re.compile(r'^/(?:c/|g/[^/]+/c/)([0-9a-fA-F-]{36})/?$')
PROJECT_ID = re.compile(r'^g-p-[0-9a-f]{32}$')


class ArchiveError(ValueError):
    """An explicitly safe error message suitable for CLI output."""


class ExportVerificationRequired(ArchiveError):
    """The account owner must complete ChatGPT's export verification."""


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
    sidebar = load_json(data_dir / 'browser-index.json')
    result['sidebar_conversation_count'] = len(sidebar.get('conversations', []))
    result['sidebar_captured_at'] = sidebar.get('captured_at')
    result['sidebar_complete'] = False
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
    words = query.casefold().split()
    if not database.is_file():
        sidebar = load_json(data_dir / 'browser-index.json')
        if not sidebar:
            raise ArchiveError('No ChatGPT export or browser conversation index is available yet.')
        results = []
        for row in sidebar_conversations(sidebar.get('conversations', [])):
            cached = load_json(data_dir / 'browser-chats' / (row['id'] + '.json'))
            text = row['title'] + '\n' + '\n'.join(message['text'] for message in cached.get('messages', []))
            if all(word in text.casefold() for word in words):
                results.append({**row, 'source': 'visible_sidebar', 'content_available': bool(cached)})
                if len(results) >= limit:
                    break
        return results
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
        index = sidebar_conversations(load_json(data_dir / 'browser-index.json').get('conversations', []))
        row = next((row for row in index if row['id'] == identifier), None)
        if row:
            cached = load_json(data_dir / 'browser-chats' / (row['id'] + '.json'))
            if cached:
                return cached
            raise ArchiveError('Only the title/link is indexed; use read-browser <id> to retrieve visible text.')
        raise ArchiveError('No ChatGPT export has been imported yet.')
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
        row = connection.execute('SELECT title,messages FROM conversations WHERE id=?', (identifier,)).fetchone()
    if row is None:
        raise ArchiveError('Conversation not found.')
    return {'id': identifier, 'title': row[0], 'messages': json.loads(row[1])}


def sidebar_conversations(rows: list[dict]) -> list[dict]:
    """Accept only titled conversation links on ChatGPT, excluding projects/assets."""
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('url'), str):
            continue
        parsed = urlsplit(urljoin('https://chatgpt.com/', row['url']))
        match = CONVERSATION_PATH.fullmatch(parsed.path)
        title = row.get('title')
        if (parsed.scheme != 'https' or parsed.hostname != 'chatgpt.com' or parsed.username
                or parsed.password or not match or not isinstance(title, str) or not title.strip()):
            continue
        identifier = match.group(1).lower()
        if identifier in seen:
            continue
        seen.add(identifier)
        result.append({'id': identifier, 'title': title.strip(),
                       'url': 'https://chatgpt.com' + parsed.path})
    return result


def sync_sidebar(data_dir: Path, max_scrolls: int) -> dict:
    """Collect rendered sidebar links with bounded scrolling, without requesting export."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{CDP_PORT}')
        context = browser.contexts[0]
        candidates = [page for page in context.pages if urlsplit(page.url).hostname == 'chatgpt.com']
        if not candidates:
            raise ArchiveError('Open the signed-in ChatGPT home page in the login browser first.')
        page = candidates[-1]
        if not is_authenticated(page):
            raise ArchiveError('The browser does not show a signed-in ChatGPT home page.')
        previous = load_json(data_dir / 'browser-index.json')
        collected = {}
        stalled = 0
        for unused in range(max_scrolls + 1):
            if not is_authenticated(page):
                raise ArchiveError('ChatGPT login became unavailable; previous index retained.')
            links = page.locator('a[href*="/c/"]')
            rows = sidebar_conversations(links.evaluate_all(
                'nodes => nodes.map(e => ({url:e.href,title:e.innerText.trim()}))'))
            before = len(collected)
            collected.update({row['id']: row for row in rows})
            stalled = stalled + 1 if len(collected) == before else 0
            if links.count() == 0 or stalled >= 3:
                break
            moved = links.first.evaluate('''e => {
                for(let p=e.parentElement;p && p!==document.body;p=p.parentElement){
                    if(p.scrollHeight>p.clientHeight && /auto|scroll/.test(getComputedStyle(p).overflowY)){
                        const before=p.scrollTop;
                        p.scrollTop=Math.min(p.scrollTop+p.clientHeight*0.8,p.scrollHeight);
                        return p.scrollTop!==before;
                    }
                }
                return false;
            }''')
            if not moved and stalled >= 2:
                break
            page.wait_for_timeout(750)
        if not collected:
            raise ArchiveError('No conversation links were visible; previous index retained.')
        # Merge prior observations: the sidebar is not an authoritative full export.
        merged = {row['id']: row for row in sidebar_conversations(previous.get('conversations', []))}
        merged.update(collected)
        snapshot = {'version': 1, 'captured_at': now(), 'source': 'visible_sidebar',
                    'complete': False, 'conversations': list(merged.values())}
        save_json(data_dir / 'browser-index.json', snapshot)
        return {'sidebar_conversation_count': len(merged), 'observed_this_run': len(collected),
                'captured_at': snapshot['captured_at'], 'complete': False}


def project_conversations(rows: list[dict], project_id: str) -> list[dict]:
    """Keep only observed links that belong to the exact selected project."""
    if not PROJECT_ID.fullmatch(project_id):
        raise ArchiveError('Invalid project identifier.')
    prefix = f'/g/{project_id}/c/'
    return [row for row in sidebar_conversations(rows) if urlsplit(row['url']).path.startswith(prefix)]


def sync_project(data_dir: Path, project_name: str, max_scrolls: int) -> dict:
    """Index the selected project's main chat list, excluding global sidebar links."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{CDP_PORT}')
        context = browser.contexts[0]
        candidates = [p for p in context.pages if urlsplit(p.url).hostname == 'chatgpt.com']
        if not candidates:
            raise ArchiveError('Open the signed-in ChatGPT login browser first.')
        page = candidates[-1]
        projects = page.locator('[data-app-action-sidebar-project-row]')
        entries = projects.evaluate_all('''nodes => nodes.map(e => ({
            name:e.getAttribute('data-app-action-sidebar-project-label'),
            id:e.getAttribute('data-app-action-sidebar-project-id')}))''')
        matching = [row for row in entries if row['name'] == project_name]
        if len(matching) != 1 or not PROJECT_ID.fullmatch(matching[0]['id'] or ''):
            raise ArchiveError('The exact project name was not found in the signed-in sidebar.')
        project_id = matching[0]['id']
        url = f'https://chatgpt.com/g/{project_id}/project'
        tab = context.new_page()
        try:
            tab.goto(url, wait_until='domcontentloaded', timeout=45_000)
            tab.locator('main').get_by_role('button', name=project_name, exact=True).wait_for(timeout=30_000)
            links = tab.locator('main a[href*="/c/"]')
            links.first.wait_for(timeout=30_000)
            collected, stalled = {}, 0
            for unused in range(max_scrolls + 1):
                if tab.url.rstrip('/') != url or not is_authenticated(tab):
                    raise ArchiveError('The selected project page is no longer available; previous index retained.')
                rows = project_conversations(links.evaluate_all('''nodes => nodes.map(e => ({
                    url:e.href,title:e.innerText.trim().split('\\n')[0]}))'''), project_id)
                before = len(collected)
                collected.update({row['id']: row for row in rows})
                stalled = stalled + 1 if len(collected) == before else 0
                moved = links.first.evaluate('''e => {
                    for(let p=e.parentElement;p && p!==document.body;p=p.parentElement){
                        if(p.scrollHeight>p.clientHeight && /auto|scroll/.test(getComputedStyle(p).overflowY)){
                            const before=p.scrollTop;
                            p.scrollTop+=p.clientHeight*0.8;
                            return p.scrollTop!==before;
                        }
                    }
                    return false;
                }''')
                if not moved and stalled >= 3:
                    break
                tab.wait_for_timeout(750)
            if not collected:
                raise ArchiveError('No conversations were observed in the selected project.')
            previous = load_json(data_dir / 'browser-project.json')
            merged = {}
            if previous.get('id') == project_id:
                merged.update({row['id']: row for row in project_conversations(previous.get('conversations', []), project_id)})
            merged.update(collected)
            project = {'version': 1, 'id': project_id, 'name': project_name, 'url': url,
                       'captured_at': now(), 'source': 'visible_project', 'complete': False,
                       'conversations': list(merged.values())}
            save_json(data_dir / 'browser-project.json', project)
            index = load_json(data_dir / 'browser-index.json')
            all_rows = {row['id']: row for row in sidebar_conversations(index.get('conversations', []))}
            all_rows.update(merged)
            save_json(data_dir / 'browser-index.json', {**index, 'version': 1, 'complete': False,
                'source': 'visible_sidebar', 'conversations': list(all_rows.values())})
            return {'project_id': project_id, 'project_name': project_name,
                    'project_conversation_count': len(merged), 'complete': False}
        finally:
            tab.close()


def collect_browser_messages(page, max_scrolls: int) -> tuple[list[dict], bool]:
    """Observe rendered messages across a bounded scroll; retain stable message order."""
    modern = ('main [data-user-message-bubble="true"]:visible,'
              'main [data-markdown-text-style="assistant-message"]:visible')
    legacy = ('main [data-message-author-role="user"]:visible,'
              'main [data-message-author-role="assistant"]:visible')
    scroll = page.locator('main .thread-scroll-container').first
    if max_scrolls and scroll.count():
        scroll.evaluate('e=>{e.scrollTop=getComputedStyle(e).flexDirection==="column-reverse"?-e.scrollHeight:0}')
        page.wait_for_timeout(750)
    observed, boundary = {}, False
    for step in range(max_scrolls + 1):
        messages = page.locator(modern)
        if not messages.count():
            messages = page.locator(legacy)
        rows = messages.evaluate_all('''nodes => nodes.map((e,i) => {
            const role=e.hasAttribute('data-user-message-bubble')?'user':
                e.getAttribute('data-message-author-role')||'assistant';
            const turn=e.closest('[data-content-search-turn-key]')?.getAttribute('data-content-search-turn-key');
            const ordinal=turn?.match(/fallback-turn-(\\d+)/);
            const holder=e.closest('[data-chatgpt-selection-message-id],[data-chatgpt-search-message-ids],[data-message-id]');
            const key=holder?.getAttribute('data-chatgpt-selection-message-id')||
                holder?.getAttribute('data-chatgpt-search-message-ids')||holder?.getAttribute('data-message-id');
            return {role,text:e.innerText.trim(),key:role+':'+(key||turn||i),
                    ordinal:ordinal?Number(ordinal[1]):null};
        }).filter(e=>e.text)''')
        for row in rows:
            previous = observed.get(row['key'])
            if previous is None or len(row['text']) >= len(previous['text']):
                observed[row['key']] = row
        if step == max_scrolls or not scroll.count():
            break
        moved = scroll.evaluate('''e=>{
            const before=e.scrollTop;
            e.scrollTop+=e.clientHeight*0.8;
            return Math.abs(e.scrollTop-before)>1;
        }''')
        page.wait_for_timeout(400)
        if not moved:
            boundary = True
            break
    rows = list(observed.values())
    if rows and all(row['ordinal'] is not None for row in rows):
        rows.sort(key=lambda row: (row['ordinal'], row['role'] != 'user'))
    return [{'role': row['role'], 'text': row['text']} for row in rows], boundary


def read_browser_conversation(data_dir: Path, identifier: str, max_scrolls: int = 0) -> dict:
    """Read one explicitly selected indexed chat through the visible web UI."""
    from playwright.sync_api import sync_playwright
    sidebar = load_json(data_dir / 'browser-index.json')
    rows = sidebar_conversations(sidebar.get('conversations', []))
    row = next((row for row in rows if row['id'] == identifier), None)
    if row is None:
        raise ArchiveError('Conversation is not in the observed browser index.')
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{CDP_PORT}')
        context = browser.contexts[0]
        page = context.new_page()
        try:
            page.goto(row['url'], wait_until='domcontentloaded', timeout=45_000)
            modern_selector = ('main [data-user-message-bubble="true"]:visible,'
                               'main [data-markdown-text-style="assistant-message"]:visible')
            legacy_selector = ('main [data-message-author-role="user"]:visible,'
                               'main [data-message-author-role="assistant"]:visible')
            page.locator(modern_selector + ',' + legacy_selector).first.wait_for(timeout=30_000)
            # Avoid claiming all historical turns have rendered on a long chat.
            page.wait_for_timeout(1500)
            current = sidebar_conversations([{'url': page.url, 'title': row['title']}])
            if not current or current[0]['id'] != row['id']:
                raise ArchiveError('The selected conversation was not opened; no chat content was saved.')
            texts, boundary = collect_browser_messages(page, max_scrolls)
            current = sidebar_conversations([{'url': page.url, 'title': row['title']}])
            if not current or current[0]['id'] != row['id']:
                raise ArchiveError('Conversation changed while reading; previous cache retained.')
            if not texts:
                raise ArchiveError('No visible conversation text was found.')
            result = {**row, 'source': 'visible_browser', 'captured_at': now(),
                      'complete': False, 'scroll_boundary_reached': boundary, 'messages': texts}
            safe_filename = row['id'] + '.json'
            save_json(data_dir / 'browser-chats' / safe_filename, result)
            return result
        finally:
            page.close()


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


def read_project(data_dir: Path, max_scrolls: int, refresh: bool = False) -> dict:
    """Cache only selected project chats, skipping already completed observations."""
    project = load_json(data_dir / 'browser-project.json')
    rows = project_conversations(project.get('conversations', []), project.get('id', ''))
    if not rows or len(rows) != len(project.get('conversations', [])):
        raise ArchiveError('The selected project manifest has invalid conversation links.')
    fetched, skipped, failures = 0, 0, []
    for row in rows:
        cached = load_json(data_dir / 'browser-chats' / (row['id'] + '.json'))
        if (not refresh and cached.get('id') == row['id'] and cached.get('url') == row['url']
                and cached.get('source') == 'visible_browser' and cached.get('messages')
                and cached.get('scroll_boundary_reached') is True):
            skipped += 1
            continue
        try:
            read_browser_conversation(data_dir, row['id'], max_scrolls)
            fetched += 1
        except Exception as exc:
            failures.append({'id': row['id'], 'error': str(exc) if isinstance(exc, ArchiveError) else type(exc).__name__})
    return {'project_name': project.get('name'), 'fetched': fetched, 'skipped': skipped,
            'failures': failures, 'complete': False}


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
        # Responsive layouts can retain a hidden copy of the same control.
        locator = page.locator(selector + ':visible')
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
    click_named(page, ('button',), r'^(Export|Export data|Export ChatGPT account data|내보내기|데이터 내보내기)$')
    page.wait_for_timeout(500)
    click_named(page, ('button',), r'^(Confirm export|Confirm|내보내기 확인|내보내기 확정|확인)$')
    page.wait_for_timeout(500)
    if urlsplit(page.url).hostname == 'auth.openai.com':
        raise ExportVerificationRequired('Complete the device or email verification in the visible browser.')
    try:
        page.get_by_text(re.compile(r'export (requested|has been requested)|successfully requested|내보내기.*요청', re.I)).first.wait_for(timeout=10_000)
    except Exception:
        if urlsplit(page.url).hostname == 'auth.openai.com':
            raise ExportVerificationRequired('Complete the device or email verification in the visible browser.') from None
        raise
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
                        except ExportVerificationRequired:
                            state['export_status'] = 'awaiting_verification'
                            print('ChatGPT requires device or email verification before confirming the export request.', flush=True)
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
    sidebar = commands.add_parser('sync-sidebar', help='Read visible conversation links without requesting export.')
    sidebar.add_argument('--max-scrolls', type=int, default=40)
    reader = commands.add_parser('read-browser', help='Read one indexed chat from the signed-in browser.')
    reader.add_argument('id')
    reader.add_argument('--max-scrolls', type=int, default=0)
    project = commands.add_parser('sync-project', help='Index only the selected project chat list.')
    project.add_argument('name')
    project.add_argument('--max-scrolls', type=int, default=40)
    project_reader = commands.add_parser('read-project', help='Cache selected project chats; skip prior observations.')
    project_reader.add_argument('--max-scrolls', type=int, default=400)
    project_reader.add_argument('--refresh', action='store_true')
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
        elif args.command == 'sync-sidebar':
            if not 0 <= args.max_scrolls <= 100:
                parser.error('--max-scrolls must be between 0 and 100')
            with locked(args.data_dir, '.browser-read.lock'):
                result = sync_sidebar(args.data_dir, args.max_scrolls)
        elif args.command == 'read-browser':
            if not 0 <= args.max_scrolls <= 400:
                parser.error('--max-scrolls must be between 0 and 400')
            with locked(args.data_dir, '.browser-read.lock'):
                result = read_browser_conversation(args.data_dir, args.id, args.max_scrolls)
        elif args.command == 'sync-project':
            if not 0 <= args.max_scrolls <= 100:
                parser.error('--max-scrolls must be between 0 and 100')
            with locked(args.data_dir, '.browser-read.lock'):
                result = sync_project(args.data_dir, args.name, args.max_scrolls)
        elif args.command == 'read-project':
            if not 0 <= args.max_scrolls <= 400:
                parser.error('--max-scrolls must be between 0 and 400')
            with locked(args.data_dir, '.browser-read.lock'):
                result = read_project(args.data_dir, args.max_scrolls, args.refresh)
        else:
            result = archive_status(args.data_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if args.command == 'read-project' and result['failures'] else 0
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
