# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Exercise quota detection, durable deduplication and verified resume outcomes."""
import json
import socket
import sqlite3
import struct
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import codex_auto_resume as resume


THREAD = '01a105d7-62a9-7601-9d8c-40f01f1b951e'
TURN = '01a105db-610b-72c3-a9d4-a20ff597fa71'


def record(kind, payload, at):
    return {'timestamp': datetime.fromtimestamp(at, timezone.utc).isoformat(),
            'type': kind, 'payload': payload}


def append(path, kind, payload, at):
    with path.open('a') as stream:
        stream.write(json.dumps(record(kind, payload, at)) + '\n')


@pytest.fixture
def environment(tmp_path):
    codex_home = tmp_path / 'codex'
    codex_home.mkdir()
    path = codex_home / 'session.jsonl'
    now = time.time()
    append(path, 'session_meta', {'id': THREAD, 'cwd': str(tmp_path), 'source': 'cli'}, now - 100)
    append(path, 'turn_context', {'cwd': str(tmp_path), 'model': 'test-model', 'effort': 'high',
                                 'approval_policy': 'never',
                                 'sandbox_policy': {'type': 'danger-full-access'},
                                 'permission_profile': {'type': 'disabled'}}, now - 90)
    append(path, 'event_msg', {'type': 'task_started', 'turn_id': TURN}, now - 80)
    append(path, 'event_msg', {'type': 'task_complete', 'turn_id': TURN,
                             'error': {'codex_error_info': 'usage_limit_exceeded',
                                       'message': 'You’ve hit your usage limit.'}}, now - 60)
    conn = sqlite3.connect(codex_home / 'state_5.sqlite')
    conn.execute('create table threads (id text, rollout_path text, archived integer)')
    conn.execute('insert into threads values (?,?,0)', (THREAD, str(path)))
    conn.commit()
    conn.close()
    store = resume.Store(tmp_path / 'state')
    return SimpleNamespace(home=codex_home, path=path, store=store, now=now)


def test_five_hours_plus_grace_and_server_reset(environment):
    snapshots = resume.scan(environment.store, environment.home, now=environment.now)
    job, = environment.store.jobs()
    assert job['due'] == pytest.approx(environment.now - 60 + 18000 + 90)
    snapshot = snapshots[THREAD]
    snapshot['reset_at'] = environment.now + 7 * 3600
    assert resume.due_for_limit(snapshot) == environment.now + 7 * 3600 + 90
    snapshot['reset_at'] = environment.now + 3600
    assert resume.due_for_limit(snapshot) == environment.now + 3600 + 90


@pytest.mark.parametrize('clock,hour,minute,next_day', [
    ('1:56 PM', 13, 56, False), ('12:00 PM', 12, 0, False),
    ('12:10 AM', 0, 10, True), ('03:09 AM', 3, 9, True),
    ('13:56', 13, 56, False), ('10:27 AM', 10, 27, False)])
def test_usage_retry_clock_is_relative_to_failure(clock, hour, minute, next_day):
    failed = datetime(2026, 10, 4, 10, 27, 35).astimezone()
    error = {'codex_error_info': 'usage_limit_exceeded', 'message': 'Try again at ' + clock + '.'}
    expected = failed.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_day:
        from datetime import timedelta
        expected += timedelta(days=1)
    assert resume.reset_from_error(error, failed.timestamp()) == expected.timestamp()


def test_error_clock_ignored_for_other_errors_and_stale_window_cleared():
    failed = time.time()
    assert resume.reset_from_error({'message': 'Network failed; try again at 1:56 PM.'}, failed) == 0
    assert resume.reset_from_error({'codex_error_info': 'usage_limit_exceeded',
                                    'message': 'Try again at 25:99 PM.'}, failed) == 0
    assert resume.reset_from_error({'codex_error_info': 'usage_limit_exceeded',
                                    'resets_at': failed + 10}, failed) == failed + 10
    snapshot = {'reset_at': failed + 86400}
    resume.apply_record(snapshot, record('event_msg', {'type': 'task_started', 'turn_id': 'new'}, failed))
    assert snapshot['reset_at'] == 0


def test_parser_upgrade_corrects_pending_due_without_duplicate_or_lost_exclusion(environment):
    resume.scan(environment.store, environment.home)
    before = environment.store.jobs()[0]
    with environment.store.db:
        environment.store.db.execute("update metadata set value='1' where key='rollout_parser_version'")
        environment.store.db.execute('insert into exclusions values (?)', ('unrelated-thread',))
    error = {'codex_error_info': 'usage_limit_exceeded', 'resets_at': environment.now + 60}
    append(environment.path, 'event_msg', {'type': 'task_complete', 'turn_id': TURN, 'error': error},
           environment.now - 60)
    upgraded = resume.Store(environment.store.directory)
    assert not upgraded.db.execute('select * from cursors').fetchall()
    assert upgraded.db.execute('select * from exclusions').fetchall()
    resume.scan(upgraded, environment.home)
    after, = upgraded.jobs()
    assert after['id'] == before['id']
    assert after['due'] == pytest.approx(environment.now + 150)
    assert json.loads(after['snapshot'])['end']['reset_at'] == environment.now + 60


def test_restarts_and_multiple_polls_never_duplicate(environment):
    resume.scan(environment.store, environment.home)
    another = resume.Store(environment.store.directory)
    resume.scan(another, environment.home)
    assert len(another.jobs()) == 1


def test_user_resumption_supersedes_pending_job(environment):
    resume.scan(environment.store, environment.home)
    append(environment.path, 'event_msg', {'type': 'task_started', 'turn_id': 'new'}, environment.now)
    snapshots = resume.scan(environment.store, environment.home)
    resume.reconcile(environment.store, snapshots)
    assert environment.store.jobs()[0]['status'] == 'superseded'


def test_partial_append_and_invalid_line_are_not_lost(environment):
    offset, before = resume.read_rollout(environment.path)
    text = json.dumps(record('event_msg', {'type': 'task_started', 'turn_id': 'new'}, environment.now))
    with environment.path.open('a') as stream:
        stream.write('not json\n' + text[:20])
    offset2, snapshot = resume.read_rollout(environment.path, offset, before)
    assert snapshot == before
    with environment.path.open('a') as stream:
        stream.write(text[20:] + '\n')
    _, snapshot = resume.read_rollout(environment.path, offset2, snapshot)
    assert snapshot['start']['turn'] == 'new'


@pytest.mark.parametrize('error', [None, {'codex_error_info': 'context_window_exceeded'},
                                  {'message': 'stream disconnected'},
                                  {'message': 'You have exceeded your context length'}])
def test_other_failures_do_not_schedule(error):
    assert not resume.is_usage_limit(error)


def test_old_stale_errors_and_subagent_errors_not_resumed(environment):
    _, snapshot = resume.read_rollout(environment.path)
    snapshot['subagent'] = True
    assert not resume.unresolved_limit(snapshot)
    snapshot['subagent'] = False
    snapshot['created'] = environment.now
    assert not resume.unresolved_limit(snapshot)  # Inherited fork error predates fork.
    resume.scan(environment.store, environment.home, now=environment.now + 2 * 86400)
    resume.scan(environment.store, environment.home, now=environment.now + 2 * 86400)
    assert not environment.store.jobs()


def test_new_error_during_long_service_outage_is_not_lost(environment):
    resume.scan(environment.store, environment.home, now=environment.now + 2 * 86400)
    append(environment.path, 'event_msg', {'type': 'task_started', 'turn_id': 'second'}, environment.now)
    append(environment.path, 'event_msg', {'type': 'task_complete', 'turn_id': 'second',
                                         'error': {'codex_error_info': 'usage_limit_exceeded'}},
           environment.now + 10)
    resume.scan(environment.store, environment.home, now=environment.now + 2 * 86400)
    assert len(environment.store.jobs()) == 1


def test_permissions_from_actual_turn_survive_tui_resume(environment):
    append(environment.path, 'event_msg', {'type': 'thread_settings_applied', 'thread_settings': {
        'permission_profile': {'type': 'managed'}, 'sandbox_policy': {'type': 'workspace-write'}}},
           environment.now)
    _, snapshot = resume.read_rollout(environment.path)
    command = resume.resume_command('/usr/bin/codex', snapshot, 'continue')
    assert command[command.index('-s') + 1] == 'danger-full-access'
    assert command[-4:] == ['resume', '--json', THREAD, 'continue']
    assert snapshot['cwd'] in command
    snapshot.pop('sandbox_policy')
    snapshot.pop('permission_profile')
    with pytest.raises(ValueError, match='permissions'):
        resume.resume_command('codex', snapshot, 'continue')


def test_calendar_time_and_grace_boundary():
    now = datetime(2026, 10, 4, 3, 10, 30, tzinfo=timezone.utc)
    assert resume.parse_reset('03:10', now) == now.timestamp() + 60
    assert resume.parse_reset('now', now) == now.timestamp()
    later = now.replace(minute=12)
    assert resume.parse_reset('03:10', later) > later.timestamp() + 23 * 3600
    with pytest.raises(ValueError):
        resume.parse_reset('25:10', now)


def test_cancelled_event_stays_cancelled_and_exclusions_work(environment):
    resume.scan(environment.store, environment.home)
    job = environment.store.jobs()[0]
    environment.store.update(job['id'], status='cancelled')
    resume.scan(environment.store, environment.home)
    assert len(environment.store.jobs()) == 1
    assert environment.store.jobs()[0]['status'] == 'cancelled'
    with environment.store.db:
        environment.store.db.execute('insert into exclusions values (?)', (THREAD,))
    assert resume.scan(environment.store, environment.home) == {}


def test_repeated_limit_schedules_next_five_hour_retry(environment):
    resume.scan(environment.store, environment.home)
    environment.store.update(environment.store.jobs()[0]['id'], status='usage_limited')
    append(environment.path, 'event_msg', {'type': 'task_started', 'turn_id': 'second'}, environment.now)
    append(environment.path, 'event_msg', {'type': 'task_complete', 'turn_id': 'second',
                                         'error': {'codex_error_info': 'usage_limit_exceeded'}},
           environment.now + 10)
    resume.scan(environment.store, environment.home)
    assert len(environment.store.jobs()) == 2
    assert environment.store.jobs()[1]['due'] == pytest.approx(environment.now + 10 + 18090)


def test_recover_completed_or_running_turn_after_worker_disappears(environment):
    resume.scan(environment.store, environment.home)
    job = environment.store.jobs()[0]
    environment.store.update(job['id'], status='running', launched=environment.now, unit='test')
    append(environment.path, 'event_msg', {'type': 'task_started', 'turn_id': 'new'}, environment.now)
    snapshots = resume.scan(environment.store, environment.home)
    resume.reconcile(environment.store, snapshots, active=lambda unit: False)
    assert environment.store.jobs()[0]['status'] == 'observing'
    append(environment.path, 'event_msg', {'type': 'task_complete', 'turn_id': 'new'}, environment.now + 1)
    resume.reconcile(environment.store, resume.scan(environment.store, environment.home), active=lambda unit: False)
    assert environment.store.jobs()[0]['status'] == 'complete'


def test_ambiguous_worker_crash_does_not_duplicate_submission(environment):
    snapshots = resume.scan(environment.store, environment.home)
    job = environment.store.jobs()[0]
    environment.store.update(job['id'], status='running', launched=environment.now - 200, unit='test')
    resume.reconcile(environment.store, snapshots, active=lambda unit: False)
    assert environment.store.jobs()[0]['status'] == 'needs_review'


def test_dispatch_uses_independent_systemd_worker_and_does_not_double_launch(environment, monkeypatch):
    snapshots = resume.scan(environment.store, environment.home, wait=0, grace=0)
    calls = []
    monkeypatch.setattr(resume.subprocess, 'run', lambda command, **kwargs:
                        calls.append(command) or SimpleNamespace(returncode=0, stderr=''))
    resume.launch_due(environment.store, snapshots, environment.home, '/usr/bin/codex')
    resume.launch_due(environment.store, snapshots, environment.home, '/usr/bin/codex')
    assert len(calls) == 1
    assert calls[0][0] == 'systemd-run'
    assert environment.store.jobs()[0]['status'] == 'launching'


@pytest.mark.parametrize('outcome,expected', [('complete', 'complete'), ('no-events', 'failed'),
                                              ('error', 'failed'), ('limit', 'usage_limited'),
                                              ('different-thread', 'failed')])
def test_real_worker_process_requires_events_and_handles_limit(environment, tmp_path, outcome, expected):
    # A real subprocess emits the same public JSON events; no OpenAI calls.
    executable = tmp_path / 'fake-codex'
    executable.write_text('#!/usr/bin/env python3\nimport json\nfrom pathlib import Path\n'
                          + f'print(json.dumps({{"type":"thread.started","thread_id":{("wrong-thread" if outcome == "different-thread" else THREAD)!r}}}))\n'
                          + ('print(json.dumps({"type":"turn.started"}))\n' if outcome != 'no-events' else '')
                          + ('print(json.dumps({"type":"turn.completed"}))\n' if outcome == 'complete' else '')
                          + ('print(json.dumps({"type":"turn.failed","error":{"message":"failed"}}))\n' if outcome == 'error' else '')
                          + (f'p=Path({str(environment.path)!r})\n'
                             f'with p.open("a") as s:\n'
                             f' s.write({json.dumps(record("event_msg", {"type": "task_started", "turn_id": "worker"}, environment.now))!r}+"\\n")\n'
                             f' s.write({json.dumps(record("event_msg", {"type": "task_complete", "turn_id": "worker", "error": {"codex_error_info": "usage_limit_exceeded"}}, environment.now + 1))!r}+"\\n")\n'
                             'print(json.dumps({"type":"turn.failed","error":{"message":"usage limit"}}))\n'
                             if outcome == 'limit' else ''))
    executable.chmod(0o700)
    resume.scan(environment.store, environment.home, wait=0, grace=0)
    job = environment.store.jobs()[0]
    environment.store.update(job['id'], status='launching', launched=environment.now, unit='test')
    resume.worker(environment.store, environment.home, str(executable), job['id'])
    assert environment.store.jobs()[0]['status'] == expected
    assert resume.worker(environment.store, environment.home, str(executable), job['id']) == 0


def test_worker_rechecks_user_turn_before_submitting(environment):
    resume.scan(environment.store, environment.home)
    job = environment.store.jobs()[0]
    environment.store.update(job['id'], status='launching')
    append(environment.path, 'event_msg', {'type': 'task_started', 'turn_id': 'user'}, environment.now)
    assert resume.worker(environment.store, environment.home, '/does/not/exist', job['id']) == 0
    assert environment.store.jobs()[0]['status'] == 'superseded'


@pytest.mark.parametrize('ending', ['complete', 'aborted', 'network-error'])
def test_resolved_quota_never_runs_even_without_a_new_start(environment, monkeypatch, ending):
    resume.scan(environment.store, environment.home, wait=0, grace=0)
    job = environment.store.jobs()[0]
    payload = {'type': 'turn_aborted' if ending == 'aborted' else 'task_complete', 'turn_id': TURN}
    if ending == 'network-error':
        payload['error'] = {'message': 'stream disconnected'}
    append(environment.path, 'event_msg', payload, environment.now)
    snapshots = resume.scan(environment.store, environment.home)
    monkeypatch.setattr(resume.subprocess, 'run', lambda *a, **k: pytest.fail('Unexpected worker launch'))
    resume.launch_due(environment.store, snapshots, environment.home, '/does/not/exist')
    assert environment.store.jobs()[0]['status'] == 'pending'
    resume.reconcile(environment.store, snapshots)
    assert environment.store.jobs()[0]['status'] == 'superseded'
    environment.store.update(job['id'], status='launching')
    assert resume.worker(environment.store, environment.home, '/does/not/exist', job['id']) == 0
    assert environment.store.jobs()[0]['status'] == 'superseded'
    calls = []
    class Client:
        def __init__(self, home):
            pass
        def call(self, method, params):
            calls.append(method)
            assert method == 'thread/read'
            return {'thread': {'id': THREAD, 'status': {'type': 'idle'}}}
        def close(self):
            pass
    monkeypatch.setattr(resume, 'DaemonClient', Client)
    assert resume.submit_to_loaded_daemon(environment.store, job, environment.home) == 0
    assert calls == ['thread/read']
    assert environment.store.jobs()[0]['status'] == 'superseded'


def test_manual_schedule_also_refuses_a_normal_completed_session(environment):
    append(environment.path, 'event_msg', {'type': 'task_complete', 'turn_id': TURN}, environment.now)
    with pytest.raises(SystemExit) as error:
        resume.main(['--codex-home', str(environment.home), '--state-dir', str(environment.store.directory),
                     'schedule', THREAD, 'now'])
    assert error.value.code == 2
    assert not environment.store.jobs()


def test_install_retains_old_command_and_service_restarts():
    root = Path(__file__).resolve().parents[1]
    installer = (root / 'bootstrap/install_codex_auto_resume.sh').read_text()
    unit = (root / 'bootstrap/codex-auto-resume.service').read_text()
    assert 'original-' in installer and 'ln -sfn' in installer
    assert 'enable --now codex-auto-resume.service' in installer
    assert 'Restart=always' in unit and 'UMask=0077' in unit


def socket_client():
    local, peer = socket.socketpair()
    client = resume.DaemonClient.__new__(resume.DaemonClient)
    client.socket, client.buffer, client.sequence = local, b'', 0
    local.settimeout(1)
    peer.settimeout(1)
    return client, peer


def receive_masked_frame(peer):
    def read(length):
        data = b''
        while len(data) < length:
            data += peer.recv(length - len(data))
        return data
    first, second = read(2)
    assert second & 0x80
    length = second & 0x7f
    if length == 126:
        length = struct.unpack('!H', read(2))[0]
    elif length == 127:
        length = struct.unpack('!Q', read(8))[0]
    mask, data = read(4), read(length)
    return first & 0xf, bytes(value ^ mask[index % 4] for index, value in enumerate(data))


@pytest.mark.parametrize('size', [12, 1000, 70000])
def test_daemon_client_masks_short_and_extended_frames(size):
    client, peer = socket_client()
    try:
        client.send_frame(b'x' * size)
        opcode, payload = receive_masked_frame(peer)
        assert opcode == 1 and payload == b'x' * size
    finally:
        client.close()
        peer.close()


def test_daemon_client_handles_fragmentation_and_ping():
    client, peer = socket_client()
    try:
        peer.sendall(b'\x01\x06{"ok":' + b'\x89\x01p' + b'\x80\x05true}')
        assert client.receive() == {'ok': True}
        assert receive_masked_frame(peer) == (10, b'p')
    finally:
        client.close()
        peer.close()


def test_daemon_client_bounds_messages():
    client, peer = socket_client()
    try:
        peer.sendall(b'\x81\x7f' + struct.pack('!Q', 17 * 1024 * 1024))
        with pytest.raises(ValueError, match='Oversized'):
            client.receive()
    finally:
        client.close()
        peer.close()


@pytest.mark.parametrize('runtime_state,expected', [('idle', 'observing'), ('systemError', 'observing'),
                                                  ('active', 'superseded'), ('notLoaded', 'pending')])
def test_writer_conflict_submits_to_same_loaded_daemon(environment, monkeypatch, runtime_state, expected):
    resume.scan(environment.store, environment.home)
    job = environment.store.jobs()[0]
    calls = []
    class Client:
        def __init__(self, home):
            assert home == environment.home
        def call(self, method, params):
            calls.append((method, params))
            if method == 'thread/read':
                return {'thread': {'id': THREAD, 'status': {'type': runtime_state}}}
            return {'turn': {'id': 'submitted-turn', 'status': 'inProgress'}}
        def close(self):
            pass
    monkeypatch.setattr(resume, 'DaemonClient', Client)
    assert resume.submit_to_loaded_daemon(environment.store, job, environment.home) == 0
    assert environment.store.jobs()[0]['status'] == expected
    if expected == 'observing':
        method, params = calls[-1]
        assert method == 'turn/start' and params['threadId'] == THREAD
        assert params['sandboxPolicy'] == {'type': 'dangerFullAccess'}
        assert params['approvalPolicy'] == 'never'
        assert json.loads(environment.store.jobs()[0]['result'])['thread_verified']
    else:
        assert len(calls) == 1


def test_worker_uses_daemon_only_for_pre_submission_writer_conflict(environment, monkeypatch, tmp_path):
    executable = tmp_path / 'locked-codex'
    executable.write_text('#!/usr/bin/env python3\nimport sys\n'
                          'sys.stderr.write("already has an active writer")\nsys.exit(1)\n')
    executable.chmod(0o700)
    resume.scan(environment.store, environment.home)
    job = environment.store.jobs()[0]
    environment.store.update(job['id'], status='launching')
    calls = []
    def submit(store, saved, home):
        calls.append(saved['thread'])
        store.update(saved['id'], status='observing', started=1)
        return 0
    monkeypatch.setattr(resume, 'submit_to_loaded_daemon', submit)
    assert resume.worker(environment.store, environment.home, str(executable), job['id']) == 0
    assert calls == [THREAD]
    assert environment.store.jobs()[0]['status'] == 'observing'
