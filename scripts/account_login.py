#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Expose safe workbench connection state and start existing login helpers.

Reuse credential owners, browser profiles and bounded user units. Never include
cookies, account identity or private Kakao endpoint paths in status responses.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

ROOM_ACCOUNTS = {'coding': ('leetcode', 'chatgpt'), 'hq': ('chatgpt',),
                 'podcast': ('youtube',), 'english': ('kakao',)}
UNITS = {'leetcode': 'hermes-leetcode-login', 'chatgpt': 'hermes-chatgpt-login',
         'youtube': 'hermes-youtube-login'}
PORTS = {'leetcode': 18782, 'chatgpt': 18781, 'youtube': 18780}


def read_json(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream)
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def unit_active(unit, runner=subprocess.run):
    try:
        return runner(['systemctl', '--user', 'is-active', '--quiet', unit],
                      capture_output=True, timeout=3).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def status_path(home, service):
    return home / 'data' / {'leetcode': 'interview/leetcode-login-status.json',
                           'chatgpt': 'chatgpt/browser-status.json',
                           'youtube': 'youtube-history/login-status.json'}[service]


def login_url(service):
    prefix = service + '-login'
    return f'/{prefix}/vnc.html?autoconnect=true&resize=scale&path={prefix}/websockify'


def connection(home, service, runner=subprocess.run):
    if service == 'kakao':
        return {'service': service, 'status': 'setup',
                'webhook_running': unit_active('kakao-webhook.service', runner),
                'tunnel_running': unit_active('kakao-tunnel.service', runner),
                'fixed_origin_configured': (home / 'data/english/kakao-public-origin.txt').is_file(),
                'skill_url_available': (home / 'data/english/kakao-skill-url.txt').is_file(),
                'manager_url': 'https://i.kakao.com/', 'channel_url': 'https://center-pf.kakao.com/'}
    state = read_json(status_path(home, service))
    active = unit_active(UNITS[service], runner)
    phase = state.get('browser_status' if service == 'chatgpt' else 'status')
    result = {'service': service, 'status': 'not_connected'}
    if active and phase in ('starting', 'awaiting_login', 'authenticated'):
        result.update(status='starting' if phase == 'starting' else 'awaiting_login',
                      url=login_url(service) if phase != 'starting' else None)
        return result
    if active and phase in ('syncing', 'verifying'):
        result['status'] = 'verifying'
        return result
    if service == 'leetcode':
        source = read_json(home / 'data/interview/leetcode_history.json')
        result['status'] = 'reconnect' if source.get('solution_sync_status') == 'reauth_required' else 'verified' if source.get('solution_sync_status') == 'ok' else 'not_connected'
    elif service == 'chatgpt':
        daily = read_json(home / 'data/chatgpt/daily-sync.json')
        stamp = state.get('authenticated_at')
        result['status'] = 'verified' if stamp else 'not_connected'
        if daily.get('status') == 'error' and str(daily.get('last_attempt_at') or '') > str(stamp or ''):
            result['status'] = 'reconnect' if 'login' in str(daily.get('error', '')).lower() else 'sync_error'
        if str(state.get('login_requested_at') or '') > str(stamp or ''):
            result['status'] = 'reconnect'
    else:
        authentication = read_json(home / 'data/youtube-history/authentication.json')
        saved = read_json(home / 'data/youtube-history/connection.json')
        result['status'] = 'verified' if authentication.get('verified_at') or saved.get('verified_at') else 'not_connected'
        if phase == 'failed':
            result['status'] = 'reconnect'
    return result


def connections(home, room, runner=subprocess.run):
    return {'accounts': [connection(home, service, runner) for service in ROOM_ACCOUNTS.get(room, ())]}


def start_login(home, service, runner=subprocess.run):
    if service not in ('chatgpt', 'youtube'):
        raise ValueError('Unsupported account login.')
    root = home / 'data/accounts'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / '.login-start.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not unit_active(UNITS[service], runner):
            runtime = home / 'venvs/youtube-history'
            if not (runtime / 'bin/python').is_file():
                raise ValueError('The existing browser login runtime is not installed.')
            path = status_path(home, service)
            previous = read_json(path)
            save_json(path, {**previous, 'browser_status' if service == 'chatgpt' else 'status': 'starting',
                             'login_requested_at': datetime.now(timezone.utc).isoformat()})
            arguments = ([str(Path(__file__).with_name('chatgpt_archive.py')), '--data-dir', str(home / 'data/chatgpt'),
                          'login', '--runtime-dir', str(runtime), '--timeout', '900', '--close-after-login']
                         if service == 'chatgpt' else
                         [str(Path(__file__).with_name('youtube_browser_login.py')), '--data-dir', str(home / 'data/youtube-history'),
                          '--runtime-dir', str(runtime), '--timeout', '900'])
            command = ['systemd-run', '--user', '--unit=' + UNITS[service], '--collect',
                       '--property=RuntimeMaxSec=25min', str(runtime / 'bin/python'), *arguments]
            result = runner(command, capture_output=True, timeout=10)
            if result.returncode:
                save_json(path, previous)
                raise ValueError('Could not start the account login window.')
        return connection(home, service, runner)


def kakao_url(home):
    """Return the private setup value only following an explicit copy action."""
    try:
        value = (home / 'data/english/kakao-skill-url.txt').read_text().strip()
    except OSError:
        raise ValueError('Kakao skill URL is not configured.') from None
    parsed = urlsplit(value)
    if (len(value) > 4096 or parsed.scheme != 'https' or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not parsed.path.startswith('/kakao/')):
        raise ValueError('Kakao skill URL is invalid.')
    return {'url': value}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path(os.environ.get('HERMES_HOME', Path.home() / '.hermes')))
    parser.add_argument('action', choices=('status', 'start', 'stop', 'kakao-url'))
    parser.add_argument('--room', choices=tuple(ROOM_ACCOUNTS), default='coding')
    parser.add_argument('--service', choices=('chatgpt', 'youtube'))
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        if args.action == 'status':
            result = connections(args.home, args.room)
        elif args.action == 'kakao-url':
            result = kakao_url(args.home)
        else:
            if not args.service:
                parser.error('--service is required')
            if args.action == 'start':
                result = start_login(args.home, args.service)
            else:
                subprocess.run(['systemctl', '--user', 'stop', UNITS[args.service]],
                               capture_output=True, timeout=15)
                result = connection(args.home, args.service)
        print(json.dumps(result), flush=True)
        return 0
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(str(exc) if isinstance(exc, ValueError) else 'Account connection action failed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
