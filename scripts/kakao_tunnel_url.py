#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Refresh the private Kakao skill URL from the current Quick Tunnel invocation.

Run after tunnel startup, including reboot and automatic service recovery. Check
the public endpoint without saving feedback; never print the shared secret.
This updates the local URL file, not Kakao's deployed skill configuration.
"""
from __future__ import annotations

import argparse
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit


def tunnel_origin(logs: str) -> str | None:
    """Accept an origin only after this invocation has connected to the edge."""
    origins = re.findall(r'https://[a-z0-9-]+\.trycloudflare\.com', logs)
    if not origins or 'Registered tunnel connection' not in logs:
        return None
    return origins[-1]


def endpoint_path(env_file: Path) -> str:
    values = [line.split('=', 1)[1].strip().strip('\"\'')
              for line in env_file.read_text().splitlines()
              if line.startswith('KAKAO_WEBHOOK_PATH=')]
    if not values or not re.fullmatch(r'/kakao/[A-Za-z0-9_-]+', values[-1]):
        raise ValueError('Kakao webhook path is missing or invalid.')
    return values[-1]


def endpoint_ready(url: str) -> bool:
    """An empty skill body must return Kakao JSON 400 without touching intake."""
    parsed = urlsplit(url)
    if parsed.hostname and parsed.hostname.endswith('.ts.net'):
        return funnel_endpoint_ready(parsed)
    request = Request(url, data=b'{}', headers={'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=4):
            return False
    except HTTPError as response:
        with response:
            if response.code != 400:
                return False
            try:
                body = json.loads(response.read(8192))
                return body.get('version') == '2.0' and bool(body.get('template', {}).get('outputs'))
            except (ValueError, AttributeError):
                return False
    except (URLError, OSError):
        return False


def public_addresses(host: str) -> list[str]:
    """Resolve Funnel through public DNS, bypassing local MagicDNS routing."""
    request = Request('https://dns.google/resolve?name=' + host
                      + '&type=A&random_padding=' + secrets.token_hex(8),
                      headers={'Cache-Control': 'no-cache'})
    with urlopen(request, timeout=4) as response:
        payload = json.loads(response.read(8192))
    return [row['data'] for row in payload.get('Answer', [])
            if row.get('type') == 1 and ipaddress.ip_address(row['data']).is_global]


def funnel_endpoint_ready(parsed) -> bool:
    """Verify public Funnel ingress rather than the same machine's private IP."""
    connection = None
    try:
        addresses = public_addresses(parsed.hostname)
        if not addresses:
            return False
        port = parsed.port or 443
        connection = http.client.HTTPSConnection(parsed.hostname, port, timeout=4)
        raw = socket.create_connection((addresses[0], port), timeout=4)
        try:
            connection.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=parsed.hostname)
        except Exception:
            raw.close()
            raise
        connection.request('POST', parsed.path, body=b'{}', headers={'Content-Type': 'application/json'})
        response = connection.getresponse()
        if response.status != 400:
            return False
        body = json.loads(response.read(8192))
        return body.get('version') == '2.0' and bool(body.get('template', {}).get('outputs'))
    except (OSError, ValueError, AttributeError, KeyError, http.client.HTTPException):
        return False
    finally:
        if connection is not None:
            connection.close()


def save_url(path: Path, url: str) -> bool:
    """Atomically replace the owner-only URL, returning whether it changed."""
    previous = path.read_text().strip() if path.exists() else None
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(url + '\n')
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return previous != url


def fixed_origin(value: str) -> str:
    """Validate a public HTTPS origin without paths, credentials or query data."""
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
            or parsed.password or parsed.path not in ('', '/') or parsed.query
            or parsed.fragment or any(c.isspace() for c in value)):
        raise ValueError('A public HTTPS origin is required.')
    _ = parsed.port
    return value.rstrip('/')


def refresh_fixed(home: Path, origin: str) -> bool:
    """Verify a stable endpoint before saving either origin or private URL."""
    origin = fixed_origin(origin)
    url = origin + endpoint_path(home / '.env')
    if not endpoint_ready(url):
        raise ValueError('Fixed endpoint is unreachable; existing URL was preserved.')
    changed = save_url(home / 'data/english/kakao-skill-url.txt', url)
    save_url(home / 'data/english/kakao-public-origin.txt', origin)
    return changed


def refresh(home: Path, invocation: str, timeout: float = 35) -> bool:
    """Wait for this service invocation, preserving the old file on failure."""
    if not re.fullmatch(r'[a-f0-9]{32}', invocation):
        raise ValueError('A current tunnel invocation ID is required.')
    secret = endpoint_path(home / '.env')
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = subprocess.run(
            ['journalctl', '--user', f'_SYSTEMD_INVOCATION_ID={invocation}', '--no-pager'],
            capture_output=True, text=True, timeout=4, check=True,
        )
        origin = tunnel_origin(result.stdout)
        if origin and endpoint_ready(origin + secret):
            return save_url(home / 'data/english/kakao-skill-url.txt', origin + secret)
        time.sleep(1)
    raise ValueError('Current tunnel endpoint did not become reachable; saved URL was preserved.')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path.home() / '.hermes')
    parser.add_argument('--invocation', default=os.environ.get('INVOCATION_ID'))
    parser.add_argument('--origin', help='Verified stable public HTTPS origin, without the secret path')
    parser.add_argument('--probe-only', action='store_true',
                        help='check the saved public skill URL without changing URL files or intake')
    args = parser.parse_args(argv)
    try:
        if args.probe_only:
            url = (args.home / 'data/english/kakao-skill-url.txt').read_text().strip()
            parsed = urlsplit(url)
            if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                    or parsed.query or parsed.fragment or
                    not re.fullmatch(r'/kakao/[A-Za-z0-9_-]+', parsed.path) or not endpoint_ready(url)):
                raise ValueError('Saved public collector probe failed.')
            print('Kakao public collector probe passed; no feedback was saved.')
            return 0
        origin_file = args.home / 'data/english/kakao-public-origin.txt'
        origin = args.origin or (origin_file.read_text().strip() if origin_file.exists() else None)
        if origin:
            changed = refresh_fixed(args.home, origin)
        else:
            invocation = args.invocation or subprocess.check_output(
                ['systemctl', '--user', 'show', 'kakao-tunnel.service', '-p', 'InvocationID', '--value'],
                text=True, timeout=4,
            ).strip()
            changed = refresh(args.home, invocation)
    except (OSError, ValueError, subprocess.SubprocessError):
        print('Kakao URL refresh failed; check tunnel connectivity and private configuration.', file=sys.stderr)
        return 1
    print('Private Kakao skill URL verified and refreshed.' if changed else 'Private Kakao skill URL is current.')
    if changed:
        print('Update the skill URL in Kakao Open Builder and deploy the bot again.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
