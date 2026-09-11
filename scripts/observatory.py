#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Hermes observatory with validated study and Kanban orchestration actions.

No Hermes imports or database migrations. Archive reads remain read-only;
explicit study actions use locked helper CLIs and HQ missions use Hermes' own
Kanban CLI. Bind to loopback and optionally the local Tailscale IP or use
Tailscale Serve. Only explicit data sources and static assets are exposed;
request dumps, auth files and private reasoning are excluded.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import ipaddress
import fcntl
import json
import mimetypes
from pathlib import Path
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import time
import threading
import subprocess
import sys
import os
import tempfile
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

TZ = ZoneInfo('America/Los_Angeles')
ROOMS = [
    ('papers', 'Frontier Radar', '논문 연구', '🔭', '#a8d8ac'),
    ('interview', 'Interview Lab', 'Staff / MLE 인터뷰', '🎯', '#b6b4eb'),
    ('coding', 'LeetCode Gym', '코딩 훈련', '⌨', '#efc783'),
    ('design', 'Design Studio', '시스템 디자인', '🏗', '#9bcad8'),
    ('english', 'English Lab', '영어 코칭 · SRS', '💬', '#e7b3c7'),
    ('hq', 'Hermes HQ', '대화 · 통합 리뷰', '✦', '#c4ccaa'),
]
JOB_ROOMS = {'papers-digest': 'papers', 'interview-prep': 'interview',
             'coding-coach': 'coding', 'system-design-coach': 'design',
             'weekly-review': 'hq', 'english-intake': 'english',
             'english-drill': 'english', 'english-weekly-review': 'english'}
SECRET_KEY = re.compile(r'(token|secret|password|api[_-]?key|authorization|cookie|credential)', re.I)
TASK_ID = re.compile(r't_[0-9a-f]{8}')
REQUEST_ID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}', re.I)
MISSION_BOARD = 'hermes-hq'
SPECIALIST_ROOMS = {
    'default': 'hq', 'papers': 'papers', 'interview': 'interview',
    'coding': 'coding', 'design': 'design', 'english': 'english',
}


def redact(value):
    """Mask recognizable credentials in both structured records and text."""
    if isinstance(value, dict):
        return {k: '[redacted]' if SECRET_KEY.search(k) and not isinstance(v, (int, float)) else redact(v)
                for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if not isinstance(value, str):
        return value
    value = re.sub(r'\b(?:bot)?\d{6,12}:[A-Za-z0-9_-]{25,}\b', '[redacted]', value)
    value = re.sub(r'\b(?:sk-|hf_)[A-Za-z0-9_-]{12,}', '[redacted]', value)
    value = re.sub(r'(?i)Bearer\s+[^\s"\x27,}]+', 'Bearer [redacted]', value)
    return re.sub(r'''(?im)((?:[\w-]*(?:token|secret|password|api_key|authorization|cookie)[\w-]*)["']?\s*[:=]\s*)[^\n]+''',
                  r'\1[redacted]', value)


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def task_prompt(prompt):
    """Separate a cron task from the injected skill and delivery instructions."""
    if 'and nothing more.]' in prompt:
        return prompt.rsplit('and nothing more.]', 1)[-1].strip()
    return prompt.rsplit('\n\n', 1)[-1].strip()


def room_for(profile, session_id, prompt, jobs):
    if profile != 'david':
        return 'english' if profile == 'english' else profile
    for job in jobs:
        if session_id.startswith('cron_' + job['id'] + '_'):
            return JOB_ROOMS.get(job['name'], 'hq')
    # Old cron IDs are replaced by the registrar; their stored first prompt
    # remains evidence for classification. General chats default to HQ.
    if not session_id.startswith('cron_'):
        return 'hq'
    p = task_prompt(prompt).lower()
    for needle, room in [('weekly review', 'hq'), ('system design coach', 'design'),
                         ('system-design coach', 'design'), ('coding coach', 'coding'),
                         ('papers-digest', 'papers'), ('research signal', 'papers'),
                         ('interview-prep', 'interview'), ('interview', 'interview'),
                         ('english', 'english')]:
        if needle in p:
            return room
    return 'hq'


def date_range(start='', end=''):
    """Local calendar dates, inclusive end date, converted to epoch bounds."""
    lo = datetime.strptime(start, '%Y-%m-%d').replace(tzinfo=TZ).timestamp() if start else 0
    hi = ((datetime.strptime(end, '%Y-%m-%d').replace(tzinfo=TZ) + timedelta(days=1))
          .timestamp() if end else float('inf'))
    if hi <= lo:
        raise ValueError('종료 날짜는 시작 날짜 이후여야 합니다.')
    return lo, hi


def page(items, offset=0, limit=40):
    return {'items': items[offset:offset + limit], 'total': len(items),
            'offset': offset, 'limit': limit}


class Observatory:
    def __init__(self, home: Path, lessons: Path | None = None,
                 hermes_cli: Path | None = None, board: str = MISSION_BOARD):
        self.home = home.resolve()
        self.lessons = lessons or Path.home() / 'english-lessons'
        self.hermes_cli = hermes_cli or Path(os.environ.get(
            'HERMES_CLI', str(Path.home() / '.local/bin/hermes')))
        self.board = board

    def profiles(self):
        result = {'david': self.home}
        root = self.home / 'profiles'
        if root.exists():
            for path in sorted(root.iterdir()):
                if (not path.is_symlink() and path.is_dir()
                        and re.fullmatch(r'[a-zA-Z0-9_-]+', path.name)
                        and (path / 'state.db').exists()):
                    result[path.name] = path
        return result

    def catalog_path(self):
        return self.home / 'skills/career/interview-prep/references/coach_catalog.json'

    def coach_state(self):
        return read_json(self.home / 'data/interview/coach_state.json',
                         {'assignments': {}, 'coding': [], 'system_design': []})

    def notebook(self):
        return read_json(self.home / 'data/observatory/workspace.json',
                         {'revision': 0, 'notes': {}, 'papers': {}, 'events': []})

    def pending_assignments(self):
        state = self.coach_state()
        latest = {}
        for assignment in sorted(state['assignments'].values(), key=lambda a: a['date']):
            if not assignment.get('completed'):
                latest[(assignment['track'], assignment['item_id'])] = assignment
        return list(latest.values())

    def workbench(self, room):
        allowed = {r[0] for r in ROOMS} | set(self.profiles())
        if room not in allowed:
            raise ValueError('알 수 없는 작업실입니다.')
        today = datetime.now(TZ).date().isoformat()
        notebook = self.notebook()
        data = {'room': room, 'today': today, 'revision': notebook['revision'],
                'note': notebook['notes'].get(room, ''),
                'events': [e for e in reversed(notebook['events']) if e['room'] == room][:12]}
        history = self.sessions(room=room, limit=5)
        data['recent'] = history['items']
        data['errors'] = history['errors']
        if room in ('coding', 'design'):
            track = 'coding' if room == 'coding' else 'system_design'
            state = self.coach_state()
            catalog = read_json(self.catalog_path(), {})
            items = {p['id']: p for p in catalog.get('problems' if track == 'coding' else 'system_design', [])}
            pending = [a for a in self.pending_assignments() if a['track'] == track]
            pending.sort(key=lambda a: a['date'], reverse=True)
            data.update(track=track, pending=[{**a, 'item': items.get(a['item_id'], {})} for a in pending],
                        completed=sorted(state[track], key=lambda a: a['date'], reverse=True),
                        today_assignment=state['assignments'].get(f'{track}:{today}'),
                        catalog_available=bool(items))
        elif room == 'english':
            cards = list(read_json(self.home / 'data/english/srs_deck.json', {'cards': {}})['cards'].values())
            due = sorted([c for c in cards if c['due'] <= today], key=lambda c: (c['box'], c['due']))
            data.update(due=due[:30], due_count=len(due), total_cards=len(cards),
                        weak=sorted(cards, key=lambda c: (c['box'], -c.get('wrong_reviews', 0)))[:5])
        elif room == 'papers':
            data['papers'] = self.library('papers', limit=12)['items']
            data['reading_list'] = list(notebook['papers'].values())
        elif room == 'hq':
            data['pending'] = self.pending_assignments()
            cards = read_json(self.home / 'data/english/srs_deck.json', {'cards': {}})['cards']
            data['due_count'] = sum(c['due'] <= today for c in cards.values())
            data['reading_count'] = sum(not p.get('read') for p in notebook['papers'].values())
            data['events'] = list(reversed(notebook['events']))[:20]
            data['orchestration'] = self.orchestration()
        elif room == 'interview':
            data['drill'] = ''
            for session in history['items']:
                conn = self.connect(session['profile'])
                try:
                    found = conn.execute("SELECT content FROM messages WHERE session_id=? AND role='assistant' AND content IS NOT NULL AND trim(content) NOT IN ('','[SILENT]') ORDER BY id DESC LIMIT 1", (session['id'],)).fetchone()
                finally:
                    conn.close()
                if found:
                    data['drill'] = found['content']
                    data['drill_session'] = session
                    break
        return data

    def kanban(self, arguments, *, timeout=20, json_output=True):
        """Call only fixed Hermes Kanban subcommands against the HQ board."""
        if not self.hermes_cli.is_file():
            raise OSError('Hermes CLI를 찾을 수 없습니다.')
        result = subprocess.run(
            [str(self.hermes_cli), 'kanban', '--board', self.board, *arguments],
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, 'HERMES_HOME': str(self.home)},
        )
        if result.returncode:
            message = result.stderr.strip().splitlines()[-1] if result.stderr else 'Kanban 작업에 실패했습니다.'
            raise ValueError(message)
        if not json_output:
            return {'message': result.stdout.strip()}
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise OSError('Kanban 응답을 읽을 수 없습니다.') from exc

    def orchestration(self):
        """Return a compact mission-board snapshot without failing the HQ desk."""
        try:
            tasks = self.kanban(['list', '--sort', 'updated', '--json'])[:100]
            assignees = self.kanban(['assignees', '--json'])
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            return {'available': False, 'board': self.board, 'error': str(exc),
                    'tasks': [], 'assignees': [], 'counts': {}}
        counts = {}
        for task in tasks:
            counts[task['status']] = counts.get(task['status'], 0) + 1
            task['room'] = SPECIALIST_ROOMS.get(task.get('assignee'), 'hq')
        return {'available': True, 'board': self.board, 'tasks': tasks,
                'assignees': [{**a, 'room': SPECIALIST_ROOMS[a['name']]}
                              for a in assignees if a['name'] in SPECIALIST_ROOMS],
                'counts': counts,
                'dispatcher_alive': self.gateway('david')['alive']}

    def mission_detail(self, task_id):
        if not isinstance(task_id, str) or not TASK_ID.fullmatch(task_id):
            raise ValueError('올바른 작업 ID가 필요합니다.')
        detail = self.kanban(['show', task_id, '--json'])
        detail['task']['room'] = SPECIALIST_ROOMS.get(detail['task'].get('assignee'), 'hq')
        return detail

    def helper(self, name, arguments):
        result = subprocess.run([sys.executable, str(Path(__file__).with_name(name)), *arguments],
                                capture_output=True, text=True, timeout=20,
                                env={**os.environ, 'TZ': str(TZ), 'HERMES_HOME': str(self.home)})
        if result.returncode:
            raise ValueError(result.stderr.strip().splitlines()[-1] if result.stderr else '저장하지 못했습니다.')
        return json.loads(result.stdout)

    def study_action(self, body):
        """Allow only concrete study and mission mutations, never shell input."""
        if not isinstance(body, dict):
            raise ValueError('JSON 객체가 필요합니다.')
        action = body.get('action')
        today = datetime.now(TZ).date().isoformat()
        if action in ('plan', 'feedback'):
            track = body.get('track')
            if track not in ('coding', 'system_design'):
                raise ValueError('알 수 없는 학습 종류입니다.')
            args = ['--state', str(self.home / 'data/interview/coach_state.json'),
                    '--catalog', str(self.catalog_path()), '--date', today]
            if action == 'plan':
                args += ['plan', track, '--format', 'json']
            else:
                assignment = body.get('assignment')
                row = self.coach_state()['assignments'].get(assignment)
                if not row or row['track'] != track:
                    raise ValueError('과제와 작업실이 일치하지 않습니다.')
                feedback = body.get('feedback')
                if not isinstance(feedback, dict):
                    raise ValueError('실제 학습 결과를 입력하세요.')
                def integer(key, maximum):
                    value = feedback.get(key)
                    if type(value) is not int or not (0 if key == 'hint_level' else 1) <= value <= maximum:
                        raise ValueError(f'{key}: 유효한 정수를 입력하세요.')
                    return str(value)
                args += ['log-coding' if track == 'coding' else 'log-design',
                         '--assignment', assignment, '--duration', integer('duration', 1440),
                         '--confidence', integer('confidence', 5)]
                if track == 'coding':
                    for key in ('independent', 'solution_viewed'):
                        if type(feedback.get(key)) is not bool:
                            raise ValueError(f'{key}: 예 또는 아니오를 선택하세요.')
                        args += ['--' + key.replace('_', '-'), 'yes' if feedback[key] else 'no']
                    args += ['--hint-level', integer('hint_level', 3), '--lesson', self.text_field(feedback, 'lesson')]
                else:
                    for key in ('requirements', 'architecture', 'trade_off', 'failure_mode'):
                        args += ['--' + key.replace('_', '-') + '-score', integer(key + '_score', 5)]
                    args += ['--next-improvement', self.text_field(feedback, 'next_improvement')]
            return {'saved': True, 'result': self.helper('interview_progress.py', args)}
        if action == 'srs_review':
            if body.get('result') not in ('correct', 'wrong') or type(body.get('expected_reviews')) is not int:
                raise ValueError('카드 결과와 현재 복습 횟수가 필요합니다.')
            card = body.get('card')
            deck = read_json(self.home / 'data/english/srs_deck.json', {'cards': {}})
            if not isinstance(card, str) or card not in deck['cards']:
                raise ValueError('카드를 찾을 수 없습니다.')
            return {'saved': True, 'result': self.helper('english_srs.py', [
                '--deck', str(self.home / 'data/english/srs_deck.json'), '--date', today,
                'review', '--id', card, '--result', body['result'],
                '--expected-reviews', str(body['expected_reviews'])])}
        if action in ('note', 'bookmark', 'paper_read'):
            return self.save_notebook(body)
        if isinstance(action, str) and action.startswith('mission_'):
            return self.mission_action(body)
        raise ValueError('허용되지 않은 동작입니다.')

    def mission_action(self, body):
        """Create and manage HQ tasks through an exact Kanban CLI allowlist."""
        action = body['action']
        if action == 'mission_create':
            goal = self.text_field(body, 'goal', maximum=200)
            context = self.optional_text_field(body, 'context', maximum=4000)
            request_id = body.get('request_id')
            priority = body.get('priority', 50)
            if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
                raise ValueError('요청 ID가 올바르지 않습니다.')
            if type(priority) is not int or not 0 <= priority <= 100:
                raise ValueError('우선순위는 0~100 사이의 정수여야 합니다.')
            task = self.kanban([
                'create', goal, '--body', context or goal, '--assignee', 'default',
                '--workspace', 'scratch', '--tenant', 'hermes-hq', '--priority', str(priority),
                '--triage', '--created-by', 'hq-ui', '--idempotency-key', 'hq:' + request_id,
                '--max-runtime', '20m', '--max-retries', '2', '--json',
            ])
            return {'saved': True, 'task': task,
                    'message': '목표를 접수했습니다. HQ가 곧 작업 그래프로 나눕니다.'}
        task_id = body.get('task')
        detail = self.mission_detail(task_id)
        status = detail['task']['status']
        if action == 'mission_comment':
            comment = self.text_field(body, 'comment', maximum=2000)
            self.kanban(['comment', '--author', 'david', '--max-len', '2000',
                         task_id, comment], json_output=False)
        elif action == 'mission_block':
            if status in ('done', 'archived'):
                raise ValueError('완료된 작업은 중지할 수 없습니다.')
            reason = self.text_field(body, 'reason', maximum=500)
            self.kanban(['block', task_id, reason], json_output=False)
        elif action == 'mission_unblock':
            if status not in ('blocked', 'scheduled'):
                raise ValueError('중단되거나 예약된 작업만 다시 실행할 수 있습니다.')
            self.kanban(['unblock', task_id], json_output=False)
        elif action == 'mission_assign':
            if status == 'running':
                raise ValueError('실행 중인 작업은 완료 또는 중지 후 재배정하세요.')
            assignee = body.get('assignee')
            available = {row['name'] for row in self.kanban(['assignees', '--json'])
                         if row.get('on_disk')}
            if assignee not in available or assignee not in SPECIALIST_ROOMS:
                raise ValueError('설치된 캠퍼스 에이전트만 선택할 수 있습니다.')
            self.kanban(['assign', task_id, assignee], json_output=False)
        else:
            raise ValueError('허용되지 않은 미션 동작입니다.')
        return {'saved': True, 'detail': self.mission_detail(task_id)}

    @staticmethod
    def text_field(body, key, maximum=16000):
        value = body.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError(f'{key}: 1~{maximum}자의 내용을 입력하세요.')
        return value.strip()

    @staticmethod
    def optional_text_field(body, key, maximum=16000):
        value = body.get(key, '')
        if not isinstance(value, str) or len(value) > maximum:
            raise ValueError(f'{key}: {maximum}자 이하의 내용을 입력하세요.')
        return value.strip()

    def save_notebook(self, body):
        path = self.home / 'data/observatory/workspace.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            book = self.notebook()
            if type(body.get('revision')) is not int or body['revision'] != book['revision']:
                raise ValueError('다른 화면에서 기록이 바뀌었습니다. 새로고침 후 다시 저장하세요.')
            action = body['action']
            room = body.get('room', 'papers')
            if room not in {r[0] for r in ROOMS}:
                raise ValueError('알 수 없는 작업실입니다.')
            if action == 'note':
                note = self.text_field(body, 'note')
                book['notes'][room] = note
            elif action == 'bookmark':
                conn = sqlite3.connect((self.home / 'data/papers/papers.db').as_uri() + '?mode=ro', uri=True)
                conn.row_factory = sqlite3.Row
                try:
                    paper = conn.execute('SELECT id,title,url FROM papers WHERE id=?', (body.get('paper'),)).fetchone()
                finally:
                    conn.close()
                if not paper:
                    raise ValueError('논문을 찾을 수 없습니다.')
                book['papers'].setdefault(paper['id'], {**dict(paper), 'read': False})
            else:
                paper = book['papers'].get(body.get('paper'))
                if not paper or type(body.get('read')) is not bool:
                    raise ValueError('읽기 목록의 논문을 선택하세요.')
                paper['read'] = body['read']
            book['revision'] += 1
            book['events'].append({'action': action, 'room': room, 'time': time.time(),
                                   'paper': body.get('paper'), 'revision': book['revision'],
                                   **({'note': book['notes'][room]} if action == 'note' else {})})
            with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as out:
                temp = Path(out.name)
                try:
                    json.dump(book, out, ensure_ascii=False, indent=2)
                    out.flush()
                    os.fsync(out.fileno())
                except BaseException:
                    temp.unlink(missing_ok=True)
                    raise
            try:
                temp.replace(path)
            finally:
                temp.unlink(missing_ok=True)
            return {'saved': True, 'revision': book['revision']}

    def profile_home(self, profile):
        if profile not in self.profiles():
            raise ValueError('알 수 없는 프로필입니다.')
        return self.profiles()[profile]

    def connect(self, profile):
        db = self.profile_home(profile) / 'state.db'
        conn = sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=2)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        return conn

    def jobs(self, profile):
        doc = read_json(self.profile_home(profile) / 'cron/jobs.json', {})
        return doc.get('jobs', [])

    def channel_rooms(self, profile, jobs):
        """Map current Telegram session IDs using persisted gateway origins."""
        index = read_json(self.profile_home(profile) / 'sessions/sessions.json', {})
        targets = {str(j.get('deliver', '')).removeprefix('telegram:'): JOB_ROOMS.get(j['name'], 'hq')
                   for j in jobs if str(j.get('deliver', '')).startswith('telegram:')}
        return {entry.get('session_id'): targets[str(entry.get('origin', {}).get('chat_id'))]
                for entry in index.values() if isinstance(entry, dict)
                and str(entry.get('origin', {}).get('chat_id')) in targets}

    def sessions(self, profile='', q='', room='', start='', end='', offset=0, limit=40):
        low, high = date_range(start, end)
        rows, errors = [], []
        names = [profile] if profile else list(self.profiles())
        for name in names:
            self.profile_home(name)
            try:
                conn = self.connect(name)
                try:
                    query = '''SELECT s.id,s.source,s.title,s.started_at,s.ended_at,
                        s.end_reason,s.model,s.message_count,s.tool_call_count,
                        s.input_tokens,s.output_tokens,
                        coalesce((SELECT m.content FROM messages m WHERE m.session_id=s.id
                        AND m.role='user' ORDER BY m.id LIMIT 1),'') AS first_prompt
                        FROM sessions s WHERE s.started_at >= ? AND s.started_at < ?'''
                    args = [low, high]
                    if q:
                        query += ''' AND (instr(lower(coalesce(s.title,'')), lower(?)) > 0
                            OR EXISTS (SELECT 1 FROM messages m WHERE m.session_id=s.id
                            AND m.role IN ('user','assistant','tool') AND
                            (instr(lower(coalesce(m.content,'')),lower(?)) > 0
                            OR instr(lower(coalesce(m.tool_name,'')),lower(?)) > 0)))'''
                        args += [q, q, q]
                    found = conn.execute(query, args).fetchall()
                finally:
                    conn.close()
                jobs = self.jobs(name)
                channels = self.channel_rooms(name, jobs)
                for raw in found:
                    row = dict(raw)
                    prompt = row.pop('first_prompt')
                    row['room'] = channels.get(row['id']) or room_for(name, row['id'], prompt, jobs)
                    if room and row['room'] != room:
                        continue
                    row['profile'] = name
                    task = task_prompt(prompt) if row['source'] == 'cron' else prompt
                    row['preview'] = task[:240]
                    row['title'] = row['title'] or task[:100] or row['id']
                    # ended_at=NULL is not proof that an agent is running.
                    row['status'] = '종료 기록 있음' if row['ended_at'] else '종료 기록 없음'
                    rows.append(row)
            except (sqlite3.Error, OSError, ValueError) as exc:
                errors.append({'profile': name, 'error': type(exc).__name__})
        rows.sort(key=lambda r: r['started_at'], reverse=True)
        return {**page(rows, offset, limit), 'errors': errors}

    def messages(self, profile, session, offset=0, limit=80, q=''):
        conn = self.connect(profile)
        try:
            if not conn.execute('SELECT 1 FROM sessions WHERE id=?', (session,)).fetchone():
                raise ValueError('세션을 찾을 수 없습니다.')
            where = "session_id=? AND role IN ('user','assistant','tool')"
            args = [session]
            if q:
                where += " AND instr(lower(coalesce(content,'') || coalesce(tool_name,'')),lower(?))>0"
                args.append(q)
            total = conn.execute('SELECT count(*) FROM messages WHERE ' + where, args).fetchone()[0]
            records = conn.execute('''SELECT id,role,content,tool_name,tool_calls,
                timestamp,finish_reason FROM messages WHERE ''' + where +
                ' ORDER BY id LIMIT ? OFFSET ?', [*args, limit, offset]).fetchall()
            items = [dict(r) for r in records]
            for item in items:
                content = item.get('content') or ''
                if item['role'] == 'user' and 'and nothing more.]' in content:
                    item['display_content'] = task_prompt(content)
            return {'items': items, 'total': total, 'offset': offset, 'limit': limit}
        finally:
            conn.close()

    def gateway(self, profile):
        state = read_json(self.profile_home(profile) / 'gateway_state.json', {})
        alive = False
        try:
            # Match Linux process start time as well as PID to reject reused PIDs.
            stat = Path(f"/proc/{int(state.get('pid', 0))}/stat").read_text()
            alive = int(stat.rsplit(')', 1)[1].split()[19]) == int(state['start_time'])
        except (OSError, ValueError, KeyError):
            pass
        return {'profile': profile, 'alive': alive, 'state': state.get('gateway_state', 'unknown'),
                'active_agents': state.get('active_agents', 0) if alive else 0,
                'updated_at': state.get('updated_at'),
                'platforms': state.get('platforms', {})}

    def overview(self):
        profiles, jobs, errors = [], [], []
        for name in self.profiles():
            try:
                profiles.append(self.gateway(name))
                for job in self.jobs(name):
                    jobs.append({**{k: job.get(k) for k in (
                        'id', 'name', 'schedule_display', 'next_run_at', 'last_run_at',
                        'last_status', 'last_error', 'last_delivery_error', 'enabled', 'deliver')},
                        'profile': name, 'room': JOB_ROOMS.get(job['name'], name)})
            except (OSError, ValueError) as exc:
                errors.append({'profile': name, 'error': type(exc).__name__})
        sessions = self.sessions(limit=1000000)
        rooms = []
        room_ids = {room[0] for room in ROOMS}
        definitions = ROOMS + [(n, n.title(), '독립 프로필', '📷', '#d2c3af')
                               for n in self.profiles() if n not in room_ids | {'david'}]
        for key, title, subtitle, icon, color in definitions:
            history = [s for s in sessions['items'] if s['room'] == key]
            room_jobs = [j for j in jobs if j['room'] == key]
            latest = history[0] if history else None
            rooms.append({'id': key, 'title': title, 'subtitle': subtitle, 'icon': icon,
                          'color': color, 'sessions': len(history), 'latest': latest,
                          'jobs': room_jobs,
                          'profile': 'david' if key == 'hq' else key})
        today = datetime.now(TZ).strftime('%Y-%m-%d')
        today_start, _ = date_range(today)
        return {'now': time.time(), 'timezone': str(TZ), 'profiles': profiles, 'jobs': jobs,
                'rooms': rooms, 'total_sessions': sessions['total'],
                'today_sessions': sum(s['started_at'] >= today_start for s in sessions['items']),
                'total_messages': sum(s['message_count'] or 0 for s in sessions['items']),
                'recent': sessions['items'][:12], 'errors': errors + sessions['errors']}

    def library(self, kind, profile='david', q='', offset=0, limit=40):
        home = self.profile_home(profile)
        items = []
        if kind == 'workspace':
            for e in reversed(self.notebook()['events']):
                items.append({'id': str(e['revision']), 'title': f"{e['room']} · {e['action']} · v{e['revision']}",
                              'content': e.get('note') or json.dumps(e, ensure_ascii=False, indent=2), 'time': e['time']})
        elif kind == 'memory':
            for filename in ('MEMORY.md', 'USER.md'):
                path = home / 'memories' / filename
                if path.exists():
                    items.append({'id': filename, 'title': filename, 'content': path.read_text(),
                                  'time': path.stat().st_mtime})
        elif kind == 'learning':
            state = read_json(self.home / 'data/interview/coach_state.json', {})
            for track in ('coding', 'system_design'):
                for entry in state.get(track, []):
                    items.append({'id': entry.get('id'), 'title': track + ' · 완료 피드백',
                                  'content': json.dumps(entry, ensure_ascii=False, indent=2)})
            for key, entry in state.get('assignments', {}).items():
                items.append({'id': key, 'title': key + ' · 배정 과제',
                              'content': json.dumps(entry, ensure_ascii=False, indent=2)})
            deck = read_json(self.home / 'data/english/srs_deck.json', {})
            for key, card in deck.get('cards', {}).items():
                items.append({'id': key, 'title': f"SRS · Box {card.get('box')} · {card.get('due', '')}",
                              'content': '\n'.join([str(card.get('wrong', '')), '→ ' + str(card.get('correct', '')),
                                                    str(card.get('note', ''))]), 'data': card})
        elif kind == 'papers':
            db = self.home / 'data/papers/papers.db'
            if db.exists():
                conn = sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=2)
                conn.row_factory = sqlite3.Row
                try:
                    for row in conn.execute('SELECT id,title,abstract,url,published_date FROM papers ORDER BY published_date DESC'):
                        items.append({'id': row['id'], 'title': row['title'], 'content': row['abstract'],
                                      'url': row['url'], 'date': row['published_date']})
                finally:
                    conn.close()
        elif kind in ('outputs', 'lessons'):
            root = home / 'cron/output' if kind == 'outputs' else self.lessons
            if root.exists():
                files = sorted((p for p in root.rglob('*') if p.is_file() and not p.is_symlink()
                                and p.suffix in ('.md', '.txt') and p.resolve().is_relative_to(root.resolve())),
                               key=lambda p: p.stat().st_mtime, reverse=True)
                for path in files:
                    if path.stat().st_size > 2_000_000:
                        continue
                    items.append({'id': str(path.relative_to(root)), 'title': str(path.relative_to(root)),
                                  'content': path.read_text(errors='replace'), 'time': path.stat().st_mtime})
        elif kind == 'logs':
            # Only gateway logs, including rotations. No arbitrary path access.
            paths = sorted((home / 'logs').glob('gateway.log*'), key=lambda p: p.stat().st_mtime, reverse=True)
            for path in paths:
                if path.is_symlink() or not path.is_file() or path.suffix == '.gz':
                    continue
                for i, line in reversed(list(enumerate(path.read_text(errors='replace').splitlines()))):
                    items.append({'id': f'{path.name}:{i+1}', 'title': f'{path.name}:{i+1}', 'content': line})
        else:
            raise ValueError('알 수 없는 기록 종류입니다.')
        if q:
            items = [i for i in items if q.casefold() in
                     (str(i.get('title', '')) + str(i.get('content', ''))).casefold()]
        return page(items, offset, limit)


def make_handler(store, assets: Path, hosts):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            # Query strings may contain private search terms.
            pass

        def respond(self, status, body, content_type='application/json; charset=utf-8'):
            if not isinstance(body, bytes):
                body = json.dumps(redact(body), ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            host = self.headers.get('Host', '').split(':')[0].lower()
            if host not in hosts or self.headers.get('Sec-Fetch-Site') == 'cross-site':
                self.respond(403, {'error': '허용되지 않은 요청입니다.'})
                return
            url = urlsplit(self.path)
            args = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                offset = max(0, int(args.get('offset', 0)))
                limit = max(1, min(100, int(args.get('limit', 40))))
                q = args.get('q', '')[:500]
                profile = args.get('profile', '')
                if url.path == '/api/overview':
                    data = store.overview()
                elif url.path == '/api/workbench':
                    data = store.workbench(args.get('room', 'hq'))
                elif url.path == '/api/mission':
                    data = store.mission_detail(args.get('task', ''))
                elif url.path == '/api/sessions':
                    data = store.sessions(profile, q, args.get('room', ''), args.get('start', ''), args.get('end', ''), offset, limit)
                elif url.path == '/api/messages':
                    data = store.messages(profile or 'david', args.get('session', ''), offset, limit, q)
                elif url.path == '/api/library':
                    data = store.library(args.get('kind', ''), profile or 'david', q, offset, limit)
                elif url.path in ('/', '/index.html', '/app.js', '/style.css', '/workbench.js', '/workbench.css'):
                    filename = 'index.html' if url.path == '/' else url.path[1:]
                    content = (assets / filename).read_bytes()
                    self.respond(200, content, mimetypes.guess_type(filename)[0] + '; charset=utf-8')
                    return
                else:
                    self.respond(404, {'error': '찾을 수 없습니다.'})
                    return
                self.respond(200, data)
            except ValueError as exc:
                self.respond(400, {'error': str(exc)})
            except (OSError, sqlite3.Error, subprocess.TimeoutExpired):
                self.respond(503, {'error': '기록을 읽을 수 없습니다. 잠시 후 다시 시도하세요.'})

        def do_POST(self):
            host = self.headers.get('Host', '')
            origin = urlsplit(self.headers.get('Origin', ''))
            if (host.split(':')[0].lower() not in hosts or origin.netloc != host
                    or origin.scheme not in ('http', 'https')
                    or self.headers.get('Sec-Fetch-Site') == 'cross-site'
                    or self.headers.get('X-Hermes-Action') != '1'):
                self.respond(403, {'error': '같은 관제실 화면에서만 저장할 수 있습니다.'})
                return
            if self.path != '/api/action':
                self.respond(404, {'error': '찾을 수 없습니다.'})
                return
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 65536 or self.headers.get('Content-Type') != 'application/json':
                    raise ValueError('64KB 이하의 JSON 요청이 필요합니다.')
                body = json.loads(self.rfile.read(length))
                self.respond(200, store.study_action(body))
            except (ValueError, KeyError, TypeError) as exc:
                self.respond(400, {'error': str(exc)})
            except (OSError, sqlite3.Error, subprocess.TimeoutExpired):
                self.respond(503, {'error': '저장 결과를 확인할 수 없습니다. 새로고침 후 기록을 확인하세요.'})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path.home() / '.hermes')
    parser.add_argument('--assets', type=Path, default=Path.home() / '.hermes/observatory')
    parser.add_argument('--port', type=int, default=8788)
    parser.add_argument('--allowed-host', action='append', default=[])
    parser.add_argument('--tailnet-ip', help='Optional local Tailscale IPv4; also keep loopback listener')
    args = parser.parse_args()
    hosts = {'127.0.0.1', 'localhost', *[h.lower() for h in args.allowed_host]}
    if args.tailnet_ip:
        if ipaddress.ip_address(args.tailnet_ip) not in ipaddress.ip_network('100.64.0.0/10'):
            parser.error('--tailnet-ip must be a Tailscale IPv4 address')
        hosts.add(args.tailnet_ip)
        tailnet = ThreadingHTTPServer((args.tailnet_ip, args.port), make_handler(Observatory(args.home), args.assets, hosts))
        threading.Thread(target=tailnet.serve_forever, daemon=True).start()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(Observatory(args.home), args.assets, hosts))
    print(f'Hermes HQ listening on 127.0.0.1:{args.port}; tailnet={args.tailnet_ip or "disabled"}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
