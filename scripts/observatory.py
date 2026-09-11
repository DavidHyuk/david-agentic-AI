#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Read-only Hermes observatory: local HTTP UI over existing runtime records.

No Hermes imports, database migrations, model calls, or runtime writes. Bind to
loopback and optionally the local Tailscale IP or use Tailscale Serve. Only explicit data sources and static
assets are exposed; request dumps, auth files and private reasoning are excluded.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import ipaddress
import json
import mimetypes
from pathlib import Path
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import time
import threading
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
    def __init__(self, home: Path, lessons: Path | None = None):
        self.home = home.resolve()
        self.lessons = lessons or Path.home() / 'english-lessons'

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
        definitions = ROOMS + [(n, n.title(), '독립 프로필', '📷', '#d2c3af')
                               for n in self.profiles() if n not in ('david', 'english')]
        for key, title, subtitle, icon, color in definitions:
            history = [s for s in sessions['items'] if s['room'] == key]
            room_jobs = [j for j in jobs if j['room'] == key]
            latest = history[0] if history else None
            rooms.append({'id': key, 'title': title, 'subtitle': subtitle, 'icon': icon,
                          'color': color, 'sessions': len(history), 'latest': latest,
                          'jobs': room_jobs, 'profile': 'david' if key in
                          ('hq', 'papers', 'interview', 'coding', 'design') else key})
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
        if kind == 'memory':
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
                elif url.path == '/api/sessions':
                    data = store.sessions(profile, q, args.get('room', ''), args.get('start', ''), args.get('end', ''), offset, limit)
                elif url.path == '/api/messages':
                    data = store.messages(profile or 'david', args.get('session', ''), offset, limit, q)
                elif url.path == '/api/library':
                    data = store.library(args.get('kind', ''), profile or 'david', q, offset, limit)
                elif url.path in ('/', '/index.html', '/app.js', '/style.css'):
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
            except (OSError, sqlite3.Error):
                self.respond(503, {'error': '기록을 읽을 수 없습니다. 잠시 후 다시 시도하세요.'})
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
