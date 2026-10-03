#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Temporarily show DGX Chromium over localhost noVNC for direct YouTube login.

Run in the dedicated YouTube Python environment after the desktop installer.
Forward localhost:18780 over SSH. No Google password, page content, or cookies
are printed. Confirmed YouTube cookies stay on this server, then normal history
connect and sync verify that authentication survives browser shutdown.
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
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

DEFAULT_RUNTIME = Path('/home/david/.hermes/venvs/youtube-history')
DEFAULT_DATA = Path('/home/david/.hermes/data/youtube-history')


def save_private_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def youtube_cookies(cookies: list[dict]) -> list[dict]:
    """Keep browser attributes intact while excluding unrelated account cookies."""
    selected = []
    for cookie in cookies:
        domain = cookie.get('domain', '').lstrip('.').lower()
        if domain == 'youtube.com' or domain.endswith('.youtube.com'):
            selected.append(dict(cookie))
    if not any(cookie.get('name') in {'SID', 'SAPISID', '__Secure-1PSID', '__Secure-3PSID'}
               for cookie in selected):
        raise ValueError('No authenticated YouTube session.')
    return selected


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def wait_port(port: int, processes: list[subprocess.Popen], timeout: float = 20) -> None:
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


def desktop_commands(runtime: Path, data_dir: Path, executable: Path, display: str) -> list[list[str]]:
    desktop = runtime / 'desktop'
    authority = data_dir / 'login.xauth'
    return [
        [str(desktop / 'usr/bin/Xvfb'), display, '-screen', '0', '1366x900x24',
         '-nolisten', 'tcp', '-auth', str(authority)],
        [str(desktop / 'usr/bin/x11vnc'), '-display', display, '-auth', str(authority),
         '-listen', '127.0.0.1', '-rfbport', '15901', '-forever', '-shared', '-nopw',
         '-noxdamage', '-quiet'],
        [str(runtime / 'bin/python'), '-m', 'websockify', '--web',
         str(desktop / 'usr/share/novnc'), '127.0.0.1:18780', '127.0.0.1:15901'],
        [str(executable), '--no-first-run', '--no-default-browser-check',
         '--password-store=basic', '--disable-dev-shm-usage', '--disable-gpu',
         '--no-sandbox',
         '--user-data-dir=' + str(data_dir / 'login-browser'),
         '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=19323',
         '--window-size=1366,900', '--window-position=0,0',
         'https://www.youtube.com/feed/history?hl=en&gl=US'],
    ]


def await_authenticated_cookies(context, processes, timeout: int) -> list[dict]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(process.poll() is not None for process in processes) or not context.pages:
            raise RuntimeError('Desktop component stopped.')
        # Sync Playwright must dispatch navigation events even while on Google or
        # about:blank. time.sleep alone leaves cached page URLs permanently stale.
        context.pages[0].wait_for_timeout(2000)
        for page in context.pages:
            if urlsplit(page.url).hostname not in ('www.youtube.com', 'youtube.com'):
                continue
            try:
                authenticated = page.evaluate("() => window.ytcfg?.get('LOGGED_IN') === true")
            except Exception:
                continue
            if authenticated:
                return youtube_cookies(context.cookies())
    raise TimeoutError('Login window expired.')


def run_desktop(runtime: Path, data_dir: Path, timeout: int) -> list[dict]:
    from playwright.sync_api import sync_playwright
    executables = sorted((runtime / 'browsers').glob('chromium-*/chrome-linux*/chrome'))
    if not executables:
        raise RuntimeError('Install the headed browser runtime first.')
    env = os.environ.copy()
    env['DISPLAY'] = ':97'
    env['LIBGL_ALWAYS_SOFTWARE'] = '1'
    env['XAUTHORITY'] = str(data_dir / 'login.xauth')
    library_dir = runtime / 'desktop/usr/lib'
    env['LD_LIBRARY_PATH'] = ':'.join(str(p) for p in sorted(library_dir.glob('*-linux-gnu')))
    env['LD_LIBRARY_PATH'] += ':' + os.environ.get('LD_LIBRARY_PATH', '')
    for port in (15901, 18780, 19323):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
    # X11 requires an owner-only authorization file; VNC/WebSocket bind loopback.
    authority = data_dir / 'login.xauth'
    authority.touch(mode=0o600)
    authority.chmod(0o600)
    subprocess.run(['xauth', '-f', str(authority), 'add', ':97', 'MIT-MAGIC-COOKIE-1',
                    secrets.token_hex(16)], check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    commands = desktop_commands(runtime, data_dir, executables[-1], ':97')
    processes = []
    with ExitStack() as cleanup:
        cleanup.callback(shutil.rmtree, data_dir / 'login-browser', ignore_errors=True)
        cleanup.callback(authority.unlink, missing_ok=True)
        for index, command in enumerate(commands):
            process = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
            processes.append(process)
            cleanup.callback(stop_process, process)
            if index == 0:
                time.sleep(1)
            elif index in (1, 2, 3):
                wait_port((15901, 18780, 19323)[index - 1], processes)
        save_private_json(data_dir / 'login-status.json', {
            'status': 'awaiting_login', 'started_at': datetime.now(timezone.utc).isoformat(),
            'web_port': 18780, 'expires_in_seconds': timeout,
        })
        print('DGX Chromium ready: forward 127.0.0.1:18780 over SSH and open /vnc.html.', flush=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp('http://127.0.0.1:19323')
            context = browser.contexts[0]
            cookies = await_authenticated_cookies(context, processes, timeout)
            # Close the interactive window before headless verification.
            browser.close()
            return cookies


def verify_session(history_script: Path, data_dir: Path, *, runner=subprocess.run) -> bool:
    """Require both initial collection and another browser launch to succeed."""
    for args in (['connect', '--saved-cookies'], ['sync']):
        result = runner([sys.executable, str(history_script), '--data-dir', str(data_dir),
                         '--browser-dir', str(data_dir / 'browser'), *args],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=150)
        if result.returncode:
            return False
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir', type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument('--data-dir', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--history-script', type=Path,
                        default=Path(__file__).with_name('youtube_history.py'))
    parser.add_argument('--timeout', type=int, default=1200)
    args = parser.parse_args(argv)
    if not 60 <= args.timeout <= 3600:
        parser.error('--timeout must be between 60 and 3600 seconds')
    args.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.data_dir.chmod(0o700)
    def interrupted(*unused):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    status_path = args.data_dir / 'login-status.json'
    with (args.data_dir / '.login.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('A YouTube login window is already running.', file=sys.stderr)
            return 1
        try:
            cookies = run_desktop(args.runtime_dir, args.data_dir, args.timeout)
            save_private_json(args.data_dir / 'session.json', {'version': 1, 'cookies': cookies})
            save_private_json(status_path, {'status': 'verifying'})
            if not verify_session(args.history_script, args.data_dir):
                raise RuntimeError('Saved session verification failed.')
            save_private_json(status_path, {'status': 'connected',
                                           'completed_at': datetime.now(timezone.utc).isoformat()})
            print('YouTube login and subsequent history sync verified. Temporary desktop stopped.')
            return 0
        except KeyboardInterrupt:
            save_private_json(status_path, {'status': 'stopped'})
            print('Temporary YouTube login stopped.')
            return 1
        except Exception:
            save_private_json(status_path, {'status': 'failed'})
            print('YouTube login window or session verification failed. Previous history is preserved.', file=sys.stderr)
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
