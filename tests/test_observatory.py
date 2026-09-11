# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Exercise private record boundaries, source failures, search and routing."""
import json
from pathlib import Path
import sqlite3
import shutil
from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace
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


def test_specialist_profiles_merge_into_existing_campus_rooms(store):
    for name in ('papers', 'coding'):
        profile = store.home / 'profiles' / name
        profile.mkdir(parents=True)
        shutil.copyfile(store.home / 'state.db', profile / 'state.db')
    rooms = store.overview()['rooms']
    assert [room['id'] for room in rooms].count('papers') == 1
    assert [room['id'] for room in rooms].count('coding') == 1
    assert next(room for room in rooms if room['id'] == 'papers')['profile'] == 'papers'
    assert next(room for room in rooms if room['id'] == 'hq')['profile'] == 'david'


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


@pytest.fixture
def study_store(store):
    catalog = store.catalog_path()
    catalog.parent.mkdir(parents=True)
    shutil.copyfile(Path(__file__).resolve().parents[1] /
                    'skills/career/interview-prep/references/coach_catalog.json', catalog)
    folder = store.home / 'data/english'
    folder.mkdir(parents=True)
    (folder / 'srs_deck.json').write_text(json.dumps({'cards': {
        key: {'id': key, 'wrong': 'I goes', 'correct': 'I go', 'box': 1,
              'due': '2000-01-01', 'reviews': 0} for key in ('one', 'two')}}))
    return store


def test_workbench_get_never_assigns_or_completes(study_store):
    for room in ('coding', 'design', 'english', 'hq', 'interview'):
        data = study_store.workbench(room)
        assert data['room'] == room
    assert not (study_store.home / 'data/interview/coach_state.json').exists()
    assert not (study_store.home / 'data/observatory/workspace.json').exists()


def test_plan_feedback_and_retries_use_shared_coach_rules(study_store):
    assignment = study_store.study_action({'action': 'plan', 'track': 'coding'})['result']
    assert not assignment['completed']
    again = study_store.study_action({'action': 'plan', 'track': 'coding'})['result']
    assert again == assignment
    assert study_store.workbench('coding')['pending'][0]['item']['name'] == 'Contains Duplicate'
    request = {'action': 'feedback', 'track': 'coding', 'assignment': assignment['id'],
               'feedback': {'duration': 25, 'confidence': 3, 'independent': False,
                            'hint_level': 2, 'solution_viewed': False,
                            'lesson': 'Used a set, checked empty input.'}}
    response = study_store.study_action(request)
    assert response['result']['hint_level'] == 2
    assert study_store.study_action(request) == response
    state = study_store.coach_state()
    assert len(state['coding']) == 1
    assert not study_store.workbench('coding')['pending']
    assert state['coding'][0]['next_review_date'] > state['coding'][0]['date']


def test_feedback_rejects_bad_track_values_and_changed_retries(study_store):
    assignment = study_store.study_action({'action': 'plan', 'track': 'system_design'})['result']
    request = {'action': 'feedback', 'track': 'system_design', 'assignment': assignment['id'],
               'feedback': {'duration': 45, 'confidence': 3, 'requirements_score': 4,
                            'architecture_score': 3, 'trade_off_score': 2,
                            'failure_mode_score': 2, 'next_improvement': 'Explain queue failures.'}}
    with pytest.raises(ValueError):
        study_store.study_action({**request, 'track': 'coding'})
    with pytest.raises(ValueError):
        study_store.study_action({**request, 'feedback': {**request['feedback'], 'confidence': 99}})
    study_store.study_action(request)
    with pytest.raises(ValueError):
        study_store.study_action({**request, 'feedback': {**request['feedback'], 'duration': 55}})
    assert study_store.coach_state()['system_design'][0]['duration'] == 45


def test_srs_review_stale_click_does_not_promote_twice(study_store):
    request = {'action': 'srs_review', 'card': 'one', 'result': 'correct', 'expected_reviews': 0}
    study_store.study_action(request)
    with pytest.raises(ValueError, match='already changed'):
        study_store.study_action(request)
    deck = json.loads((study_store.home / 'data/english/srs_deck.json').read_text())
    assert deck['cards']['one']['box'] == 2
    assert deck['cards']['one']['reviews'] == 1
    assert study_store.workbench('english')['due_count'] == 1


def test_srs_concurrent_cards_preserve_both_reviews(study_store):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(study_store.study_action, [
            {'action': 'srs_review', 'card': card, 'result': 'wrong', 'expected_reviews': 0}
            for card in ('one', 'two')]))
    assert all(r['saved'] for r in results)
    deck = json.loads((study_store.home / 'data/english/srs_deck.json').read_text())
    assert [c['reviews'] for c in deck['cards'].values()] == [1, 1]


def test_notes_preserve_versions_and_reject_stale_writes(store):
    first = store.study_action({'action': 'note', 'room': 'interview', 'note': 'First answer', 'revision': 0})
    assert first['revision'] == 1
    with pytest.raises(ValueError, match='다른 화면'):
        store.study_action({'action': 'note', 'room': 'interview', 'note': 'Stale answer', 'revision': 0})
    store.study_action({'action': 'note', 'room': 'interview', 'note': 'Second answer', 'revision': 1})
    assert store.workbench('interview')['note'] == 'Second answer'
    archive = store.library('workspace')
    assert archive['total'] == 2
    assert archive['items'][1]['content'] == 'First answer'


def test_bookmarks_require_catalog_paper_and_persist_read_status(store):
    folder = store.home / 'data/papers'
    folder.mkdir(parents=True)
    conn = sqlite3.connect(folder / 'papers.db')
    conn.executescript("CREATE TABLE papers(id TEXT,title TEXT,url TEXT); INSERT INTO papers VALUES('p1','Title','https://example.com/p1');")
    conn.close()
    store.study_action({'action': 'bookmark', 'paper': 'p1', 'revision': 0})
    assert store.workbench('hq')['reading_count'] == 1
    store.study_action({'action': 'paper_read', 'paper': 'p1', 'read': True, 'revision': 1})
    assert store.workbench('hq')['reading_count'] == 0
    with pytest.raises(ValueError):
        store.study_action({'action': 'bookmark', 'paper': "p1' OR 1=1", 'revision': 2})


def test_http_actions_require_same_origin_json_and_action_header(store):
    assets = Path(__file__).resolve().parents[1] / 'browser/observatory'
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(store, assets, {'127.0.0.1'}))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = 'http://127.0.0.1:' + str(server.server_port)
    payload = json.dumps({'action': 'note', 'room': 'hq', 'revision': 0, 'note': 'My next step'})
    def request(headers):
        conn = HTTPConnection(*server.server_address)
        conn.request('POST', '/api/action', body=payload, headers=headers)
        response = conn.getresponse()
        status = response.status
        response.read()
        conn.close()
        return status
    base = {'Content-Type': 'application/json', 'X-Hermes-Action': '1', 'Origin': origin}
    try:
        assert request({**base, 'Origin': 'http://evil.example'}) == 403
        assert request({**base, 'Origin': ''}) == 403
        assert request({**base, 'X-Hermes-Action': ''}) == 403
        assert request({**base, 'Content-Type': 'text/plain'}) == 400
        assert not (store.home / 'data/observatory/workspace.json').exists()
        assert request(base) == 200
        assert store.notebook()['notes']['hq'] == 'My next step'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_hq_orchestration_reads_board_and_maps_specialist_rooms(store, monkeypatch):
    executable = Path('/bin/true')
    store.hermes_cli = executable
    task = {'id': 't_1234abcd', 'title': 'Read agent papers', 'body': 'Find evidence',
            'assignee': 'papers', 'status': 'running', 'priority': 80,
            'created_at': 1789150000, 'result': None}

    def run(command, **kwargs):
        assert command[:4] == [str(executable), 'kanban', '--board', 'hermes-hq']
        if command[4] == 'list':
            output = [task]
        elif command[4] == 'assignees':
            output = [{'name': 'default', 'on_disk': True, 'counts': {}},
                      {'name': 'papers', 'on_disk': True, 'counts': {'running': 1}},
                      {'name': 'clawgram', 'on_disk': True, 'counts': {}}]
        else:
            raise AssertionError(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps(output), stderr='')

    monkeypatch.setattr('observatory.subprocess.run', run)
    board = store.orchestration()
    assert board['available'] is True, board
    assert board['tasks'][0]['room'] == 'papers'
    assert board['counts'] == {'running': 1}
    assert [row['name'] for row in board['assignees']] == ['default', 'papers']


def test_hq_mission_actions_validate_and_use_fixed_cli_arguments(store, monkeypatch):
    executable = Path('/bin/true')
    store.hermes_cli = executable
    calls = []
    task = {'id': 't_1234abcd', 'title': 'Goal', 'body': 'Context',
            'assignee': 'default', 'status': 'triage', 'priority': 50,
            'created_at': 1789150000, 'result': None}

    def run(command, **kwargs):
        calls.append(command)
        action = command[4]
        if action == 'create':
            output = task
        elif action == 'show':
            output = {'task': dict(task), 'latest_summary': None, 'parents': [],
                      'children': [], 'comments': [], 'events': [], 'runs': []}
        elif action == 'assignees':
            output = [{'name': 'default', 'on_disk': True, 'counts': {}},
                      {'name': 'papers', 'on_disk': True, 'counts': {}}]
        elif action in ('assign', 'comment', 'block', 'unblock'):
            return SimpleNamespace(returncode=0, stdout='ok\n', stderr='')
        else:
            raise AssertionError(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps(output), stderr='')

    monkeypatch.setattr('observatory.subprocess.run', run)
    request_id = '11111111-1111-4111-8111-111111111111'
    response = store.study_action({'action': 'mission_create',
                                   'goal': 'Goal; touch /tmp/never',
                                   'context': 'Only summarize.', 'priority': 80,
                                   'request_id': request_id})
    assert response['task']['id'] == 't_1234abcd'
    create = calls[0]
    assert create[5] == 'Goal; touch /tmp/never'
    assert create[create.index('--idempotency-key') + 1] == 'hq:' + request_id
    assert '--triage' in create and '--max-runtime' in create
    store.study_action({'action': 'mission_assign', 'task': 't_1234abcd',
                        'assignee': 'papers'})
    assert any(call[4:7] == ['assign', 't_1234abcd', 'papers'] for call in calls)
    with pytest.raises(ValueError):
        store.study_action({'action': 'mission_create', 'goal': 'short',
                            'context': '', 'priority': 101, 'request_id': request_id})
    with pytest.raises(ValueError):
        store.mission_detail('../../secret')
    with pytest.raises(ValueError, match='캠퍼스'):
        store.study_action({'action': 'mission_assign', 'task': 't_1234abcd',
                            'assignee': 'clawgram'})
