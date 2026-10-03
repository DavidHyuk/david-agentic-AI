#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Install a user-local temporary YouTube desktop on Ubuntu 24.04 DGX Spark.

Use the existing YouTube venv; no sudo, system package changes or permanent
desktop service. Ubuntu packages are fetched over HTTPS and checked against
their repository SHA256 before extraction into the private runtime directory.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import os
from pathlib import Path
import subprocess
import urllib.request

BASE_URL = 'https://ports.ubuntu.com/ubuntu-ports/'
PACKAGES = {'xvfb', 'x11vnc', 'libvncserver1', 'libvncclient1', 'novnc', 'xauth'}


def package_records(text: str) -> dict[str, dict]:
    records = {}
    for block in text.split('\n\n'):
        fields = dict(line.split(': ', 1) for line in block.splitlines()
                      if ': ' in line and not line.startswith(' '))
        if fields.get('Package') in PACKAGES:
            records[fields['Package']] = fields
    return records


def fetch_package(record: dict) -> tuple[str, bytes]:
    filename = record['Filename']
    if not filename.startswith('pool/') or '..' in Path(filename).parts:
        raise ValueError('Invalid Ubuntu package path.')
    payload = urllib.request.urlopen(BASE_URL + filename, timeout=60).read()
    if hashlib.sha256(payload).hexdigest() != record['SHA256']:
        raise ValueError('Ubuntu package integrity check failed.')
    return Path(filename).name, payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir', type=Path,
                        default=Path('/home/david/.hermes/venvs/youtube-history'))
    args = parser.parse_args(argv)
    os.umask(0o077)
    architecture = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip()
    if architecture != 'arm64' or 'VERSION_ID="24.04"' not in Path('/etc/os-release').read_text():
        parser.error('This installer targets Ubuntu 24.04 arm64 on DGX Spark.')
    python = args.runtime_dir / 'bin/python'
    if not python.is_file():
        parser.error('Run bootstrap/install_youtube_history.sh first.')
    desktop = args.runtime_dir / 'desktop'
    cache = desktop / 'packages'
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    desktop.chmod(0o700)
    records = {}
    for suite in ('noble', 'noble-updates'):
        for component in ('main', 'universe'):
            url = BASE_URL + f'dists/{suite}/{component}/binary-arm64/Packages.gz'
            payload = urllib.request.urlopen(url, timeout=60).read()
            records.update(package_records(gzip.decompress(payload).decode()))
    missing = PACKAGES - records.keys()
    if missing:
        raise RuntimeError('Required Ubuntu desktop packages are missing.')
    for package in sorted(PACKAGES):
        filename, payload = fetch_package(records[package])
        target = cache / filename
        target.write_bytes(payload)
        subprocess.run(['dpkg-deb', '--extract', str(target), str(desktop)], check=True)
        print('Installed user-local', package)
    environment = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(args.runtime_dir / 'browsers'))
    subprocess.run([str(python), '-m', 'playwright', 'install', 'chromium', '--no-remove'],
                   env=environment, check=True)
    uv = Path.home() / '.local/bin/uv'
    command = ([str(uv), 'pip', 'install', '--python', str(python)] if uv.is_file()
               else [str(python), '-m', 'pip', 'install'])
    subprocess.run([*command, 'websockify>=0.13,<1'], check=True)
    print('Temporary YouTube desktop runtime ready. No persistent desktop service installed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
