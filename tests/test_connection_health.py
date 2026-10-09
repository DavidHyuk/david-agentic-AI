# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Verify external outage detection, privacy, deduplication and delivery retries."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import connection_health as health

NOW = datetime(2026, 10, 9, 18, tzinfo=timezone.utc)


def write(home, relative, document):
    path = home / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document))
    return path


def observed(service='chatgpt_sync', status='failed', reason='sync_failed'):
    return health.observation(service, status, reason if status == 'failed' else None)


def test_unconfigured_accounts_do_not_generate_alerts(tmp_path):
    def runner(*args, **kwargs):
        pytest.fail('Unconfigured accounts must not launch probes or logins.')
    rows = health.collect_connections(tmp_path, runner=runner, now=NOW)
    assert len(rows) == 5 and all(row['status'] == 'unknown' for row in rows)
    state = {}
    assert health.update_incidents(state, rows, NOW) == []


def test_chatgpt_sync_and_auth_failures_are_fixed_descriptions(tmp_path):
    write(tmp_path, 'data/chatgpt/daily-sync.json', {'status': 'error', 'error': 'SECRET_COOKIE private chat text'})
    write(tmp_path, 'data/chatgpt/browser-status.json', {'authenticated_at': '2026-10-08T18:00:00+00:00',
        'login_requested_at': '2026-10-09T18:00:00+00:00', 'email': 'private@example.com'})
    rows = health.collect_connections(tmp_path, now=NOW)
    by_service = {row['service']: row for row in rows}
    assert by_service['chatgpt_sync']['reason'] == 'sync_failed'
    assert by_service['chatgpt_account']['reason'] == 'reauth_required'
    state = {}
    message = health.notice_message(health.update_incidents(state, rows, NOW))
    assert 'ChatGPT' in message and '다시 연결' in message
    assert 'SECRET_COOKIE' not in message + json.dumps(state)
    assert 'private' not in message + json.dumps(state)


@pytest.mark.parametrize('status,reason', [('reauth_required', 'reauth_required'), ('error', 'sync_failed')])
def test_leetcode_source_failure(tmp_path, status, reason):
    write(tmp_path, 'data/interview/leetcode_history.json', {'solution_sync_status': status})
    row = next(row for row in health.collect_connections(tmp_path, now=NOW) if row['service'] == 'leetcode')
    assert row['status'] == 'failed' and row['reason'] == reason


def test_youtube_sync_failure_overrides_old_verified_connection(tmp_path):
    write(tmp_path, 'data/youtube-history/authentication.json', {'verified_at': NOW.isoformat()})
    write(tmp_path, 'data/youtube-history/sync-status.json', {'status': 'error', 'error_code': 'reauth_required'})
    row = next(row for row in health.collect_connections(tmp_path, now=NOW) if row['service'] == 'youtube')
    assert row['status'] == 'failed' and row['reason'] == 'reauth_required'
    write(tmp_path, 'data/youtube-history/sync-status.json', {'status': 'ok', 'last_success_at': NOW.isoformat()})
    row = next(row for row in health.collect_connections(tmp_path, now=NOW) if row['service'] == 'youtube')
    assert row['status'] == 'healthy'


def test_later_verification_supersedes_old_failed_login():
    documents = {'login': {'status': 'failed'}, 'login_updated_at': NOW.timestamp() - 30}
    assert health.account_observation('youtube', documents)['status'] == 'failed'
    assert health.account_observation('youtube', documents, NOW.timestamp())['status'] == 'healthy'


@pytest.mark.parametrize('unit_active,probe_code,reason', [
    (True, 0, None), (True, 1, 'public_unreachable'), (False, 0, 'collector_down')])
def test_kakao_checks_collector_and_public_probe_without_secret_arguments(tmp_path, unit_active, probe_code, reason):
    path = tmp_path / 'data/english/kakao-skill-url.txt'
    path.parent.mkdir(parents=True)
    path.write_text('https://private.ts.net:10000/kakao/SECRET_ENDPOINT')
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        if command[0] == 'systemctl':
            return SimpleNamespace(returncode=0 if unit_active else 3, stdout='active' if unit_active else 'inactive')
        assert '--probe-only' in command and 'SECRET_ENDPOINT' not in str(command)
        return SimpleNamespace(returncode=probe_code)
    row = next(row for row in health.collect_connections(tmp_path, runner=runner, now=NOW) if row['service'] == 'kakao')
    assert row['reason'] == reason
    assert row['status'] == ('healthy' if reason is None else 'failed')
    assert len(calls) == (2 if unit_active else 1)


def test_public_network_failure_requires_two_consecutive_checks():
    state = {}
    failed = [observed('kakao', reason='public_unreachable')]
    assert health.update_incidents(state, failed, NOW) == []
    assert health.update_incidents(state, [observed('kakao', 'unknown')], NOW) == []
    assert health.update_incidents(state, failed, NOW) == []
    assert len(health.update_incidents(state, failed, NOW)) == 1
    health.update_incidents(state, failed, NOW)
    assert len(state['events']) == 1


def test_unknown_state_never_claims_recovery():
    state = {}
    health.update_incidents(state, [observed()], NOW)
    health.update_incidents(state, [observed(status='unknown')], NOW + timedelta(minutes=5))
    assert state['services']['chatgpt_sync']['incident_open']
    assert len(state['events']) == 1


def test_notification_failure_retries_and_recovery_reopens_next_incident(tmp_path):
    sent = []
    delivery_results = iter([False, True, True, True])
    def sender(home, message):
        assert home == tmp_path
        sent.append(message)
        return next(delivery_results)
    state = health.check_and_notify(tmp_path, [observed()], now=NOW, sender=sender)
    assert state['pending'] and state['last_delivery_ok'] is False
    state = health.check_and_notify(tmp_path, [observed()], now=NOW, sender=sender)
    assert state['pending'] == [] and len(state['events']) == 1
    assert sent[0] == sent[1]
    health.check_and_notify(tmp_path, [observed()], now=NOW, sender=sender)
    assert len(sent) == 2
    state = health.check_and_notify(tmp_path, [observed(status='healthy')], now=NOW, sender=sender)
    assert '복구 확인' in sent[-1] and len(state['events']) == 2
    state = health.check_and_notify(tmp_path, [observed()], now=NOW, sender=sender)
    assert len(sent) == 4 and len(state['events']) == 3
    assert (tmp_path / 'data/observatory/connection-health.json').stat().st_mode & 0o777 == 0o600


def test_delivery_batches_large_pending_history(tmp_path):
    events = [{'service': 'youtube', 'label': 'YouTube', 'kind': 'failed',
               'reason': 'sync_failed', 'time': NOW.isoformat()}] * 20
    write(tmp_path, 'data/observatory/connection-health.json', {'services': {}, 'events': events, 'pending': events})
    sent = []
    state = health.check_and_notify(tmp_path, [], now=NOW, sender=lambda home, message: sent.append(message) or True)
    assert len(state['pending']) == 12 and len(sent[0]) < 4000


def test_sender_uses_david_home_and_strips_inherited_profile_and_routes(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_PROFILE', 'english')
    monkeypatch.setenv('TELEGRAM_HOME_CHANNEL', 'SECRET_OTHER_CHAT')
    monkeypatch.setenv('HERMES_CRON_CHAT_ID', 'SECRET_OTHER_CHAT')
    def runner(command, **kwargs):
        assert command == ['hermes', 'send', '--to', 'telegram', '--quiet']
        assert kwargs['input'] == 'safe notice'
        assert kwargs['env']['HERMES_HOME'] == str(tmp_path)
        assert 'HERMES_PROFILE' not in kwargs['env']
        assert 'TELEGRAM_HOME_CHANNEL' not in kwargs['env']
        assert 'HERMES_CRON_CHAT_ID' not in kwargs['env']
        return SimpleNamespace(returncode=0)
    assert health.send_notice(tmp_path, 'safe notice', runner=runner)
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('contains-private-token', 20)
    assert not health.send_notice(tmp_path, 'safe notice', runner=timeout)


def test_external_cron_failure_ignores_disabled_jobs_and_raw_errors(tmp_path):
    write(tmp_path, 'cron/jobs.json', {'jobs': [
        {'name': 'chatgpt-project-sync', 'last_status': 'error', 'last_error': 'SECRET'},
        {'name': 'papers-catalog-sync', 'last_status': 'failed', 'enabled': False},
        {'name': 'coding-coach', 'last_status': 'error'}]})
    rows = health.collect_external_jobs(tmp_path)
    assert len(rows) == 1 and rows[0]['service'] == 'job:david:chatgpt-project-sync'
    state = {}
    assert 'SECRET' not in health.notice_message(health.update_incidents(state, rows, NOW))


def test_corrupt_source_is_observable_without_resetting_it(tmp_path):
    path = tmp_path / 'data/chatgpt/daily-sync.json'
    path.parent.mkdir(parents=True)
    path.write_text('SECRET broken json')
    rows = health.collect_connections(tmp_path, now=NOW)
    assert any(row['reason'] == 'state_unreadable' for row in rows)
    assert path.read_text() == 'SECRET broken json'
    assert 'SECRET' not in json.dumps(rows)


def test_running_sync_reports_stall_after_two_hours():
    document = {'status': 'running', 'last_attempt_at': (NOW - timedelta(hours=3)).isoformat()}
    assert health.sync_observation('chatgpt_sync', document, NOW)['reason'] == 'sync_stalled'
    assert health.sync_observation('chatgpt_sync', document, NOW - timedelta(hours=2))['status'] == 'unknown'


def test_chatgpt_source_and_job_failure_form_one_incident():
    rows = health.combine_observations([observed()], [{'service': 'job:david:chatgpt-project-sync',
        'label': 'ChatGPT automatic sync', 'status': 'failed', 'reason': 'sync_failed'}])
    assert len(rows) == 1 and rows[0]['service'] == 'chatgpt_sync'
    state = {}
    assert len(health.update_incidents(state, rows, NOW)) == 1
    assert health.notice_message(state['pending']).count('장애 감지') == 1


@pytest.mark.parametrize('source_age,job_status,expected', [
    (0, 'failed', 'healthy'), (2, 'failed', 'failed'), (0, 'ok', 'healthy'),
])
def test_recovery_uses_newest_source_or_job_evidence(tmp_path, source_age, job_status, expected):
    write(tmp_path, 'data/chatgpt/daily-sync.json', {'status': 'ok',
        'last_success_at': (NOW - timedelta(hours=source_age)).isoformat()})
    write(tmp_path, 'cron/jobs.json', {'jobs': [{'name': 'chatgpt-project-sync',
        'last_status': job_status, 'last_run_at': (NOW - timedelta(hours=1)).isoformat()}]})
    rows = health.combine_observations(health.collect_connections(tmp_path, now=NOW), health.collect_external_jobs(tmp_path))
    syncs = [row for row in rows if row['service'] == 'chatgpt_sync']
    assert len(syncs) == 1 and syncs[0]['status'] == expected


def test_old_duplicate_incidents_migrate_without_a_second_failure_or_recovery():
    state = {'services': {name: {'incident_open': True, 'failure_count': 3}
                         for name in ('chatgpt_sync', 'job:david:chatgpt-project-sync')},
             'events': [], 'pending': []}
    health.update_incidents(state, [observed()], NOW)
    assert 'job:david:chatgpt-project-sync' not in state['services']
    assert state['events'] == []
    health.update_incidents(state, [observed(status='healthy')], NOW)
    assert len(state['events']) == 1 and state['events'][0]['kind'] == 'recovered'


def test_pending_alias_notices_deduplicate_without_dropping_later_incidents():
    event = {'service': 'chatgpt_sync', 'label': 'ChatGPT', 'kind': 'failed',
             'reason': 'sync_failed', 'time': NOW.isoformat()}
    state = {'pending': [event, {**event, 'service': 'job:david:chatgpt-project-sync'},
                         {**event, 'kind': 'recovered', 'reason': None,
                          'time': (NOW + timedelta(minutes=5)).isoformat()}]}
    health.migrate_incident_aliases(state)
    assert len(state['pending']) == 2
    assert [event['kind'] for event in state['pending']] == ['failed', 'recovered']


def test_read_only_cli_and_notification_failure_are_fail_open(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(health, 'collect_connections', lambda home: [observed()])
    assert health.main(['--home', str(tmp_path)]) == 0
    assert 'connections' in capsys.readouterr().out
    assert not (tmp_path / 'data/observatory/connection-health.json').exists()
    monkeypatch.setattr(health, 'check_and_notify', lambda *a, **k: (_ for _ in ()).throw(OSError('SECRET')))
    assert health.main(['--home', str(tmp_path), '--notify']) == 0
    assert 'SECRET' not in capsys.readouterr().err
