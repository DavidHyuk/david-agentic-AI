#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Link a LeetCode browser session and maintain a private, read-only snapshot.

LeetCode does not publish a personal-history API.  This standalone helper uses
the account's ``LEETCODE_SESSION`` cookie only for read-only GraphQL requests;
it never submits code, changes profile data, or stores a password.  The session
is entered through a hidden terminal prompt (or standard input), not a command
argument, and is written with owner-only permissions.

Usage:
  python3 leetcode_sync.py connect --username <leetcode-handle>
  python3 leetcode_sync.py sync
  python3 leetcode_sync.py status
  python3 leetcode_sync.py disconnect
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import getpass
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_URL = 'https://leetcode.com/graphql/'
USER_AGENT = 'david-agentic-ai/leetcode-sync (personal read-only coach)'
USERNAME_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
MAX_HISTORY = 100
DEFAULT_CDP_URL = 'http://127.0.0.1:19222'
DEFAULT_CHROMIUM_EXECUTABLE = '/snap/bin/chromium'

USER_STATUS_QUERY = '''query userStatus { userStatus { username } }'''
HISTORY_QUERY = '''query history($username: String!, $limit: Int!) {
  matchedUser(username: $username) {
    submitStatsGlobal { acSubmissionNum { difficulty count submissions } }
  }
  recentAcSubmissionList(username: $username, limit: $limit) { title titleSlug timestamp }
}'''


class LeetCodeSyncError(ValueError):
    """A safe-to-display connection, response, or local-state error."""


def default_home() -> Path:
    return Path(os.environ.get('HERMES_HOME', '~/.hermes')).expanduser()


def default_session_path(home: Path | None = None) -> Path:
    return (home or default_home()) / 'data/interview/leetcode_session.json'


def default_snapshot_path(home: Path | None = None) -> Path:
    return (home or default_home()) / 'data/interview/leetcode_history.json'


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def validate_username(username: str) -> str:
    value = (username or '').strip()
    if not USERNAME_RE.fullmatch(value):
        raise LeetCodeSyncError('LeetCode username must contain 1–64 letters, digits, _ or - only.')
    return value


def validate_session(session: str) -> str:
    value = (session or '').strip()
    if len(value) < 20 or any(char.isspace() for char in value):
        raise LeetCodeSyncError('LEETCODE_SESSION is missing or malformed.')
    return value


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise LeetCodeSyncError(f'Cannot read {path.name}; preserve it for recovery.') from exc


def save_private_json(path: Path, value: dict) -> None:
    """Atomically write private session or history data with owner-only access."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def load_connection(path: Path) -> dict:
    data = read_json(path)
    if not isinstance(data, dict) or data.get('version') != 1:
        raise LeetCodeSyncError('No valid LeetCode session is linked. Run connect first.')
    return {
        'username': validate_username(str(data.get('username', ''))),
        'session': validate_session(str(data.get('session', ''))),
        'csrf_token': str(data.get('csrf_token', '')).strip(),
        'linked_at': str(data.get('linked_at', '')),
    }


def graphql(query: str, variables: dict, connection: dict, timeout: int = 20) -> dict:
    """Make one authenticated, read-only GraphQL request without logging secrets."""
    cookies = [f"LEETCODE_SESSION={connection['session']}"]
    csrf_token = connection.get('csrf_token', '')
    if csrf_token:
        cookies.append(f'csrftoken={csrf_token}')
    headers = {
        'Content-Type': 'application/json', 'Accept': 'application/json',
        'User-Agent': USER_AGENT, 'Origin': 'https://leetcode.com',
        'Referer': 'https://leetcode.com/', 'Cookie': '; '.join(cookies),
    }
    if csrf_token:
        headers['x-csrftoken'] = csrf_token
    payload = json.dumps({'query': query, 'variables': variables}).encode()
    request = Request(API_URL, data=payload, headers=headers, method='POST')
    try:
        with urlopen(request, timeout=timeout) as response:
            document = json.loads(response.read().decode())
    except (HTTPError, URLError, OSError, json.JSONDecodeError) as exc:
        raise LeetCodeSyncError('LeetCode could not be reached; the saved history was left unchanged.') from exc
    if not isinstance(document, dict) or document.get('errors') or not isinstance(document.get('data'), dict):
        raise LeetCodeSyncError('LeetCode rejected the session or returned an unexpected response.')
    return document['data']


def verify_connection(connection: dict) -> str:
    data = graphql(USER_STATUS_QUERY, {}, connection)
    status = data.get('userStatus') or {}
    username = status.get('username') if isinstance(status, dict) else None
    if not isinstance(username, str) or not username:
        raise LeetCodeSyncError('LeetCode rejected the session. Log in again and relink a fresh session.')
    if username.lower() != connection['username'].lower():
        raise LeetCodeSyncError('The session belongs to a different LeetCode username.')
    return username


def _timestamp(value: object) -> str | None:
    try:
        return datetime.fromtimestamp(int(str(value)), timezone.utc).isoformat(timespec='seconds')
    except (TypeError, ValueError, OverflowError):
        return None


def normalize_history(data: dict, username: str) -> dict:
    user = data.get('matchedUser')
    if not isinstance(user, dict):
        raise LeetCodeSyncError('LeetCode did not return history for this username.')
    totals = {'All': 0, 'Easy': 0, 'Medium': 0, 'Hard': 0}
    stats = ((user.get('submitStatsGlobal') or {}).get('acSubmissionNum') or [])
    for row in stats:
        if isinstance(row, dict) and row.get('difficulty') in totals and isinstance(row.get('count'), int):
            totals[row['difficulty']] = row['count']
    recent = []
    for row in data.get('recentAcSubmissionList') or []:
        if not isinstance(row, dict):
            continue
        title, slug = row.get('title'), row.get('titleSlug')
        if not isinstance(title, str) or not isinstance(slug, str):
            continue
        recent.append({'title': title, 'slug': slug, 'accepted_at': _timestamp(row.get('timestamp'))})
    return {
        'version': 1, 'username': username, 'synced_at': utc_now(),
        'total_solved': totals['All'],
        'solved_by_difficulty': {key.lower(): totals[key] for key in ('Easy', 'Medium', 'Hard')},
        'recent_accepted': recent,
    }


def sync(connection_path: Path, snapshot_path: Path, limit: int = MAX_HISTORY) -> dict:
    if not 1 <= limit <= MAX_HISTORY:
        raise LeetCodeSyncError(f'History limit must be between 1 and {MAX_HISTORY}.')
    connection = load_connection(connection_path)
    data = graphql(HISTORY_QUERY, {'username': connection['username'], 'limit': limit}, connection)
    snapshot = normalize_history(data, connection['username'])
    save_private_json(snapshot_path, snapshot)
    return snapshot


def public_status(connection_path: Path, snapshot_path: Path) -> dict:
    linked = None
    try:
        connection = load_connection(connection_path)
        linked = {'username': connection['username'], 'linked_at': connection['linked_at']}
    except LeetCodeSyncError:
        pass
    snapshot = read_json(snapshot_path, {}) or {}
    return {'linked': linked, 'snapshot': {
        key: snapshot.get(key) for key in ('username', 'synced_at', 'total_solved', 'solved_by_difficulty')
    } if isinstance(snapshot, dict) and snapshot else None}


def read_session_from_terminal(stdin: bool) -> str:
    if stdin:
        return validate_session(sys.stdin.read())
    supplied = os.environ.get('LEETCODE_SESSION')
    if supplied:
        return validate_session(supplied)
    if not sys.stdin.isatty():
        raise LeetCodeSyncError('Set LEETCODE_SESSION or pass --stdin when no terminal is attached.')
    return validate_session(getpass.getpass('Paste LEETCODE_SESSION (input hidden): '))


def _cookie_value(cookies: list[dict], name: str) -> str:
    for cookie in cookies:
        if cookie.get('name') == name and isinstance(cookie.get('value'), str):
            return cookie['value']
    return ''


def login_failure_reason(page_text: str) -> str | None:
    """Turn known public login-page messages into an actionable safe error."""
    text = ' '.join((page_text or '').lower().split())
    if any(phrase in text for phrase in (
            'cloudflare', 'just a moment', 'checking your browser', '보안 확인 수행 중')):
        return ('Cloudflare blocked the headless browser before the LeetCode login form. '
                'Use a normal browser to sign in, then use connect; this helper will not bypass it.')
    if any(phrase in text for phrase in (
            'incorrect password', 'incorrect username', 'invalid password',
            'invalid username', 'invalid credentials', 'wrong password',
            'username or password is incorrect')):
        return 'LeetCode rejected the login ID or password. Check both and try again.'
    if any(phrase in text for phrase in (
            'captcha', 'verify you are human', 'security check', 'verification challenge')):
        return 'LeetCode requires CAPTCHA verification. Complete it in a normal browser, then use connect.'
    if any(phrase in text for phrase in (
            'two-factor', '2fa', 'verification code', 'one-time password')):
        return 'LeetCode requires MFA verification. Complete it in a normal browser, then use connect.'
    return None


def login_with_browser(cdp_url: str, username: str, login: str, password: str) -> dict:
    """Use the existing local headless Chromium only to obtain a fresh session.

    Credentials remain in memory for this function's lifetime. CAPTCHA, MFA, and
    changed login forms deliberately fail closed rather than attempting a bypass.
    """
    try:
        from playwright.sync_api import Error as PlaywrightError, sync_playwright
    except ImportError as exc:
        raise LeetCodeSyncError(
            'Playwright is not installed. Run python3 -m pip install -r requirements.txt.'
        ) from exc
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(cdp_url, timeout=15_000)
            try:
                if not browser.contexts:
                    raise LeetCodeSyncError('The local Chromium browser has no usable context.')
                context = browser.contexts[0]
                existing = _cookie_value(context.cookies('https://leetcode.com'), 'LEETCODE_SESSION')
                if existing:
                    candidate = {'username': username, 'session': existing, 'csrf_token': '', 'linked_at': ''}
                    verify_connection(candidate)
                    return {'session': existing, 'csrf_token': _cookie_value(
                        context.cookies('https://leetcode.com'), 'csrftoken')}
                page = context.new_page()
                try:
                    page.goto('https://leetcode.com/accounts/login/', wait_until='domcontentloaded', timeout=20_000)
                    login_field = page.locator('input[name="login"], #id_login, input[type="email"]').first
                    password_field = page.locator('input[name="password"], #id_password, input[type="password"]').first
                    if login_field.count() != 1 or password_field.count() != 1:
                        reason = login_failure_reason(page.locator('body').inner_text(timeout=1_000))
                        if reason:
                            raise LeetCodeSyncError(reason)
                        raise LeetCodeSyncError(
                            'LeetCode login form was not available. Complete browser verification, then use connect.'
                        )
                    login_field.fill(login)
                    password_field.fill(password)
                    submit = page.locator('button[type="submit"], input[type="submit"]').first
                    if submit.count() != 1:
                        raise LeetCodeSyncError('LeetCode login submit control was not found; use connect instead.')
                    submit.click()
                    deadline = time.monotonic() + 25
                    while time.monotonic() < deadline:
                        cookies = context.cookies('https://leetcode.com')
                        session = _cookie_value(cookies, 'LEETCODE_SESSION')
                        if session:
                            candidate = {'username': username, 'session': session, 'csrf_token': '', 'linked_at': ''}
                            verify_connection(candidate)
                            return {'session': session, 'csrf_token': _cookie_value(cookies, 'csrftoken')}
                        reason = login_failure_reason(page.locator('body').inner_text(timeout=1_000))
                        if reason:
                            raise LeetCodeSyncError(reason)
                        page.wait_for_timeout(250)
                    raise LeetCodeSyncError(
                        'LeetCode did not issue a session. The login form may have changed or require browser verification; use connect.'
                    )
                finally:
                    page.close()
            finally:
                browser.close()
    except LeetCodeSyncError:
        raise
    except PlaywrightError as exc:
        raise LeetCodeSyncError('Could not use the local headless Chromium; run browser/setup_browser.sh --check.') from exc


def login_in_headed_browser(username: str, executable: str, timeout_seconds: int,
                            profile_parent: Path) -> dict:
    """Open a temporary local GUI browser for user-completed verification.

    The user, not automation, enters credentials and completes Cloudflare/MFA.
    The temporary Chromium profile is deleted after extracting the session.
    """
    if timeout_seconds < 30 or timeout_seconds > 900:
        raise LeetCodeSyncError('Headed login timeout must be between 30 and 900 seconds.')
    if not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        raise LeetCodeSyncError(
            'Headed login requires a local graphical display. Run it in a desktop terminal or use connect.'
        )
    browser_path = Path(executable).expanduser()
    if not browser_path.is_file() or not os.access(browser_path, os.X_OK):
        raise LeetCodeSyncError(f'Chromium executable is unavailable: {browser_path}')
    try:
        from playwright.sync_api import Error as PlaywrightError, sync_playwright
    except ImportError as exc:
        raise LeetCodeSyncError(
            'Playwright is not installed. Run python3 -m pip install -r requirements.txt.'
        ) from exc
    profile_parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    profile_parent.chmod(0o700)
    try:
        with tempfile.TemporaryDirectory(prefix='leetcode-login-', dir=profile_parent) as profile:
            os.chmod(profile, 0o700)
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    profile, executable_path=str(browser_path), headless=False,
                    args=['--no-first-run', '--no-default-browser-check'],
                )
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    page.goto('https://leetcode.com/accounts/login/', wait_until='domcontentloaded', timeout=20_000)
                    print('Complete LeetCode sign-in and any browser verification in the opened window.', flush=True)
                    deadline = time.monotonic() + timeout_seconds
                    while time.monotonic() < deadline:
                        cookies = context.cookies('https://leetcode.com')
                        session = _cookie_value(cookies, 'LEETCODE_SESSION')
                        if session:
                            candidate = {'username': username, 'session': session, 'csrf_token': '', 'linked_at': ''}
                            verify_connection(candidate)
                            return {'session': session, 'csrf_token': _cookie_value(cookies, 'csrftoken')}
                        page.wait_for_timeout(500)
                    raise LeetCodeSyncError('Timed out waiting for a LeetCode session; no credentials were saved.')
                finally:
                    context.close()
    except LeetCodeSyncError:
        raise
    except PlaywrightError as exc:
        raise LeetCodeSyncError('Could not open local Chromium; verify the graphical desktop and browser path.') from exc


def parse_args(argv=None) -> argparse.Namespace:
    home = default_home()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-file', type=Path, default=default_session_path(home))
    parser.add_argument('--snapshot-file', type=Path, default=default_snapshot_path(home))
    sub = parser.add_subparsers(dest='command', required=True)
    connect = sub.add_parser('connect', help='verify and store a LeetCode browser session')
    connect.add_argument('--username', required=True)
    connect.add_argument('--stdin', action='store_true', help='read LEETCODE_SESSION from standard input')
    login = sub.add_parser('login', help='sign in through local headless Chromium; passwords are never stored')
    login.add_argument('--username', required=True)
    login.add_argument('--cdp-url', default=os.environ.get('HERMES_BROWSER_CDP_URL', DEFAULT_CDP_URL))
    login.add_argument('--headed', action='store_true',
                       help='open a temporary local GUI Chromium for manual Cloudflare/MFA completion')
    login.add_argument('--browser-executable', default=os.environ.get(
        'HERMES_CHROMIUM_EXECUTABLE', DEFAULT_CHROMIUM_EXECUTABLE))
    login.add_argument('--timeout-seconds', type=int, default=300)
    syncing = sub.add_parser('sync', help='refresh the read-only history snapshot')
    syncing.add_argument('--limit', type=int, default=MAX_HISTORY)
    sub.add_parser('status', help='show connection and snapshot metadata without secrets')
    sub.add_parser('disconnect', help='remove only the saved session; retain history')
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    session_path, snapshot_path = args.session_file.expanduser(), args.snapshot_file.expanduser()
    lock_path = snapshot_path.parent / '.leetcode-sync.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with lock_path.open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if args.command == 'connect':
                connection = {'version': 1, 'username': validate_username(args.username),
                              'session': read_session_from_terminal(args.stdin),
                              'csrf_token': os.environ.get('LEETCODE_CSRF_TOKEN', '').strip(),
                              'linked_at': utc_now()}
                verified_username = verify_connection(connection)
                connection['username'] = verified_username
                save_private_json(session_path, connection)
                output = {'linked': True, 'username': verified_username,
                          'session_file': str(session_path), 'next': 'Run sync to fetch history.'}
            elif args.command == 'login':
                username = validate_username(args.username)
                if args.headed:
                    credentials = login_in_headed_browser(
                        username, args.browser_executable, args.timeout_seconds, session_path.parent)
                else:
                    if not sys.stdin.isatty():
                        raise LeetCodeSyncError('The login command requires an interactive terminal.')
                    login = input('LeetCode email or username: ').strip()
                    if not login:
                        raise LeetCodeSyncError('LeetCode email or username is required.')
                    password = getpass.getpass('LeetCode password (input hidden): ')
                    if not password:
                        raise LeetCodeSyncError('LeetCode password is required.')
                    credentials = login_with_browser(args.cdp_url, username, login, password)
                connection = {'version': 1, 'username': username, **credentials, 'linked_at': utc_now()}
                verified_username = verify_connection(connection)
                connection['username'] = verified_username
                save_private_json(session_path, connection)
                output = {'linked': True, 'username': verified_username,
                          'session_file': str(session_path), 'next': 'Run sync to fetch history.'}
            elif args.command == 'sync':
                snapshot = sync(session_path, snapshot_path, args.limit)
                output = {'synced': True, 'username': snapshot['username'], 'synced_at': snapshot['synced_at'],
                          'total_solved': snapshot['total_solved'],
                          'recent_accepted_count': len(snapshot['recent_accepted'])}
            elif args.command == 'status':
                output = public_status(session_path, snapshot_path)
            else:
                session_path.unlink(missing_ok=True)
                output = {'disconnected': True, 'history_retained': snapshot_path.exists()}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (LeetCodeSyncError, OSError, ValueError) as exc:
        print(f'LeetCode sync error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
