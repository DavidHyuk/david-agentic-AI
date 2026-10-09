#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Notify Hermes HQ about observed external connection failures and recoveries.

Standalone watchdog helper: read existing account/sync evidence, probe the Kakao
public collector without feedback, and send through David's existing Telegram
home. No gateway restart, browser login, credential changes, or new bot. Only
fixed descriptions enter notices/state; source errors and private URLs do not.
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

SERVICES = {
    'chatgpt_sync': ('ChatGPT 채팅룸 동기화', 'Hermes HQ 또는 Jun의 ChatGPT 연결 상태를 확인하고 동기화를 재시도하세요.'),
    'chatgpt_account': ('ChatGPT 계정 연결', 'Hermes HQ → 계정·연결 설정 → ChatGPT 다시 연결을 사용하세요.'),
    'youtube': ('YouTube 계정·시청 기록', 'Rina → 계정·연결 설정 → Google 다시 연결을 사용하세요.'),
    'leetcode': ('LeetCode 계정·제출 코드', 'Jun → 계정·연결 설정 → LeetCode 다시 연결을 사용하세요.'),
    'kakao': ('카카오톡 영어 피드백 수신', 'Ellie의 연결 상태와 카카오 Open Builder의 스킬 URL·배포 상태를 확인하세요.'),
}
REASONS = {
    'sync_failed': '최근 외부 자료 갱신이 실패했습니다. 기존 자료는 보존됩니다.',
    'reauth_required': '저장된 계정 연결을 다시 인증해야 합니다.',
    'login_failed': '계정 연결 또는 로그인 검증이 실패했습니다.',
    'collector_down': '로컬 카카오 수신 서비스가 실행되지 않고 있습니다.',
    'public_unreachable': '카카오 공개 수신 경로의 응답을 확인하지 못했습니다.',
    'probe_failed': '카카오 공개 연결 검사 실행에 실패했습니다.',
    'state_unreadable': '저장된 연결 상태를 읽을 수 없습니다.',
    'sync_stalled': '자료 갱신이 2시간 이상 실행 중인 상태로 남아 있습니다.',
}


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict):
        raise ValueError('Invalid status document.')
    return value


def stamp(value) -> float:
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.timestamp() if parsed.tzinfo else 0
    except (ValueError, TypeError):
        return 0


def observation(service: str, status: str, reason: str | None = None) -> dict:
    return {'service': service, 'status': status, 'reason': reason}


def sync_observation(service: str, document: dict, now: datetime) -> dict:
    status = document.get('status')
    if status in ('error', 'failed'):
        return observation(service, 'failed', 'reauth_required' if
                           document.get('error_code') == 'reauth_required' else 'sync_failed')
    if status == 'ok':
        return observation(service, 'healthy')
    if status == 'running' and stamp(document.get('last_attempt_at')):
        if now.timestamp() - stamp(document['last_attempt_at']) > 7200:
            return observation(service, 'failed', 'sync_stalled')
    return observation(service, 'unknown')


def account_observation(service: str, documents: dict, latest_success: float = 0) -> dict:
    login = documents.get('login', {})
    phase = login.get('browser_status', login.get('status'))
    verified = max(latest_success, stamp(login.get('authenticated_at')),
                   stamp(login.get('completed_at')),
                   stamp(documents.get('authentication', {}).get('verified_at')),
                   stamp(documents.get('connection', {}).get('verified_at')))
    if phase in ('starting', 'awaiting_login', 'verifying', 'syncing'):
        return observation(service, 'unknown')
    if phase == 'failed' and documents.get('login_updated_at', 0) > verified:
        return observation(service, 'failed', 'login_failed')
    if stamp(login.get('login_requested_at')) > verified:
        return observation(service, 'failed', 'reauth_required')
    return observation(service, 'healthy' if verified else 'unknown')


def collect_connections(home: Path, *, runner=subprocess.run, now: datetime | None = None) -> list:
    now = now or datetime.now(timezone.utc)
    results = []
    root = home / 'data'
    for service, directory, login_name in (
            ('chatgpt_account', 'chatgpt', 'browser-status.json'),
            ('youtube', 'youtube-history', 'login-status.json')):
        try:
            folder = root / directory
            sync = read_json(folder / ('daily-sync.json' if service == 'chatgpt_account' else 'sync-status.json'))
            login_path = folder / login_name
            documents = {'login': read_json(login_path),
                         'login_updated_at': login_path.stat().st_mtime if login_path.exists() else 0}
            if service == 'youtube':
                documents.update(authentication=read_json(folder / 'authentication.json'),
                                 connection=read_json(folder / 'connection.json'))
            account = account_observation(service, documents, stamp(sync.get('last_success_at')))
            synced = sync_observation('chatgpt_sync' if service == 'chatgpt_account' else service, sync, now)
            if service == 'chatgpt_account':
                results += [account, synced]
            else:
                results.append(synced if synced['status'] == 'failed' or
                               account['status'] == 'unknown' else account)
        except (OSError, ValueError, TypeError):
            results.append(observation(service, 'failed', 'state_unreadable'))
            if service == 'chatgpt_account':
                results.append(observation('chatgpt_sync', 'unknown'))
    try:
        source = read_json(root / 'interview/leetcode_history.json')
        phase = source.get('solution_sync_status')
        status = ('failed' if phase in ('reauth_required', 'error', 'failed') else
                  'healthy' if phase == 'ok' else 'unknown')
        reason = 'reauth_required' if phase == 'reauth_required' else 'sync_failed' if status == 'failed' else None
        login_path = root / 'interview/leetcode-login-status.json'
        login = read_json(login_path)
        if (status != 'failed' and login.get('status') == 'failed'
                and login_path.stat().st_mtime > stamp(source.get('synced_at'))):
            status, reason = 'failed', 'login_failed'
        results.append(observation('leetcode', status, reason))
    except (OSError, ValueError, TypeError):
        results.append(observation('leetcode', 'failed', 'state_unreadable'))
    configured = any((root / 'english' / name).exists() for name in
                     ('kakao-skill-url.txt', 'kakao-public-origin.txt'))
    if not configured:
        results.append(observation('kakao', 'unknown'))
        return results
    try:
        unit = runner(['systemctl', '--user', 'is-active', 'kakao-webhook.service'],
                      capture_output=True, text=True, timeout=5, check=False)
        if unit.returncode != 0 or unit.stdout.strip() != 'active':
            results.append(observation('kakao', 'failed', 'collector_down'))
        else:
            probe = runner([sys.executable, str(Path(__file__).with_name('kakao_tunnel_url.py')),
                            '--home', str(home), '--probe-only'],
                           capture_output=True, text=True, timeout=20, check=False)
            results.append(observation('kakao', 'healthy' if probe.returncode == 0 else 'failed',
                                       None if probe.returncode == 0 else 'public_unreachable'))
    except (OSError, subprocess.SubprocessError):
        results.append(observation('kakao', 'failed', 'probe_failed'))
    return results


def collect_external_jobs(home: Path) -> list:
    """Report task failures without claiming every task failure is a login fault."""
    labels = {'chatgpt-project-sync': 'ChatGPT 자동 동기화 작업',
              'leetcode-history-sync': 'LeetCode 기록 갱신 작업',
              'english-podcast-daily': 'YouTube 팟캐스트 자료·연습 전달 작업',
              'papers-catalog-sync': '논문 카탈로그 갱신 작업'}
    result = []
    for profile_home in (home, home / 'profiles/english'):
        try:
            jobs = read_json(profile_home / 'cron/jobs.json').get('jobs', [])
            if not isinstance(jobs, list) or any(not isinstance(job, dict) for job in jobs):
                raise ValueError('Invalid job state.')
            for job in jobs:
                name = job.get('name')
                if name not in labels or not job.get('enabled', True):
                    continue
                status = str(job.get('last_status', '')).lower()
                profile = 'english' if profile_home != home else 'david'
                result.append({'service': 'job:' + profile + ':' + name, 'label': labels[name],
                               'status': 'failed' if status in ('error', 'failed', 'failure') else
                               'healthy' if status == 'ok' else 'unknown',
                               'reason': 'sync_failed' if status in ('error', 'failed', 'failure') else None})
        except (OSError, ValueError, TypeError):
            result.append({'service': 'job-state:' + ('english' if profile_home != home else 'david'),
                           'label': '외부 연동 예약 작업 상태', 'status': 'failed', 'reason': 'state_unreadable'})
    return result


def update_incidents(state: dict, observations: list, now: datetime) -> list:
    """Queue one notice per incident/recovery and retain failed deliveries."""
    state.setdefault('services', {})
    state.setdefault('events', [])
    state.setdefault('pending', [])
    timestamp = now.isoformat(timespec='seconds')
    for observed in observations:
        service = observed['service']
        record = state['services'].setdefault(service, {'incident_open': False, 'failure_count': 0})
        record.update(observed, checked_at=timestamp)
        if observed['status'] == 'unknown':
            record['failure_count'] = 0
            continue  # Missing/unverified evidence cannot close an incident.
        if observed['status'] == 'failed':
            record['failure_count'] += 1
            threshold = 2 if observed['reason'] in ('public_unreachable', 'probe_failed') else 1
            if record['incident_open'] or record['failure_count'] < threshold:
                continue
            record.update(incident_open=True, failed_at=timestamp)
            kind = 'failed'
        else:
            record['failure_count'] = 0
            if not record['incident_open']:
                continue
            record.update(incident_open=False, recovered_at=timestamp)
            kind = 'recovered'
        event = {'service': service, 'label': observed.get('label') or SERVICES[service][0],
                 'kind': kind, 'reason': observed['reason'], 'time': timestamp}
        state['events'].append(event)
        state['pending'].append(event)
    state['checked_at'] = timestamp
    state['events'] = state['events'][-100:]
    return state['pending']


def notice_message(events: list) -> str:
    lines = ['🔌 Hermes 외부 연결 알림']
    for event in events:
        if event['kind'] == 'recovered':
            lines += ['', f"✅ {event['label']} · 복구 확인", f"확인 시각: {event['time']}"]
        else:
            lines += ['', f"⚠️ {event['label']} · 장애 감지", f"확인 시각: {event['time']}",
                      REASONS[event['reason']],
                      SERVICES.get(event['service'], ('', 'Hermes HQ에서 해당 작업의 최근 실행 상태를 확인하고 재시도하세요.'))[1]]
        if event['service'] == 'kakao':
            lines.append('공개 수신 경로 검사 기준이며, 카카오 관리자센터 배포와 실제 메시지 전달은 별도 확인이 필요합니다.')
    lines.append('\n같은 장애는 반복 알리지 않으며, 확인된 복구는 다시 알립니다.')
    return '\n'.join(lines)


def send_notice(home: Path, message: str, *, runner=subprocess.run) -> bool:
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('TELEGRAM_', 'HERMES_CRON_'))}
    env['HERMES_HOME'] = str(home)
    env.pop('HERMES_PROFILE', None)
    try:
        result = runner(['hermes', 'send', '--to', 'telegram', '--quiet'], input=message,
                        capture_output=True, text=True, check=False, timeout=20, env=env)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as handle:
            json.dump(state, handle, indent=2, ensure_ascii=False)
            handle.write('\n')
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def check_and_notify(home: Path, observations: list, *, now: datetime | None = None,
                     sender=send_notice) -> dict:
    now = now or datetime.now(timezone.utc)
    path = home / 'data/observatory/connection-health.json'
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read_json(path)
        pending = update_incidents(state, observations, now)
        # Persist detection before attempting delivery so failures can retry.
        save_state(path, state)
        if pending:
            batch = pending[:8]
            delivered = sender(home, notice_message(batch))
            state['last_delivery_ok'] = delivered
            state['last_delivery_at'] = now.isoformat(timespec='seconds')
            if delivered:
                state['pending'] = pending[len(batch):]
            save_state(path, state)
            print('External connection notice sent.' if delivered else
                  'External connection notice delivery failed; retrying on the next watchdog tick.')
    return state


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path(os.environ.get('HERMES_HOME', '~/.hermes')).expanduser())
    parser.add_argument('--notify', action='store_true', help="notify David's existing Hermes Telegram home")
    args = parser.parse_args(argv)
    try:
        home = args.home.expanduser()
        observations = collect_connections(home) + collect_external_jobs(home)
        if args.notify:
            check_and_notify(home, observations)
        print(json.dumps({'connections': observations}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError):
        print('External connection monitor failed; preserved saved incident state.', file=sys.stderr)
        return 0 if args.notify else 1  # Monitoring cannot prevent gateway recovery.


if __name__ == '__main__':
    raise SystemExit(main())
