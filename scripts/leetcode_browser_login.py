#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Reconnect LeetCode through a temporary DGX browser in the private dashboard.

Reuse the installed YouTube desktop runtime without sharing browser profiles or
credentials. Open the Jun workbench's login link. The user completes login
and browser verification; the existing sync CLI verifies and saves the session.
Close the temporary desktop, download Accepted code and rebuild missing reviews.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time

WEB_PORT = 18782
VNC_PORT = 15903
DISPLAY = ':96'
LOGIN_URL = '/leetcode-login/vnc.html?autoconnect=true&resize=scale&path=leetcode-login/websockify'
LOGIN_UNIT = 'hermes-leetcode-login'


def save_status(path, status, **fields):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump({'status': status, **fields}, handle)
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def stop_process(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def wait_port(port, processes, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(process.poll() is not None for process in processes):
            raise RuntimeError('Temporary desktop component stopped.')
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.3):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError('Temporary desktop is not ready.')


def desktop_commands(runtime, authority):
    desktop = runtime / 'desktop'
    return [
        [str(desktop / 'usr/bin/Xvfb'), DISPLAY, '-screen', '0', '1366x900x24',
         '-nolisten', 'tcp', '-auth', str(authority)],
        [str(desktop / 'usr/bin/x11vnc'), '-display', DISPLAY, '-auth', str(authority),
         '-listen', '127.0.0.1', '-rfbport', str(VNC_PORT), '-forever', '-shared',
         '-nopw', '-noxdamage', '-quiet'],
        [str(runtime / 'bin/python'), '-m', 'websockify', '--web',
         str(desktop / 'usr/share/novnc'), f'127.0.0.1:{WEB_PORT}', f'127.0.0.1:{VNC_PORT}'],
    ]


def start_login(home, runtime, username, timeout, runner=subprocess.run):
    """Start a bounded user unit that survives dashboard requests and SSH exits."""
    root = home / 'data/interview'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    status_path = root / 'leetcode-login-status.json'
    with (root / '.leetcode-login-start.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        active = runner(['systemctl', '--user', 'is-active', '--quiet', LOGIN_UNIT],
                        capture_output=True, timeout=5)
        if active.returncode:
            save_status(status_path, 'starting')
            command = ['systemd-run', '--user', '--unit=' + LOGIN_UNIT, '--collect',
                       '--property=RuntimeMaxSec=55min', sys.executable, str(Path(__file__).resolve()),
                       '--home', str(home), '--runtime-dir', str(runtime),
                       '--username', username, '--timeout', str(timeout)]
            result = runner(command, capture_output=True, timeout=10)
            if result.returncode:
                save_status(status_path, 'failed')
                raise RuntimeError('Could not start the temporary login service.')
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                status = json.loads(status_path.read_text()).get('status')
            except (OSError, ValueError):
                status = None
            if status in ('awaiting_login', 'syncing', 'connected'):
                return {'status': status, 'url': LOGIN_URL if status == 'awaiting_login' else None}
            if status in ('failed', 'stopped'):
                raise RuntimeError('Temporary login did not start. Check the private login log.')
            time.sleep(0.2)
        raise RuntimeError('Login window is still starting. Refresh the Jun workbench shortly.')


def connect_session(home, username, session, runner=subprocess.run):
    """Verify a user-pasted LeetCode cookie through stdin, then refresh in background."""
    if not isinstance(session, str) or not 20 <= len(session.strip()) <= 8192 or any(c.isspace() for c in session.strip()):
        raise RuntimeError('LEETCODE_SESSION value is missing or malformed.')
    runner(['systemctl', '--user', 'stop', LOGIN_UNIT], capture_output=True, timeout=15)
    result = runner([sys.executable, str(Path(__file__).with_name('leetcode_sync.py')),
                     '--session-file', str(home / 'data/interview/leetcode_session.json'),
                     'connect', '--username', username, '--stdin'],
                    input=session.strip(), capture_output=True, text=True, timeout=45,
                    env={**os.environ, 'HERMES_HOME': str(home)})
    if result.returncode:
        raise RuntimeError('LeetCode session verification failed. Use a fresh cookie for the linked account.')
    status_path = home / 'data/interview/leetcode-login-status.json'
    save_status(status_path, 'syncing')
    result = runner(['systemd-run', '--user', '--unit=' + LOGIN_UNIT, '--collect',
                     '--property=RuntimeMaxSec=45min', sys.executable, str(Path(__file__).resolve()),
                     '--home', str(home), '--username', username, '--refresh'],
                    capture_output=True, timeout=10)
    if result.returncode:
        save_status(status_path, 'failed')
        return {'verified': True, 'refresh_started': False}
    return {'verified': True, 'refresh_started': True, 'status': 'syncing'}


def reconnect(home, runtime, username, timeout, status_path):
    """Run the existing manual-login CLI on an isolated temporary display."""
    browsers = sorted((runtime / 'browsers').glob('chromium-*/chrome-linux*/chrome'))
    if not browsers:
        raise RuntimeError('Install the temporary browser desktop runtime first.')
    for port in (VNC_PORT, WEB_PORT):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('127.0.0.1', port))
    env = {**os.environ, 'HERMES_HOME': str(home), 'DISPLAY': DISPLAY,
           'LIBGL_ALWAYS_SOFTWARE': '1'}
    libraries = [str(path) for path in sorted((runtime / 'desktop/usr/lib').glob('*-linux-gnu'))]
    env['LD_LIBRARY_PATH'] = ':'.join(libraries + [os.environ.get('LD_LIBRARY_PATH', '')])
    with tempfile.TemporaryDirectory(prefix='leetcode-desktop-', dir=status_path.parent) as temporary:
        authority = Path(temporary) / 'xauth'
        authority.touch(mode=0o600)
        env['XAUTHORITY'] = str(authority)
        subprocess.run(['xauth', '-f', str(authority), 'add', DISPLAY, 'MIT-MAGIC-COOKIE-1',
                        secrets.token_hex(16)], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        with ExitStack() as cleanup:
            processes = []
            for index, command in enumerate(desktop_commands(runtime, authority)):
                process = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL)
                processes.append(process)
                cleanup.callback(stop_process, process)
                if index == 0:
                    time.sleep(1)
                else:
                    wait_port((VNC_PORT, WEB_PORT)[index - 1], processes)
            save_status(status_path, 'awaiting_login', web_port=WEB_PORT,
                        started_at=datetime.now(timezone.utc).isoformat(), expires_in_seconds=timeout)
            print('LeetCode browser ready; open the login link in the Jun workbench.', flush=True)
            command = [str(runtime / 'bin/python'), str(Path(__file__).with_name('leetcode_sync.py')),
                       '--session-file', str(home / 'data/interview/leetcode_session.json'),
                       'login', '--headed', '--username', username,
                       '--browser-executable', str(browsers[-1]), '--timeout-seconds', str(timeout)]
            log_path = status_path.parent / 'leetcode-login.log'
            with log_path.open('w') as log:
                log_path.chmod(0o600)
                result = subprocess.run(command, env=env, stdout=log,
                                        stderr=log, timeout=timeout + 90)
            if result.returncode:
                raise RuntimeError('User login or account verification did not complete.')
    # ExitStack closes desktop components before any inference begins.


def refresh_sources(home, runner=subprocess.run):
    """Require authenticated source sync before requesting code-backed reviews."""
    env = {**os.environ, 'HERMES_HOME': str(home)}
    directory = Path(__file__).parent
    runner([sys.executable, str(directory / 'leetcode_sync.py'), 'sync', '--missing-only'],
           env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=240)
    snapshot = json.loads((home / 'data/interview/leetcode_history.json').read_text())
    if snapshot.get('solution_sync_status') != 'ok':
        raise RuntimeError('New login did not restore private submission access.')
    result = runner([sys.executable, str(directory / 'leetcode_review.py'), 'prepare'],
                    env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1800)
    return {'downloaded_solution_count': len(snapshot.get('accepted_solutions', [])),
            'reviews_prepared': result.returncode == 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path(os.environ.get('HERMES_HOME', Path.home() / '.hermes')))
    parser.add_argument('--runtime-dir', type=Path, default=Path.home() / '.hermes/venvs/youtube-history')
    parser.add_argument('--username')
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('--start', action='store_true', help='start/reuse a bounded background login window')
    parser.add_argument('--connect-stdin', action='store_true', help='verify a PC browser session from stdin')
    parser.add_argument('--refresh', action='store_true', help='refresh verified source and reviews without a login window')
    args = parser.parse_args(argv)
    if not 60 <= args.timeout <= 900:
        parser.error('--timeout must be between 60 and 900 seconds')
    os.umask(0o077)
    root = args.home / 'data/interview'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    username = args.username
    if not username:
        username = json.loads((root / 'leetcode_session.json').read_text()).get('username')
    if not isinstance(username, str) or not username:
        parser.error('--username is required for the first connection')
    status_path = root / 'leetcode-login-status.json'
    if args.start or args.connect_stdin:
        try:
            result = (connect_session(args.home, username, sys.stdin.read(8193)) if args.connect_stdin
                      else start_login(args.home, args.runtime_dir, username, args.timeout))
            print(json.dumps(result), flush=True)
            return 0
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            print(str(exc), file=sys.stderr)
            return 1
    def interrupted(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    with (root / '.leetcode-login.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('A LeetCode login window is already running.', file=sys.stderr)
            return 1
        try:
            if not args.refresh:
                reconnect(args.home, args.runtime_dir, username, args.timeout, status_path)
            save_status(status_path, 'syncing')
            result = refresh_sources(args.home)
            save_status(status_path, 'connected', completed_at=datetime.now(timezone.utc).isoformat(), **result)
            print(json.dumps({'status': 'connected', **result}), flush=True)
            return 0
        except KeyboardInterrupt:
            save_status(status_path, 'stopped')
            print('Temporary LeetCode login stopped; prior sources retained.')
            return 1
        except Exception:
            save_status(status_path, 'failed')
            print('LeetCode login or source verification did not complete; prior sources retained.', file=sys.stderr)
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
