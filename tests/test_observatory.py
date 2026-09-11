# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Exercise private record boundaries, source failures, search and routing."""
import json
from pathlib import Path
import sqlite3
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from observatory import Observatory, date_range, make_handler, redact, room_for


@pytest.fixture
def store(tmp_path):
    home = tmp_path / 'hermes'
    home.mkdir()
    conn = sqlite3.connect(home / 'state.db')
    conn.executescript('''
    CREATE TABLE sessions(id TEXT,source TEXT,title TEXT,started_at REAL,
      ended_at REAL,end_reason TEXT,model TEXT,message_count INTEGER,
      tool_call_count INTEGER,input_tokens INTEGER,output_tokens INTEGER);
    CREATE TABLE messages(id INTEGER,session_id TEXT,role TEXT,content TEXT,
      tool_name TEXT,tool_calls TEXT,timestamp REAL,finish_reason TEXT);
    INSERT INTO sessions VALUES('s1','telegram','First',1789150000,NULL,NULL,'local',3,1,42,5);
    INSERT INTO sessions VALUES('s2','cron','Second',1789151000,1789151020,'done','local',1,0,10,4);
    INSERT INTO messages VALUES(1,'s1','system','private system prompt',NULL,NULL,1789150000,NULL);
    INSERT INTO messages VALUES(2,'s1','user','Two Sum <script>alert(1)</script>',NULL,NULL,1789150001,NULL);
    INSERT INTO messages VALUES(3,'s1','tool','result','terminal',NULL,1789150002,NULL);
    INSERT INTO messages VALUES(4,'s2','assistant','Hello English',NULL,NULL,1789151001,'stop');
    ''')
    conn.commit()
    conn.close()
    (home / 'cron').mkdir()
    (home / 'cron/jobs.json').write_text(json.dumps({'jobs': [
        {'id': 'new', 'name': 'coding-coach', 'deliver': 'telegram:-12', 'enabled': True}]}))
    (home / 'sessions').mkdir()
    (home / 'sessions/sessions.json').write_text(json.dumps({
        'gateway-key': {'session_id': 's1', 'origin': {'chat_id': '-12'}}}))
    return Observatory(home, tmp_path / 'lessons')


def test_search_is_literal_and_covers_tool_names(store):
    assert store.sessions(q='two sum')['total'] == 1
    assert store.sessions(q='TERMINAL')['total'] == 1
    assert store.sessions(q="%' OR 1=1 --")['total'] == 0
    assert store.sessions(q='private system prompt')['total'] == 0


def test_session_pagination_dates_and_channel_mapping(store):
    assert store.sessions(limit=1)['items'][0]['id'] == 's2'
    assert store.sessions(offset=1, limit=1)['items'][0]['id'] == 's1'
    assert store.sessions(room='coding')['items'][0]['id'] == 's1'
    assert store.sessions(start='2026-09-12')['total'] == 0
    assert store.sessions(room='coding')['items'][0]['status'] == '종료 기록 없음'


def test_messages_exclude_system_and_paginate_oldest_first(store):
    result = store.messages('david', 's1', limit=1)
    assert result['total'] == 2
    assert result['items'][0]['role'] == 'user'
    assert store.messages('david', 's1', offset=1)['items'][0]['tool_name'] == 'terminal'
    assert store.messages('david', 's1', q='result')['total'] == 1


def test_invalid_profile_never_traverses_filesystem(store):
    with pytest.raises(ValueError):
        store.messages('../../', 's1')
    with pytest.raises(ValueError):
        store.library('../../.env')


def test_recreated_cron_uses_task_not_injected_skill():
    prompt = 'Skill: weekly review, system design coach, English\n\nand nothing more.]\n\nDeliver today\'s Coding Coach using interview-prep.'
    assert room_for('david', 'cron_old_20260911', prompt, []) == 'coding'
    assert room_for('english', 'cron_old', prompt, []) == 'english'
    assert room_for('david', 'chat', prompt, []) == 'hq'


def test_redaction_preserves_metrics_but_masks_credentials():
    data = {'input_tokens': 123, 'api_key': 'something', 'body':
            'bot123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ_123456789\nPASSWORD=abc\nBearer abcdef'}
    output = redact(data)
    assert output['input_tokens'] == 123
    assert output['api_key'] == '[redacted]'
    assert 'PASSWORD=abc' not in output['body']
    assert 'Bearer abcdef' not in output['body']
    assert 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' not in output['body']


def test_missing_sources_are_empty_and_db_is_readonly(store):
    assert store.library('learning')['total'] == 0
    assert store.library('memory')['total'] == 0
    conn = store.connect('david')
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute('DELETE FROM sessions')
    finally:
        conn.close()


def test_gateway_pid_absent_is_not_live(store):
    (store.home / 'gateway_state.json').write_text(json.dumps(
        {'pid': 999999999, 'start_time': 0, 'active_agents': 4, 'gateway_state': 'running'}))
    assert store.gateway('david')['alive'] is False
    assert store.gateway('david')['active_agents'] == 0


def test_date_range_uses_local_day_with_dst():
    start, end = date_range('2026-03-08', '2026-03-08')
    assert end - start == 23 * 3600
    with pytest.raises(ValueError):
        date_range('2026-09-11', '2026-09-10')


def test_partial_database_failure_remains_visible(store):
    other = store.home / 'profiles/english'
    other.mkdir(parents=True)
    (other / 'state.db').write_text('broken')
    result = store.sessions()
    assert result['total'] == 2
    assert result['errors'][0]['profile'] == 'english'


def test_http_blocks_untrusted_hosts_cross_site_and_arbitrary_files(store):
    assets = Path(__file__).resolve().parents[1] / 'browser/observatory'
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(store, assets, {'127.0.0.1'}))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def request(path, headers=None):
        conn = HTTPConnection(*server.server_address)
        conn.request('GET', path, headers=headers or {})
        response = conn.getresponse()
        result = response.status, response.read(), dict(response.getheaders())
        conn.close()
        return result
    try:
        assert request('/api/overview', {'Host': 'evil.example'})[0] == 403
        assert request('/api/overview', {'Sec-Fetch-Site': 'cross-site'})[0] == 403
        assert request('/../../.env')[0] == 404
        status, body, headers = request('/api/messages?session=s1')
        assert status == 200
        assert b'private system prompt' not in body
        assert headers['Cache-Control'] == 'no-store'
        assert 'frame-ancestors' in headers['Content-Security-Policy']
        assert request('/api/sessions?offset=bad')[0] == 400
        assert request('/')[0] == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
