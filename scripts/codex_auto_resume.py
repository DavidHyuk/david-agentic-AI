#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Persist Codex usage-limit retries and submit verified non-interactive turns.

No Hermes imports or runtime dependencies. The watcher reads Codex rollouts;
independent systemd workers survive watcher restarts. Only quota failures get
automatic task retries. Never replay an ambiguous, already submitted turn.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import shutil
import socket
import sqlite3
import struct
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

WAIT_SECONDS = 5 * 60 * 60
GRACE_SECONDS = 90
ROLLOUT_PARSER_VERSION = '2'
PROMPT = ('사용량 제한으로 중단된 기존 작업을 계속 진행해줘. 기존 대화의 목표와 '
          '승인 범위를 유지하고, 현재 파일과 실행 상태를 확인하여 이미 완료한 '
          '작업이나 외부 전송을 중복하지 말고 남은 작업을 완료하고 검증해줘.')


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def is_usage_limit(error):
    if not isinstance(error, dict):
        return False
    info = error.get('codex_error_info')
    if info == 'usage_limit_exceeded':
        return True
    if isinstance(info, dict) and 'usage_limit_exceeded' in info:
        return True
    # Older versions omit the structured code. Context-window errors differ.
    return 'hit your usage limit' in error.get('message', '').lower()


def reset_from_error(error, failed_at):
    """Interpret Codex's local retry clock relative to the failure, not today."""
    if not is_usage_limit(error):
        return 0
    explicit = error.get('resets_at')
    if isinstance(explicit, (int, float)) and explicit >= failed_at:
        return explicit
    match = re.search(r'\btry again at (\d{1,2}):(\d{2})(?:\s*([AP]M))?\b',
                      error.get('message', ''), re.IGNORECASE)
    if not match:
        return 0
    hour, minute = map(int, match.group(1, 2))
    period = match.group(3)
    if minute > 59 or (period and not 1 <= hour <= 12) or (not period and hour > 23):
        return 0
    if period:
        hour = hour % 12 + (12 if period.upper() == 'PM' else 0)
    local = datetime.fromtimestamp(failed_at).astimezone()
    target = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target.timestamp() + GRACE_SECONDS <= failed_at:
        target += timedelta(days=1)
    return target.timestamp()


def apply_record(snapshot, record):
    payload = record.get('payload', {})
    kind = record.get('type')
    if kind == 'session_meta':
        snapshot.update(id=payload.get('id'), cwd=payload.get('cwd'),
                        created=timestamp(payload.get('timestamp', record['timestamp'])),
                        subagent=isinstance(payload.get('source'), dict))
    elif kind == 'turn_context':
        # A TUI resume can overwrite thread_settings without starting work.
        # Use the last actual turn's permissions, not that accidental downgrade.
        for key in ('cwd', 'approval_policy', 'sandbox_policy', 'permission_profile',
                    'model', 'effort', 'runtime_workspace_roots'):
            if key in payload:
                snapshot[key] = payload[key]
    elif kind == 'event_msg':
        event = payload.get('type')
        if event == 'task_started':
            snapshot['start'] = {'turn': payload['turn_id'], 'at': timestamp(record['timestamp'])}
            snapshot['reset_at'] = 0  # Never reuse an earlier turn's quota window.
        elif event == 'task_complete':
            failed_at = timestamp(record['timestamp'])
            snapshot['end'] = {'turn': payload['turn_id'], 'at': timestamp(record['timestamp']),
                               'usage_limit': is_usage_limit(payload.get('error')),
                               'failed': bool(payload.get('error')),
                               'reset_at': reset_from_error(payload.get('error'), failed_at)}
        elif event == 'turn_aborted':
            snapshot['end'] = {'turn': payload.get('turn_id'),
                               'at': timestamp(record['timestamp']),
                               'usage_limit': False, 'failed': True}
        elif event == 'token_count':
            limits = payload.get('rate_limits') or {}
            resets = [window.get('resets_at', 0) for key in ('primary', 'secondary')
                      if (window := limits.get(key)) and window.get('used_percent', 0) >= 100]
            snapshot['reset_at'] = max(resets, default=0)


def read_rollout(path, offset=0, snapshot=None):
    snapshot = dict(snapshot or {})
    with Path(path).open('rb') as stream:
        if offset > os.fstat(stream.fileno()).st_size:
            offset, snapshot = 0, {}
        stream.seek(offset)
        while line := stream.readline():
            if not line.endswith(b'\n'):
                break  # An append in progress must be reread next poll.
            try:
                apply_record(snapshot, json.loads(line))
            except (ValueError, KeyError, TypeError):
                pass
            offset = stream.tell()
    return offset, snapshot


def unresolved_limit(snapshot):
    end = snapshot.get('end', {})
    start = snapshot.get('start', {})
    return (not snapshot.get('subagent') and end.get('usage_limit', False)
            and end.get('at', 0) >= snapshot.get('created', 0)
            and start.get('at', 0) <= end['at'])


def due_for_limit(snapshot, wait=WAIT_SECONDS, grace=GRACE_SECONDS):
    reset = max(snapshot['end'].get('reset_at', 0), snapshot.get('reset_at', 0))
    return (reset or snapshot['end']['at'] + wait) + grace


def resume_command(codex, snapshot, prompt):
    sandbox = (snapshot.get('sandbox_policy') or {}).get('type')
    if snapshot.get('permission_profile', {}).get('type') == 'disabled':
        sandbox = 'danger-full-access'
    if sandbox not in ('read-only', 'workspace-write', 'danger-full-access'):
        raise ValueError('No supported last-turn permissions; refusing to guess')
    command = [codex, 'exec', '-C', snapshot['cwd'], '-s', sandbox,
               '-c', 'approval_policy="never"']
    # Never run hooks for diagnostics; ordinary resumes retain trusted hooks.
    if snapshot.get('disable_hooks'):
        command += ['--disable', 'hooks']
    if snapshot.get('model'):
        command += ['-m', snapshot['model']]
    if snapshot.get('effort'):
        command += ['-c', 'model_reasoning_effort=' + json.dumps(snapshot['effort'])]
    roots = set(snapshot.get('runtime_workspace_roots') or [])
    roots.update((snapshot.get('sandbox_policy') or {}).get('writable_roots') or [])
    for root in sorted(roots):
        if root != snapshot['cwd']:
            command += ['--add-dir', root]
    return command + ['resume', '--json', snapshot['id'], prompt]


class DaemonClient:
    """Local JSON-RPC over the daemon's Unix WebSocket; no network dependency."""
    def __init__(self, codex_home):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.settimeout(30)
        self.buffer = b''
        self.sequence = 0
        try:
            endpoint = (Path(codex_home) / 'app-server-control/app-server-control.sock').resolve()
            if not endpoint.exists():
                raise FileNotFoundError('Shared Codex daemon socket is unavailable')
            self.socket.connect(str(endpoint))
            key = base64.b64encode(os.urandom(16)).decode()
            request = ('GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n'
                       'Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n'
                       'Sec-WebSocket-Key: ' + key + '\r\n\r\n')
            self.socket.sendall(request.encode())
            while b'\r\n\r\n' not in self.buffer:
                data = self.socket.recv(4096)
                if not data or len(self.buffer) > 16384:
                    raise ValueError('Invalid daemon handshake')
                self.buffer += data
            header, self.buffer = self.buffer.split(b'\r\n\r\n', 1)
            expected = base64.b64encode(hashlib.sha1(
                (key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
            if b' 101 ' not in header.split(b'\r\n', 1)[0] or expected not in header:
                raise ValueError('Daemon WebSocket upgrade rejected')
            self.call('initialize', {'clientInfo': {'name': 'codex-auto-resume', 'version': '1.0'}})
            self.send({'method': 'initialized', 'params': {}})
        except Exception:
            self.close()
            raise

    def close(self):
        self.socket.close()

    def read_bytes(self, length):
        while len(self.buffer) < length:
            data = self.socket.recv(max(4096, length - len(self.buffer)))
            if not data:
                raise ConnectionError('Codex daemon disconnected')
            self.buffer += data
        data, self.buffer = self.buffer[:length], self.buffer[length:]
        return data

    def send_frame(self, payload, opcode=1):
        mask = os.urandom(4)
        length = len(payload)
        header = bytes([0x80 | opcode, 0x80 | length]) if length < 126 else (
            bytes([0x80 | opcode, 0x80 | 126]) + struct.pack('!H', length) if length < 65536 else
            bytes([0x80 | opcode, 0x80 | 127]) + struct.pack('!Q', length))
        encoded = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        self.socket.sendall(header + mask + encoded)

    def send(self, value):
        self.send_frame(json.dumps(value, ensure_ascii=False).encode())

    def receive(self):
        fragments = bytearray()
        while True:
            first, second = self.read_bytes(2)
            length = second & 0x7f
            if length == 126:
                length = struct.unpack('!H', self.read_bytes(2))[0]
            elif length == 127:
                length = struct.unpack('!Q', self.read_bytes(8))[0]
            if length + len(fragments) > 16 * 1024 * 1024:
                raise ValueError('Oversized daemon message')
            if second & 0x80:
                raise ValueError('Unexpected masked server message')
            payload = self.read_bytes(length)
            opcode = first & 0x0f
            if opcode == 8:
                raise ConnectionError('Daemon closed WebSocket')
            if opcode == 9:
                self.send_frame(payload, 10)
                continue
            if opcode == 10:
                continue
            if opcode not in (0, 1):
                raise ValueError('Unexpected daemon frame')
            fragments.extend(payload)
            if first & 0x80:
                return json.loads(fragments)

    def call(self, method, params):
        self.sequence += 1
        request_id = self.sequence
        self.send({'id': request_id, 'method': method, 'params': params})
        while True:
            value = self.receive()
            if value.get('id') == request_id:
                if 'error' in value:
                    raise ValueError(value['error'].get('message', 'Daemon request failed'))
                return value['result']


def submit_to_loaded_daemon(store, job, codex_home):
    """Handle an idle thread owned by an open TUI without stealing its writer."""
    try:
        client = DaemonClient(codex_home)
    except FileNotFoundError:
        store.update(job['id'], status='pending', due=time.time() + 60,
                     result='Another app owns the writer; waiting for release')
        return 0
    try:
        thread = client.call('thread/read', {'threadId': job['thread'], 'includeTurns': False})['thread']
        if thread['id'] != job['thread']:
            raise ValueError('Daemon returned a different session ID')
        state = thread['status']['type']
        if state == 'active':
            store.update(job['id'], status='superseded', result='Daemon already has an active turn')
            return 0
        if state not in ('idle', 'systemError'):
            store.update(job['id'], status='pending', due=time.time() + 60,
                         result='Writer belongs to another app; waiting for release')
            return 0
        snapshot = find_snapshot(codex_home, job['thread'])
        if not eligible_for_job(job, snapshot):
            store.update(job['id'], status='superseded', result='Quota failure resolved before daemon submission')
            return 0
        saved = json.loads(job['snapshot'])
        sandbox = resume_command('codex', saved, job['prompt'])
        mode = sandbox[sandbox.index('-s') + 1]
        policies = {'danger-full-access': {'type': 'dangerFullAccess'},
                    'read-only': {'type': 'readOnly'},
                    'workspace-write': {'type': 'workspaceWrite',
                                        'writableRoots': list(set([saved['cwd']] +
                                            list(saved.get('runtime_workspace_roots') or []) +
                                            list((saved.get('sandbox_policy') or {}).get('writable_roots') or []))),
                                        'networkAccess': bool((saved.get('sandbox_policy') or {}).get('network_access'))}}
        params = {'threadId': job['thread'], 'input': [{'type': 'text', 'text': job['prompt']}],
                  'cwd': saved['cwd'], 'approvalPolicy': 'never', 'sandboxPolicy': policies[mode]}
        if saved.get('model'):
            params['model'] = saved['model']
        if saved.get('effort'):
            params['effort'] = saved['effort']
        # The response acknowledges an actual started turn, not a queued message.
        turn = client.call('turn/start', params)['turn']
        receipt = {'transport': 'shared_daemon', 'thread_verified': True,
                   'turn_started': True, 'turn_id': turn['id']}
        store.update(job['id'], status='observing', started=1, result=json.dumps(receipt))
        log('daemon_turn_started', thread=job['thread'], job=job['id'], turn=turn['id'])
        return 0
    finally:
        client.close()


def parse_reset(value, now=None, grace=GRACE_SECONDS):
    now = datetime.now().astimezone() if now is None else now
    if value == 'now':
        return now.timestamp()
    if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
        raise ValueError('Reset time must be HH:MM (local time), or now')
    hour, minute = map(int, value.split(':'))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target.timestamp() + grace <= now.timestamp():
        target += timedelta(days=1)
    return target.timestamp() + grace


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(self.directory / 'state.sqlite', timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute('pragma journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS cursors (
                path TEXT PRIMARY KEY, offset INTEGER NOT NULL, snapshot TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, thread TEXT NOT NULL, cause TEXT NOT NULL,
                due REAL NOT NULL, status TEXT NOT NULL, snapshot TEXT NOT NULL,
                prompt TEXT NOT NULL, created REAL NOT NULL, launched REAL,
                unit TEXT, log TEXT, started INTEGER DEFAULT 0, result TEXT,
                UNIQUE(thread, cause));
            CREATE TABLE IF NOT EXISTS exclusions (thread TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')
        with self.db:
            version = self.db.execute("select value from metadata where key='rollout_parser_version'").fetchone()
            if not version or version['value'] != ROLLOUT_PARSER_VERSION:
                # Reparse immutable history after a parser upgrade; retain jobs and exclusions.
                self.db.execute('delete from cursors')
                self.db.execute("insert or replace into metadata values ('rollout_parser_version',?)",
                                (ROLLOUT_PARSER_VERSION,))

    def enqueue(self, snapshot, cause, due, prompt=PROMPT):
        existing = self.db.execute('select id,status,due from jobs where thread=? and cause=?',
                                   (snapshot['id'], cause)).fetchone()
        if existing:
            if existing['status'] == 'pending' and existing['due'] != due:
                self.update(existing['id'], due=due, snapshot=json.dumps(snapshot))
                log('rescheduled', thread=snapshot['id'], job=existing['id'], due=due)
            return existing['id']
        job_id = str(uuid.uuid4())
        with self.db:
            self.db.execute('insert into jobs (id,thread,cause,due,status,snapshot,prompt,created) '
                            'values (?,?,?,?,?,?,?,?)',
                            (job_id, snapshot['id'], cause, due, 'pending',
                             json.dumps(snapshot), prompt, time.time()))
        log('scheduled', thread=snapshot['id'], job=job_id, due=due)
        return job_id

    def update(self, job_id, **values):
        with self.db:
            self.db.execute('update jobs set ' + ','.join(k + '=?' for k in values) + ' where id=?',
                            [*values.values(), job_id])

    def jobs(self, statuses=None):
        if statuses:
            return self.db.execute('select * from jobs where status in (' +
                                   ','.join('?' for _ in statuses) + ') order by due', statuses).fetchall()
        return self.db.execute('select * from jobs order by created').fetchall()


def log(event, **fields):
    print(json.dumps({'at': datetime.now().astimezone().isoformat(), 'event': event,
                      **fields}, ensure_ascii=False), flush=True)


def discover(codex_home):
    # The official thread index avoids enumerating archived/unrelated files.
    databases = sorted(Path(codex_home).glob('state_*.sqlite'))
    if not databases:
        return []
    with sqlite3.connect(databases[-1].as_uri() + '?mode=ro', uri=True) as conn:
        return conn.execute('select id,rollout_path from threads where archived=0').fetchall()


def scan(store, codex_home, now=None, wait=WAIT_SECONDS, grace=GRACE_SECONDS):
    now = time.time() if now is None else now
    excluded = {row[0] for row in store.db.execute('select thread from exclusions')}
    snapshots = {}
    for thread, path in discover(codex_home):
        if thread in excluded or not Path(path).is_file():
            continue
        row = store.db.execute('select * from cursors where path=?', (path,)).fetchone()
        offset, snapshot = read_rollout(path, row['offset'] if row else 0,
                                        json.loads(row['snapshot']) if row else None)
        if snapshot.get('id') != thread:
            continue
        snapshots[thread] = snapshot
        with store.db:
            store.db.execute('insert or replace into cursors values (?,?,?)',
                             (path, offset, json.dumps(snapshot)))
        # Bootstrap only recent failures, never revive months-old abandoned tasks.
        previous = json.loads(row['snapshot']) if row else {}
        new_failure = bool(row) and previous.get('end', {}).get('turn') != snapshot.get('end', {}).get('turn')
        if unresolved_limit(snapshot) and (new_failure or snapshot['end']['at'] >= now - 86400):
            store.enqueue(snapshot, snapshot['end']['turn'], due_for_limit(snapshot, wait, grace))
    return snapshots


def changed_since_job(job, snapshot):
    old = json.loads(job['snapshot'])
    start = snapshot.get('start', {})
    return (start.get('turn') != old.get('start', {}).get('turn')
            and start.get('at', 0) > old.get('end', {}).get('at', 0))


def eligible_for_job(job, snapshot):
    """A reservation is valid only while its original quota failure is current."""
    old = json.loads(job['snapshot'])
    return (unresolved_limit(snapshot) and not changed_since_job(job, snapshot)
            and snapshot.get('end', {}).get('turn') == old.get('end', {}).get('turn'))


def unit_active(unit):
    return subprocess.run(['systemctl', '--user', 'is-active', '--quiet', unit],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def reconcile(store, snapshots, now=None, active=unit_active):
    now = time.time() if now is None else now
    for job in store.jobs(('pending', 'launching', 'running', 'observing')):
        snapshot = snapshots.get(job['thread'])
        if not snapshot:
            if job['status'] == 'pending':
                store.update(job['id'], status='cancelled', result='Thread archived, missing or excluded')
            continue
        changed = changed_since_job(job, snapshot)
        if job['status'] == 'pending':
            if not eligible_for_job(job, snapshot):
                store.update(job['id'], status='superseded', result='Original quota failure is no longer current')
            continue
        if active(job['unit']):
            continue
        if changed:
            end = snapshot.get('end', {})
            try:
                receipt = json.loads(job['result'] or '{}')
            except ValueError:
                receipt = {}
            if end.get('at', 0) >= snapshot['start']['at']:
                status = 'usage_limited' if end.get('usage_limit') else ('failed' if end.get('failed') else 'complete')
                receipt.update(recovered_from_rollout=True, turn_completed=True)
                store.update(job['id'], status=status, started=1,
                             result=json.dumps(receipt))
            else:
                receipt.update(observing_daemon_turn=True)
                store.update(job['id'], status='observing', started=1,
                             result=json.dumps(receipt))
        elif now - (job['launched'] or now) > 120:
            # Crash between submission and recording is ambiguous. Do not replay.
            store.update(job['id'], status='needs_review',
                         result='Worker disappeared without a verified turn outcome')


def launch_due(store, snapshots, codex_home, codex, now=None, max_workers=3):
    now = time.time() if now is None else now
    occupied = {job['thread'] for job in store.jobs(('launching', 'running', 'observing'))}
    available = max_workers - len(occupied)
    for job in store.jobs(('pending',)):
        if available <= 0:
            break
        if job['due'] > now or job['thread'] in occupied:
            continue
        snapshot = snapshots.get(job['thread'])
        if snapshot is None or not eligible_for_job(job, snapshot):
            continue
        try:
            resume_command(codex, json.loads(job['snapshot']), job['prompt'])
        except (ValueError, KeyError) as exc:
            store.update(job['id'], status='failed', result=str(exc))
            continue
        unit = 'codex-auto-resume-job-' + job['id']
        store.update(job['id'], status='launching', launched=now, unit=unit)
        command = ['systemd-run', '--user', '--quiet', '--collect', '--unit', unit,
                   '--property=Type=exec', '--property=UMask=0077',
                   '--property=KillMode=control-group', '--property=TimeoutStopSec=20',
                   '--setenv=CODEX_HOME=' + str(codex_home),
                   sys.executable, str(Path(__file__).resolve()),
                   '--state-dir', str(store.directory), '--codex-home', str(codex_home),
                   '--codex', codex, 'worker', job['id']]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            store.update(job['id'], status='pending', due=now + 60,
                         result='systemd worker launch failed: ' + result.stderr[:300])
        else:
            occupied.add(job['thread'])
            available -= 1
            log('launched', thread=job['thread'], job=job['id'], unit=unit)


def find_snapshot(codex_home, thread):
    for found, path in discover(codex_home):
        if found == thread:
            return read_rollout(path)[1]
    raise ValueError('Session not found in Codex index: ' + thread)


def worker(store, codex_home, codex, job_id):
    # Atomic claim also makes accidental repeated worker starts harmless.
    with store.db:
        claimed = store.db.execute("update jobs set status='running' where id=? and status='launching'",
                                   (job_id,)).rowcount
    if not claimed:
        return 0
    job = store.db.execute('select * from jobs where id=?', (job_id,)).fetchone()
    try:
        snapshot = find_snapshot(codex_home, job['thread'])
        if not eligible_for_job(job, snapshot):
            store.update(job_id, status='superseded', result='Quota failure resolved before worker submission')
            return 0
        saved = json.loads(job['snapshot'])
        command = resume_command(codex, saved, job['prompt'])
        path = store.directory / (job_id + '.jsonl')
        stderr_path = store.directory / (job_id + '.stderr.log')
        store.update(job_id, log=str(path))
        started = completed = thread_verified = False
        error = None
        with path.open('a', encoding='utf-8') as output, stderr_path.open('a') as stderr:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=stderr,
                                       text=True, cwd=saved['cwd'],
                                       env={**os.environ, 'CODEX_HOME': str(codex_home)})
            for line in process.stdout:
                output.write(line)
                output.flush()
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                kind = event.get('type')
                if kind == 'thread.started':
                    thread_verified = event.get('thread_id') == job['thread']
                    if not thread_verified:
                        error = {'message': 'Codex returned a different session ID'}
                        process.terminate()
                        break
                elif kind == 'turn.started':
                    started = True
                    store.update(job_id, started=1)
                    log('turn_started', thread=job['thread'], job=job_id)
                elif kind == 'turn.completed':
                    completed = True
                elif kind in ('turn.failed', 'error'):
                    error = event.get('error', event)
            exit_code = process.wait()
        current = find_snapshot(codex_home, job['thread'])
        end = current.get('end', {})
        if not started and 'already has an active writer' in stderr_path.read_text():
            return submit_to_loaded_daemon(store, job, codex_home)
        limited = changed_since_job(job, current) and end.get('usage_limit')
        if limited:
            status = 'usage_limited'
        elif thread_verified and started and completed and exit_code == 0 and not error:
            status = 'complete'
        elif started:
            status = 'needs_review' if not error else 'failed'
        else:
            status = 'failed'
        store.update(job_id, status=status,
                     result=json.dumps({'exit_code': exit_code, 'turn_started': started,
                                        'turn_completed': completed, 'thread_verified': thread_verified,
                                        'usage_limit': bool(limited)}))
        log('worker_finished', thread=job['thread'], job=job_id, status=status)
        return 0 if status in ('complete', 'usage_limited') else 1
    except (OSError, ValueError, KeyError) as exc:
        store.update(job_id, status='needs_review', result=str(exc)[:500])
        log('worker_error', job=job_id, error=str(exc)[:500])
        return 1


def watch(store, codex_home, codex, poll=10, once=False, wait=WAIT_SECONDS, grace=GRACE_SECONDS):
    lock = (store.directory / 'watch.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    log('watcher_started', poll_seconds=poll, wait_seconds=wait, grace_seconds=grace)
    while True:
        try:
            snapshots = scan(store, codex_home, wait=wait, grace=grace)
            reconcile(store, snapshots)
            launch_due(store, snapshots, codex_home, codex)
        except (OSError, sqlite3.Error, ValueError) as exc:
            log('watcher_error', error=str(exc)[:500])
        if once:
            break
        time.sleep(poll)
    lock.close()


def main(argv=None):
    os.umask(0o077)
    argv = list(sys.argv[1:] if argv is None else argv)
    # Preserve the user's existing `codex-auto-resume UUID HH:MM` interface.
    if argv and re.fullmatch(r'[0-9a-fA-F-]{36}', argv[0]):
        argv.insert(0, 'schedule')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path,
                        default=Path(os.environ.get('CODEX_AUTO_RESUME_STATE_DIR',
                                     str(Path.home() / '.local/state/codex-auto-resume'))))
    parser.add_argument('--codex-home', type=Path,
                        default=Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))))
    parser.add_argument('--codex', default=shutil.which('codex') or str(Path.home() / '.local/bin/codex'))
    commands = parser.add_subparsers(dest='action', required=True)
    watcher = commands.add_parser('watch')
    watcher.add_argument('--poll', type=float, default=10)
    watcher.add_argument('--once', action='store_true')
    watcher.add_argument('--wait-seconds', type=float, default=WAIT_SECONDS,
                         help='Retry delay; default 18000. Shorten only in isolated tests.')
    watcher.add_argument('--grace-seconds', type=float, default=GRACE_SECONDS)
    schedule = commands.add_parser('schedule')
    schedule.add_argument('thread')
    schedule.add_argument('reset', help='HH:MM in local time, or now')
    schedule.add_argument('--prompt', default=PROMPT)
    schedule.add_argument('--disable-hooks', action='store_true', help='For diagnostic sessions only')
    commands.add_parser('status')
    for name in ('cancel', 'exclude'):
        commands.add_parser(name).add_argument('thread')
    commands.add_parser('worker').add_argument('job')
    args = parser.parse_args(argv)
    store = Store(args.state_dir)
    if args.action == 'watch':
        if args.poll <= 0 or args.wait_seconds < 0 or args.grace_seconds < 0:
            parser.error('Poll must be positive and delays nonnegative')
        watch(store, args.codex_home, args.codex, args.poll, args.once,
              args.wait_seconds, args.grace_seconds)
    elif args.action == 'worker':
        return worker(store, args.codex_home, args.codex, args.job)
    elif args.action == 'schedule':
        try:
            thread = str(uuid.UUID(args.thread))
            snapshot = find_snapshot(args.codex_home, thread)
            if not unresolved_limit(snapshot):
                raise ValueError('Session is not currently stopped by a usage limit; refusing to resume')
            snapshot['disable_hooks'] = args.disable_hooks
            resume_command(args.codex, snapshot, args.prompt)
            due = parse_reset(args.reset)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        with store.db:
            store.db.execute('delete from exclusions where thread=?', (thread,))
            store.db.execute("update jobs set status='superseded',result='Replaced by manual schedule' "
                             "where thread=? and status='pending'", (thread,))
        job_id = store.enqueue(snapshot, 'manual:' + str(uuid.uuid4()), due, args.prompt)
        print('Session:', thread, '\nResume at:', datetime.fromtimestamp(due).astimezone().isoformat(),
              '\nJob:', job_id, '\nPersistent schedule saved; tmux/SSH may be closed.')
    elif args.action == 'status':
        for job in store.jobs():
            print(json.dumps({key: job[key] for key in ('id', 'thread', 'due', 'status', 'started',
                                                       'unit', 'log', 'result')}, ensure_ascii=False))
    else:
        thread = str(uuid.UUID(args.thread))
        with store.db:
            if args.action == 'exclude':
                store.db.execute('insert or ignore into exclusions values (?)', (thread,))
            store.db.execute("update jobs set status='cancelled', result='Cancelled by user' "
                             "where thread=? and status='pending'", (thread,))
        print('Pending schedules cancelled for', thread,
              '(future detection excluded)' if args.action == 'exclude' else '')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
