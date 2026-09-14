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

import observatory as observatory_module
from observatory import (Observatory, date_range, make_handler,
                         notification_excerpt, redact, room_for)


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
    assert room_for('david', 'observatory_coding', '', []) == 'coding'


def test_podcast_cron_uses_its_own_room_on_shared_english_profile():
    jobs = [{'id': 'pod', 'name': 'english-podcast-daily'}]
    prompt = 'Use the english-podcast-coach skill for the English Goal Podcast lesson.'
    assert room_for('english', 'cron_pod_20260913', prompt, jobs) == 'podcast'
    assert room_for('english', 'cron_old_20260912', prompt, []) == 'podcast'
    assert room_for('english', 'telegram_chat', 'Review my correction.', jobs) == 'english'


def test_redaction_preserves_metrics_but_masks_credentials():
    data = {'input_tokens': 123, 'api_key': 'something', 'body':
            'bot123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ_123456789\nPASSWORD=abc\nBearer abcdef'}
    output = redact(data)
    assert output['input_tokens'] == 123
    assert output['api_key'] == '[redacted]'
    assert 'PASSWORD=abc' not in output['body']
    assert 'Bearer abcdef' not in output['body']
    assert 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' not in output['body']


def test_notification_excerpt_uses_first_meaningful_line_and_stays_compact():
    content = '\n---\n## **Today:** [Production RAG](https://example.com) ' + 'x' * 120
    excerpt = notification_excerpt(content, limit=50)
    assert excerpt.startswith('Today: Production RAG')
    assert len(excerpt) == 50
    assert excerpt.endswith('…')
    assert notification_excerpt('[SILENT]') == ''


def test_overview_exposes_actual_cron_response_as_room_notice(store):
    hq = next(room for room in store.overview()['rooms'] if room['id'] == 'hq')
    assert hq['notice']['text'] == 'Hello English'
    assert hq['action'] == {'title': '오늘의 우선순위', 'detail': '팀의 다음 흐름 확인'}
    coding = next(room for room in store.overview()['rooms'] if room['id'] == 'coding')
    assert coding['notice'] is None
    assert coding['action']['title'] == '코딩 과제'


def test_coding_workbench_exposes_only_safe_leetcode_snapshot(store):
    path = store.home / 'data/interview/leetcode_history.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        'version': 1, 'username': 'david_choi', 'synced_at': '2026-09-14T12:00:00+00:00',
        'total_solved': 12, 'solved_by_difficulty': {'easy': 5, 'medium': 6, 'hard': 1},
        'recent_accepted': [{'title': 'Two Sum', 'slug': 'two-sum'}],
        'session': 'must-not-leak',
    }))

    history = store.workbench('coding')['leetcode_history']

    assert history['username'] == 'david_choi'
    assert history['recent_accepted'][0]['title'] == 'Two Sum'
    assert 'session' not in history


def test_observatory_chats_clear_sent_drafts_and_support_shift_enter():
    root = Path(__file__).resolve().parents[1] / 'browser/observatory'
    workbench = (root / 'workbench.js').read_text()
    office = (root / 'office.js').read_text()
    assert 'event.key === "Enter" && event.shiftKey' in workbench
    assert 'field.value = "";' in workbench
    assert 'const message = field.value.trim();' in workbench
    assert 'message,' in workbench
    assert 'form.requestSubmit();' in workbench
    assert 'event.key === "Enter" && event.shiftKey' in office
    assert '$("office-chat-form").requestSubmit();' in office
    assert 'localWrite("office-draft:" + room, null)' in office
    assert '$("office-message").value = "";' in office


def test_completion_lesson_display_preserves_saved_line_breaks():
    root = Path(__file__).resolve().parents[1] / 'browser/observatory'
    assert 'class="completion-lesson"' in (root / 'workbench.js').read_text()
    css = (root / 'workbench.css').read_text()
    assert '.completion-lesson' in css
    assert 'white-space: pre-wrap' in css


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


@pytest.mark.parametrize('room', ['hq', 'papers', 'interview', 'coding', 'design', 'english', 'podcast'])
def test_office_chat_persists_separate_session_without_delivery(store, monkeypatch, room):
    calls = []
    def agent_api(method, path, payload=None, **kwargs):
        calls.append((method, path, payload))
        if method == 'GET':
            return {'_status': 404}
        return {'message': {'content': '안녕하세요!'}}
    monkeypatch.setattr(store, 'agent_api', agent_api)
    monkeypatch.setattr(store, 'telegram_send', lambda *args: pytest.fail('Office chat must not send Telegram'))
    result = store.study_action({'action': 'office_chat', 'room': room, 'message': '안녕'})
    assert result['response'] == '안녕하세요!'
    assert calls[1][2]['id'] == 'office_' + room
    assert calls[2][1] == '/api/sessions/office_' + room + '/chat'
    assert 'Do not modify' in calls[2][2]['instructions']
    if room == 'english':
        assert 'You are Ellie, a friendly female English conversation tutor' in calls[2][2]['instructions']
        assert calls[1][2]['title'] == 'Ellie · Office conversation'
    assert room_for('david', 'office_' + room, '', []) == room
    assert not store.office_locks[room].locked()


def test_office_read_is_inert_and_room_validation_is_closed(store, monkeypatch):
    monkeypatch.setattr(store, 'agent_api', lambda *args, **kwargs: pytest.fail('Read invoked model'))
    assert store.office_conversation('english')['history'] == []
    for room in ('../../', 'unknown', [], None):
        with pytest.raises(ValueError):
            store.office_conversation(room)
        with pytest.raises(ValueError):
            store.office_chat({'room': room, 'message': 'hi'})


def test_office_chat_lock_released_after_model_failure(store, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError('offline')
    monkeypatch.setattr(store, 'agent_api', fail)
    with pytest.raises(OSError):
        store.office_chat({'room': 'hq', 'message': 'hi'})
    assert not store.office_locks['hq'].locked()
    store.office_locks['hq'].acquire()
    try:
        with pytest.raises(ValueError, match='답변 중'):
            store.office_chat({'room': 'hq', 'message': 'hi'})
    finally:
        store.office_locks['hq'].release()


def test_agent_api_fails_fast_with_a_clear_gateway_error(store, monkeypatch):
    store.agent_api_key = 'local-secret'
    seen = {}

    def timeout(request, timeout):
        seen['timeout'] = timeout
        raise TimeoutError
    monkeypatch.setattr(observatory_module, 'urlopen', timeout)
    with pytest.raises(OSError, match='gateway가 응답하지 않습니다'):
        store.agent_api('GET', '/health')
    assert seen['timeout'] == 15


def test_office_history_excludes_system_and_other_characters(store):
    conn = sqlite3.connect(store.home / 'state.db')
    conn.execute("INSERT INTO messages VALUES(11,'office_english','assistant','Hello!',NULL,NULL,2,NULL)")
    conn.execute("INSERT INTO messages VALUES(12,'office_english','system','hidden',NULL,NULL,3,NULL)")
    conn.execute("INSERT INTO messages VALUES(13,'office_podcast','assistant','Other',NULL,NULL,4,NULL)")
    conn.commit()
    conn.close()
    assert [row['content'] for row in store.office_conversation('english')['history']] == ['Hello!']


def test_room_presence_distinguishes_ambient_live_and_blocked(store):
    board = store.home / 'kanban/boards/hermes-hq'
    board.mkdir(parents=True)
    conn = sqlite3.connect(board / 'kanban.db')
    conn.execute('''CREATE TABLE tasks(
        id TEXT, title TEXT, status TEXT, assignee TEXT, created_at INTEGER)''')
    conn.executemany('INSERT INTO tasks VALUES(?,?,?,?,?)', [
        ('t_11111111', 'Run coding mission', 'running', 'coding', 2),
        ('t_22222222', 'Review a design issue', 'blocked', 'design', 1),
    ])
    conn.commit()
    conn.close()

    presence = store.room_presence([{
        'profile': 'david', 'alive': True, 'active_agents': 1,
    }])
    assert presence['coding']['mode'] == 'working'
    assert presence['coding']['task'] == 'Run coding mission'
    assert presence['design']['mode'] == 'blocked'
    assert presence['hq']['source'] == 'gateway'
    assert presence['papers']['mode'] == 'ambient'


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


def test_podcast_room_reuses_english_profile_and_lists_its_schedule(store):
    profile = store.home / 'profiles' / 'english'
    profile.mkdir(parents=True)
    shutil.copyfile(store.home / 'state.db', profile / 'state.db')
    (profile / 'cron').mkdir()
    (profile / 'cron/jobs.json').write_text(json.dumps({'jobs': [{
        'id': 'pod', 'name': 'english-podcast-daily', 'enabled': True,
        'schedule_display': '0 9 * * *', 'deliver': 'telegram:-99',
    }]}))

    room = next(room for room in store.overview()['rooms'] if room['id'] == 'podcast')
    assert room['title'] == 'Morning Echo'
    assert room['profile'] == 'english'
    assert [job['name'] for job in room['jobs']] == ['english-podcast-daily']


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
        status, body, headers = request('/assets/hermes-agent-cast.png')
        assert status == 200
        assert headers['Content-Type'] == 'image/png'
        assert body.startswith(b'\x89PNG')
        status, body, headers = request('/assets/ellie-english-tutor.png')
        assert status == 200
        assert headers['Content-Type'] == 'image/png'
        assert body.startswith(b'\x89PNG')
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
    for room in ('coding', 'design', 'english', 'podcast', 'hq', 'interview'):
        data = study_store.workbench(room)
        assert data['room'] == room
    assert not (study_store.home / 'data/interview/coach_state.json').exists()
    assert not (study_store.home / 'data/observatory/workspace.json').exists()


def test_podcast_workbench_reports_downloaded_transcripts_without_exposing_paths(store):
    root = store.home / 'data/english-podcast'
    (root / 'metadata').mkdir(parents=True)
    (root / 'transcripts').mkdir()
    video_id = 'abc123XYZ00'
    (root / 'state.json').write_text(json.dumps({'assignments': {
        '2026-09-13': {'video_id': video_id, 'title': 'Speak with Confidence',
                       'url': 'https://youtube.com/watch?v=' + video_id,
                       'prepared_at': 1, 'delivered_at': None},
    }}))
    (root / 'metadata' / f'{video_id}.json').write_text(json.dumps({
        'word_count': 1420, 'caption_kind': 'auto',
        'transcript_path': '/private/path/that/must/not/be/exposed',
    }))
    (root / 'transcripts' / f'{video_id}.txt').write_text('transcript')

    result = store.workbench('podcast')
    assert result['episode_count'] == 1
    assert result['transcript_count'] == 1
    assert result['latest_episode']['title'] == 'Speak with Confidence'
    assert result['latest_episode']['transcript_available'] is True
    assert 'transcript_path' not in result['latest_episode']


def test_room_chat_uses_fixed_destination_and_persisted_agent_session(store, monkeypatch):
    store.agent_api_key = 'local-secret'
    calls = []
    deliveries = []

    def agent_api(method, path, payload=None, allow_status=(), **kwargs):
        calls.append((method, path, payload, allow_status, kwargs))
        if method == 'GET':
            return {'_status': 404}
        if path == '/api/sessions':
            return {'session': {'id': payload['id']}}
        return {'message': {'role': 'assistant', 'content': '먼저 접근 방법을 설명해 주세요.'}}

    monkeypatch.setattr(store, 'agent_api', agent_api)
    monkeypatch.setattr(store, 'telegram_send', lambda target, text: deliveries.append((target, text)))
    message = '현재 문제 접근을 봐줘; touch /tmp/never'
    result = store.study_action({'action': 'room_chat', 'room': 'coding', 'message': message})

    assert result['session'] == 'observatory_coding'
    assert result['delivered'] is True
    assert calls[1][2]['id'] == 'observatory_coding'
    assert calls[2][1] == '/api/sessions/observatory_coding/chat'
    assert calls[2][2]['message'] == message
    assert 'hint ladder' in calls[2][2]['instructions']
    assert calls[2][4]['timeout'] == 600
    assert deliveries[0][0] == 'telegram:-12'
    assert message in deliveries[0][1] and result['response'] in deliveries[0][1]


def test_room_chat_rejects_unmapped_rooms_and_preserves_answer_on_delivery_failure(store, monkeypatch):
    store.agent_api_key = 'local-secret'
    with pytest.raises(ValueError, match='연결된 Telegram'):
        store.study_action({'action': 'room_chat', 'room': 'hq', 'message': 'hello'})
    with pytest.raises(ValueError):
        store.study_action({'action': 'room_chat', 'room': 'coding', 'message': ''})

    monkeypatch.setattr(store, 'ensure_dashboard_session', lambda room: 'observatory_coding')
    monkeypatch.setattr(store, 'agent_api', lambda *args, **kwargs: {
        'message': {'content': 'Saved answer'}})
    monkeypatch.setattr(store, 'telegram_send', lambda *args: (_ for _ in ()).throw(
        OSError('Telegram 그룹에 답변을 전송하지 못했습니다.')))
    result = store.room_chat({'room': 'coding', 'message': 'question'})
    assert result['response'] == 'Saved answer'
    assert result['delivered'] is False
    assert '전송하지 못했습니다' in result['delivery_error']


def test_dashboard_chat_history_and_fixed_telegram_target(store):
    conn = sqlite3.connect(store.home / 'state.db')
    conn.execute("INSERT INTO sessions VALUES('observatory_coding','api_server','Chat',1789152000,NULL,NULL,'local',2,0,1,1)")
    conn.execute("INSERT INTO messages VALUES(5,'observatory_coding','user','question',NULL,NULL,1789152001,NULL)")
    conn.execute("INSERT INTO messages VALUES(6,'observatory_coding','assistant','answer',NULL,NULL,1789152002,NULL)")
    conn.commit()
    conn.close()

    assert [row['content'] for row in store.room_chat_history('coding')] == ['question', 'answer']
    assert store.sessions(room='coding')['items'][0]['id'] == 'observatory_coding'
    with pytest.raises(OSError, match='대상'):
        store.telegram_send('telegram:not-a-chat', 'message')


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

    next_assignment = study_store.study_action({'action': 'plan', 'track': 'coding'})['result']
    assert next_assignment['id'].endswith(':2')
    assert next_assignment['item_id'] == 'valid-anagram'
    bench = study_store.workbench('coding')
    assert bench['pending'][0]['id'] == next_assignment['id']
    assert bench['today_assignment'] == next_assignment
    assert study_store.study_action({'action': 'plan', 'track': 'coding'})['result'] == next_assignment


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


def test_review_action_is_explicit_and_new_problem_action_stays_new(study_store):
    assignment = study_store.study_action({'action': 'plan', 'track': 'coding'})['result']
    study_store.study_action({'action': 'feedback', 'track': 'coding', 'assignment': assignment['id'],
                              'feedback': {'duration': 25, 'confidence': 2, 'independent': False,
                                           'hint_level': 2, 'solution_viewed': False,
                                           'lesson': 'Need more HashMap practice.'}})
    review = study_store.study_action({'action': 'plan', 'track': 'coding', 'mode': 'review'})['result']
    assert review['item_id'] == 'contains-duplicate'
    assert review['reason'] == 'requested review'


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
    assert [row['name'] for row in board['assignees']] == [
        'default', 'papers', 'clawgram',
    ]


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
    assert 'self-contained result' in create[create.index('--body') + 1]
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
                            'assignee': 'rogue'})
