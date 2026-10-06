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


def test_hq_chatgpt_readiness_excludes_titles_links_and_account_data(store):
    import chatgpt_archive
    root = store.home / 'data/chatgpt'
    chatgpt_archive.save_json(root / 'browser-status.json', {
        'browser_status': 'awaiting_login', 'export_status': 'requested',
        'email': 'private@example.com', 'export_link': 'signed-private-link'})
    path = root / 'input.json'
    path.write_text(json.dumps([{'id': 'private-id', 'title': 'private-title', 'current_node': 'one',
                               'mapping': {'one': {'parent': None, 'message': {
                                   'author': {'role': 'user'}, 'content': {
                                       'content_type': 'text', 'parts': ['private-message']}}}}}]))
    chatgpt_archive.import_export(path, root)
    result = store.chatgpt_archive_status()
    assert result['conversation_count'] == 1
    assert result['message_count'] == 1
    assert result['export_status'] == 'requested'
    assert 'private' not in json.dumps(result)
    assert room_for('david', 'office_hq', 'ChatGPT archive', []) == 'hq'


def test_hq_chatgpt_status_reports_corruption_without_exposing_records(store):
    root = store.home / 'data/chatgpt'
    root.mkdir(parents=True)
    (root / 'archive.db').write_text('private broken database')
    result = store.chatgpt_archive_status()
    assert result['error'] == 'Source status unavailable'
    assert 'private' not in json.dumps(result)


def test_project_rag_status_exposes_only_readiness_name_and_counts(store, monkeypatch):
    calls = []
    def helper(name, args, **kwargs):
        calls.append((name, args))
        return {'ready': True, 'project_name': 'Career 2027', 'conversation_count': 9,
                'message_count': 116, 'chunk_count': 254, 'dimensions': 384,
                'indexed_at': '2026-10-04T12:00:00+00:00', 'source_complete': True,
                'messages': 'PRIVATE CONTENT', 'source_fingerprint': 'PRIVATE HASH',
                'cookies': 'PRIVATE TOKEN'}
    monkeypatch.setattr(store, 'helper', helper)
    result = store.chatgpt_project_rag_status()
    assert result['ready'] is True and result['conversation_count'] == 9
    assert result['source_complete'] is False
    assert 'PRIVATE' not in json.dumps(result)
    assert calls == [('chatgpt_rag.py', ['--data-dir', str(store.home / 'data/chatgpt'), 'status'])]


def test_project_rag_failure_never_exposes_library_exception(store, monkeypatch):
    def helper(*args, **kwargs):
        raise OSError('PRIVATE CONTENT account@example.com')
    monkeypatch.setattr(store, 'helper', helper)
    result = store.chatgpt_project_rag_status()
    assert result['ready'] is False and 'PRIVATE' not in json.dumps(result)


def test_hq_browser_index_is_distinct_from_an_imported_export(store):
    import chatgpt_archive
    root = store.home / 'data/chatgpt'
    chatgpt_archive.save_json(root / 'browser-index.json', {
        'captured_at': '2026-10-04T00:00:00+00:00', 'complete': False,
        'conversations': [{'id': 'private-id', 'title': 'private-title', 'url': 'private-url'}]})
    chatgpt_archive.save_json(root / 'browser-status.json', {'export_status': 'verification_loop'})
    result = store.chatgpt_archive_status()
    assert result['sidebar_conversation_count'] == 1
    assert result['conversation_count'] == 0
    assert result['sidebar_complete'] is False
    assert result['export_status'] == 'verification_loop'
    assert 'private' not in json.dumps(result)


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
    assert room_for('english', 'telegram_chat', 'Run youtube_browser_login.py for login.', jobs) == 'podcast'
    assert room_for('english', 'cron_old_20260912', 'Run youtube_browser_login.py for login.', []) == 'podcast'
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


def test_background_sync_stays_searchable_but_not_in_recent_activity(store):
    jobs_path = store.home / 'cron/jobs.json'
    jobs = json.loads(jobs_path.read_text())
    jobs['jobs'].append({
        'id': 'sync', 'name': 'leetcode-history-sync', 'deliver': None, 'enabled': True,
    })
    jobs_path.write_text(json.dumps(jobs))
    conn = sqlite3.connect(store.home / 'state.db')
    conn.execute('''INSERT INTO sessions VALUES(
        'cron_sync_20260921','cron','Refresh snapshot',1789152000,1789152010,
        'done','local',2,1,20,2)''')
    conn.execute('''INSERT INTO messages VALUES(
        20,'cron_sync_20260921','user',
        'Refresh the opt-in LeetCode history snapshot. Run python3 ~/.hermes/scripts/leetcode_sync.py sync.',
        NULL,NULL,1789152001,NULL)''')
    conn.execute('''INSERT INTO messages VALUES(
        21,'cron_sync_20260921','assistant','[SILENT]',NULL,NULL,1789152002,'stop')''')
    conn.commit()
    conn.close()

    archived = store.sessions(q='opt-in LeetCode history')['items']
    assert archived[0]['id'] == 'cron_sync_20260921'
    assert archived[0]['background_maintenance'] is True
    assert [item['id'] for item in store.workbench('coding')['recent']] == ['s1']
    overview = store.overview()
    assert 'cron_sync_20260921' not in {item['id'] for item in overview['recent']}
    coding = next(room for room in overview['rooms'] if room['id'] == 'coding')
    assert coding['latest']['id'] == 's1'


def test_reward_digest_routes_to_existing_hq_room():
    jobs = [{"id": "reward", "name": "career-rewards-daily"}]
    prompt = "Run reward_system.py notify for Career Cash."

    assert room_for("david", "cron_reward_20260915", prompt, jobs) == "hq"


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


def test_coding_login_status_exposes_fixed_local_port_without_credentials(store, monkeypatch):
    monkeypatch.setattr(store, 'refresh_leetcode_sources', lambda: None)
    path = store.home / 'data/interview/leetcode-login-status.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'status': 'awaiting_login', 'web_port': 1234,
                                'session': 'PRIVATE', 'password': 'PRIVATE'}))
    status = store.workbench('coding')['leetcode_login']
    assert status == {'status': 'awaiting_login', 'web_port': 18782,
                      'url': '/leetcode-login/vnc.html?autoconnect=true&resize=scale&path=leetcode-login/websockify'}
    assert 'PRIVATE' not in json.dumps(status)


def test_login_action_uses_fixed_helper_and_rejects_other_rooms(store, monkeypatch):
    calls = []
    monkeypatch.setattr(store, 'helper', lambda name, args, **kw: calls.append((name, args)) or {'status': 'awaiting_login'})
    assert store.study_action({'action': 'leetcode_login', 'room': 'coding', 'command': 'untrusted'})['saved']
    assert calls == [('leetcode_browser_login.py', ['--start'])]
    with pytest.raises(ValueError, match='Jun'):
        store.study_action({'action': 'leetcode_login', 'room': 'english'})


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


def test_office_visually_celebrates_verified_rewards():
    root = Path(__file__).resolve().parents[1] / 'browser/observatory'
    office = (root / 'office.js').read_text()
    office_css = (root / 'office.css').read_text()
    workbench = (root / 'workbench.js').read_text()

    assert 'reward-hud' in office
    assert 'celebrateReward' in office
    assert 'REWARD UNLOCKED' in office_css
    assert '@keyframes reward-coin' in office_css
    assert 'CAREER CASH · GAME REWARD' in workbench


def test_office_reward_hud_opens_cash_earning_guide():
    root = Path(__file__).resolve().parents[1] / 'browser/observatory'
    office = (root / 'office.js').read_text()
    office_css = (root / 'office.css').read_text()

    assert 'id="reward-guide"' in office
    assert 'toggleRewardGuide' in office
    assert 'renderRewardGuide' in office
    assert 'data-reward-room' in office
    assert '이번 주 미션 전체 완료' in office
    assert '.reward-guide' in office_css


def test_design_workbench_does_not_render_coding_only_leetcode_card():
    workbench = (Path(__file__).resolve().parents[1] /
                 'browser/observatory/workbench.js').read_text()

    assert 'const lcSummary = d.room !== "coding" ? "" : codingReviewCard(d)' in workbench


def test_office_randomizes_short_next_action_conversations():
    office = (Path(__file__).resolve().parents[1] /
              'browser/observatory/office.js').read_text()

    assert 'lastVisitRoom' in office
    assert 'lastNoticeRoom' in office
    assert 'visitDeck = shuffled(leaderVisits)' in office
    assert 'visitDeck.splice(index, 1)[0]' in office
    assert 'lastLeaderTalk.set(partner, lines)' in office
    assert 'variants.filter(lines => lines !== previous)' in office
    assert 'scene.rooms.every(room => actors.has(room))' in office
    assert 'scene.turns[3][0], scene.turns[3][1]' in office
    assert 'showBubble("hq", lines[2], "dialogue")' in office
    assert 'showBubble(partner, lines[3], "dialogue")' in office
    assert 'finishTalk(11800)' in office
    assert 'showBubble(scene[0], notificationLine(scene[0])' not in office
    assert 'showBubble(scene[1], notificationLine(scene[1])' not in office
    assert 'return `${action.title} · ${action.detail}`' in office
    assert '3200 + Math.random() * 2800' in office
    assert 'routineIndex++ % leaderVisits.length' not in office


def test_fold_layout_keeps_small_bubbles_attached_to_characters():
    root = Path(__file__).resolve().parents[1] / 'browser/observatory'
    office = (root / 'office.js').read_text()
    css = (root / 'office.css').read_text()

    assert 'class="walk-bubble" role="status" aria-live="polite"' in office
    assert 'office-compact-caption' not in office
    assert 'container: office / inline-size' in css
    assert '@container office (max-width: 900px)' in css
    assert '.walk-name small, .walk-name i { display: none; }' in css
    assert '.walk-bubble { max-width: 150px; padding: 6px 8px' in css
    assert '.walk-bubble { display: none' not in css
    assert 'separateBubbles("hq", partner)' in office
    assert 'finishTalk(11800)' in office
    assert 'followupTimer = setTimeout(() => showBubble("hq", lines[2]' in office
    assert '.bubble-shift-left { --bubble-shift: -55px; }' in css
    assert '.bubble-shift-right { --bubble-shift: 55px; }' in css
    assert 'translateX(-50%) translateX(var(--bubble-shift, 0px))' in css
    assert '#office-roster { grid-template-columns: repeat(2' in css


def test_office_auto_fits_partial_laptop_windows_before_manual_zoom():
    root = Path(__file__).resolve().parents[1] / 'browser/observatory'
    office = (root / 'office.js').read_text()
    css = (root / 'office.css').read_text()

    assert 'new ResizeObserver(() => setOfficeZoom(officeZoom, null, false))' in office
    assert 'const referenceWidth = Math.max(780, viewport.clientWidth)' in office
    assert 'const fitScale = Math.min(1, viewport.clientWidth / referenceWidth)' in office
    assert 'const floorWidth = referenceWidth / Math.min(1, officeZoom)' in office
    assert 'const scale = Math.round(fitScale * officeZoom * 1000) / 1000' in office
    assert 'floor.dataset.scale = String(scale)' in office
    assert 'min-width: 0; aspect-ratio: 1000 / 560' in css


def test_desktop_sidebar_collapses_and_persists_without_hiding_mobile_nav():
    root = Path(__file__).resolve().parents[1] / 'browser/observatory'
    html = (root / 'index.html').read_text()
    app = (root / 'app.js').read_text()
    css = (root / 'style.css').read_text()

    assert 'id="sidebar-toggle"' in html
    assert 'aria-controls="sidebar"' in html
    assert 'readUiPreference("hermes-sidebar-collapsed", false)' in app
    assert 'writeUiPreference("hermes-sidebar-collapsed", sidebarCollapsed)' in app
    assert 'document.documentElement.classList.toggle("sidebar-collapsed"' in app
    assert 'html.sidebar-collapsed main { margin-left: 0; }' in css
    assert 'html.sidebar-collapsed .sidebar { transform: translateX(-100%); }' in css
    assert '.sidebar-toggle { display: none; }' in css


def test_missing_sources_are_empty_and_db_is_readonly(store):
    assert store.library('learning')['total'] == 0
    assert store.library('memory')['total'] == 0


def test_superseded_coach_assignments_leave_the_active_workbench(store):
    state = store.home / 'data/interview/coach_state.json'
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({'coding': [], 'system_design': [], 'assignments': {
        'old': {'id': 'old', 'track': 'coding', 'item_id': 'old', 'date': '2026-09-16',
                'completed': False, 'superseded': True},
        'new': {'id': 'new', 'track': 'coding', 'item_id': 'new', 'date': '2026-09-16',
                'completed': False},
    }}))

    assert [item['id'] for item in store.pending_assignments()] == ['new']
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
    if room == 'coding':
        assert calls[2][2]['instructions'].startswith('[jun-dialogue-mode:fast]\n')
    if room == 'hq':
        policy = calls[2][2]['instructions']
        assert 'chatgpt_rag.py' in policy
        assert 'Silicon Valley Career 2027' in policy
        assert 'read <chunk-id>' in policy and 'three rounds' in policy
        assert 'without an explicit scope expansion' in policy
    assert room_for('david', 'office_' + room, '', []) == room
    assert not store.office_locks[room].locked()


def test_jun_deep_mode_keeps_study_boundaries(store, monkeypatch):
    calls = []
    def api(method, path, payload=None, **kwargs):
        calls.append(payload)
        return {'message': {'content': '힌트'}}
    monkeypatch.setattr(store, 'agent_api', api)
    store.office_chat({'room': 'coding', 'message': '힌트', 'response_mode': 'deep'})
    assert calls[-1]['instructions'].startswith('[jun-dialogue-mode:deep]\n')
    assert 'Do not modify files, memories, schedules or study progress' in calls[-1]['instructions']
    with pytest.raises(ValueError, match='답변 방식'):
        store.office_chat({'room': 'coding', 'message': '힌트', 'response_mode': 'unknown'})
    assert not store.office_locks['coding'].locked()


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
        'schedule_display': '0 18 * * 1-5', 'deliver': 'telegram:-99',
    }, {
        'id': 'pod-review', 'name': 'english-podcast-weekend-review', 'enabled': True,
        'schedule_display': '0 18 * * 6,0', 'deliver': 'telegram:-99',
    }]}))

    room = next(room for room in store.overview()['rooms'] if room['id'] == 'podcast')
    assert room['title'] == 'Morning Echo'
    assert room['profile'] == 'english'
    assert {job['name'] for job in room['jobs']} == {'english-podcast-daily', 'english-podcast-weekend-review'}


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


def test_coding_workbench_shows_imported_learning_and_actual_practice_gap(study_store):
    today = observatory_module.datetime.now(observatory_module.TZ).date()
    accepted_date = (today - observatory_module.timedelta(days=4)).isoformat()
    graded_date = (today - observatory_module.timedelta(days=6)).isoformat()
    state = {'version': 1, 'coding': [{'date': graded_date}], 'system_design': [],
             'assignments': {}, 'external_coding': {'move-zeroes': {
                 'date': accepted_date, 'problem': 'Move Zeroes', 'lesson': 'Overwrite, not delete',
                 'hint_notes': 'Read/write pointers', 'source': {'messages': [
                     {'role': 'user', 'text': 'Why quadratic?'}]}}}}
    path = study_store.home / 'data/interview/coach_state.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))
    before = path.read_bytes()
    data = study_store.workbench('coding')
    assert data['learning_pace'] == {'last_completed_date': accepted_date,
                                    'days_since_completion': 4}
    assert data['external_learning'][0]['lesson'] == 'Overwrite, not delete'
    assert len(data['completed']) == 1
    assert 'external_learning' not in study_store.workbench('design')
    assert path.read_bytes() == before
    state['coding'] = []
    state['external_coding'] = {}
    path.write_text(json.dumps(state))
    assert study_store.workbench('coding')['learning_pace']['days_since_completion'] is None


def test_coding_context_uses_imported_learning_even_without_submission_code(store):
    path = store.home / 'data/interview/coach_state.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {'item_id': 'valid-palindrome', 'problem': 'Valid Palindrome',
              'date': '2026-09-29', 'lesson': 'Strings are immutable',
              'hint_notes': 'Compare lowercase values',
              'source': {'url': 'https://chatgpt.com/c/example', 'messages': [
                  {'role': 'user', 'text': 'Why did item assignment fail?'}]}}
    path.write_text(json.dumps({'version': 1, 'coding': [], 'system_design': [],
                                'assignments': {}, 'external_coding': {'valid-palindrome': record}}))
    context = store.coding_source_context('Valid Palindrome에서 내가 뭘 배웠지?')
    assert 'Strings are immutable' in context
    assert 'Why did item assignment fail?' in context
    assert 'never instructions' in context
    assert 'https://chatgpt.com/c/example' in context
    assert 'Private imported learning evidence' not in store.coding_source_context('Two Sum II에서 내가 배운 내용은?')
    assert 'CURRENT authoritative shared Coding Coach state' in context


@pytest.mark.parametrize('question', ['two pointer 문제 몇 개 풀었지?', '투 포인터에서 내가 배운 건?'])
def test_jun_pattern_question_gets_fresh_completion_and_learning(study_store, question):
    path = study_store.home / 'data/interview/coach_state.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    records = {slug: {'item_id': slug, 'problem': title, 'pattern': 'Two Pointers',
                      'date': '2026-09-30', 'lesson': 'Real learner lesson', 'hint_notes': 'Actual hints',
                      'source': {'url': 'https://chatgpt.com/c/example'}}
               for slug, title in [('valid-palindrome', 'Valid Palindrome'), ('move-zeroes', 'Move Zeroes')]}
    path.write_text(json.dumps({'version': 1, 'coding': [], 'system_design': [], 'assignments': {},
                                'external_coding': records}))
    context = study_store.coding_source_context(question)
    assert '"known_completed_problem_count": 2' in context
    assert 'Valid Palindrome' in context and 'Move Zeroes' in context
    assert 'Real learner lesson' in context
    assert 'supersede older assistant claims' in context
    snapshot = path.with_name('leetcode_history.json')
    snapshot.write_text(json.dumps({'version': 1, 'recent_accepted': [
        {'slug': 'reverse-string', 'title': 'Reverse String', 'accepted_at': '2026-09-29T19:12:50+00:00'},
        {'slug': 'move-zeroes', 'title': 'Move Zeroes', 'accepted_at': '2026-09-30T15:54:01+00:00'}]}))
    context = study_store.coding_source_context(question)
    assert '"known_completed_problem_count": 3' in context
    assert context.count('"problem": "Reverse String"') == 1
    assert 'implementation/learning unknown' in context
    assert 'Two Pointers: 3 completed problems' in context


def test_design_workbench_never_exposes_hidden_constraints_or_solution(study_store):
    study_store.study_action({'action': 'plan', 'track': 'system_design'})

    assignment = study_store.workbench('design')['pending'][0]

    assert assignment['item']['prompt']
    assert assignment['item']['clarification_questions']
    assert 'hidden_constraints' not in assignment['item']
    assert 'reference_solution' not in assignment['item']


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


def test_coding_chat_includes_matching_accepted_submission_as_evidence(store, monkeypatch):
    store.agent_api_key = 'local-secret'
    path = store.home / 'data/interview/leetcode_history.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'version': 1, 'accepted_solutions': [{
        'title': 'Valid Anagram', 'slug': 'valid-anagram', 'accepted_at': '2026-09-11T22:56:59+00:00',
        'language': 'Python3', 'code': 'class Solution:\n    def isAnagram(self, s, t):\n        return {}\n',
    }]}))
    calls = []
    def agent_api(method, path, payload=None, allow_status=(), **kwargs):
        calls.append((method, path, payload))
        if method == 'GET':
            return {'_status': 404}
        if path == '/api/sessions':
            return {'session': {'id': payload['id']}}
        return {'message': {'content': '실제 제출 코드를 설명합니다.'}}
    monkeypatch.setattr(store, 'agent_api', agent_api)
    monkeypatch.setattr(store, 'telegram_send', lambda *_args: None)

    store.room_chat({'room': 'coding', 'message': 'Anagram을 어떻게 풀었더라?'})

    instructions = calls[-1][2]['instructions']
    assert 'authoritative LeetCode evidence' in instructions
    assert 'Valid Anagram' in instructions
    assert 'def isAnagram' in instructions


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
    assert response['reward']['earned'] == 30
    repeated = study_store.study_action(request)
    assert repeated['result'] == response['result']
    assert repeated['reward']['earned'] == 0
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

    new_assignment = study_store.study_action(
        {'action': 'plan', 'track': 'coding', 'mode': 'next'}
    )['result']
    bench = study_store.workbench('coding')
    assert new_assignment['item_id'] == 'valid-anagram'
    assert bench['pending'][0]['id'] == new_assignment['id']
    assert bench['pending'][0]['session_type'] == 'new'
    assert bench['pending_reviews'][0]['id'] == review['id']


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


def test_podcast_workbench_exposes_dated_watch_history_without_browser_credentials(store):
    root = store.home / 'data/youtube-history'
    root.mkdir(parents=True)
    (root / 'snapshot.json').write_text(json.dumps({
        'date': '2000-01-01', 'synced_at': '2000-01-01T18:00:00-08:00',
        'channel_filter': 'English Goal Podcast, Daily English Podcast', 'selection': 'latest',
        'title_keyword': 'Podcast',
        'videos': [{'title': 'Watched', 'url': 'https://www.youtube.com/watch?v=abcdefghijk'}],
        'browser_path': '/private/browser', 'cookie': 'never expose',
    }))
    history = store.workbench('podcast')['watch_history']
    assert history['videos'][0]['title'] == 'Watched'
    assert history['selection'] == 'latest'
    assert history['title_keyword'] == 'Podcast'
    assert history['is_today'] is False
    assert 'cookie' not in history and 'browser_path' not in history


def test_historical_evening_history_sessions_stay_in_shared_podcast_room():
    assert room_for('english', 'cron_removed_20261003',
                    'Run youtube_history.py notify for evening watch-history.', []) == 'podcast'
    assert room_for('english', 'cron_removed_review',
                    'Run english_podcast.py review for weekend podcast review.', []) == 'podcast'


@pytest.mark.parametrize('practice_video,visible', [('abcdefghijk', True), ('bbbbbbbbbbb', False)])
def test_podcast_practice_matches_current_selected_video_and_exposes_only_source_fields(store, practice_video, visible):
    from datetime import datetime
    today = datetime.now(observatory_module.TZ).date().isoformat()
    history_root = store.home / 'data/youtube-history'
    history_root.mkdir(parents=True)
    (history_root / 'snapshot.json').write_text(json.dumps({'date': today, 'videos': [{
        'video_id': 'abcdefghijk', 'title': 'Selected', 'url': 'https://www.youtube.com/watch?v=abcdefghijk',
    }]}))
    root = store.home / 'data/english-podcast/watched'
    root.mkdir(parents=True)
    (root / 'practice.json').write_text(json.dumps({
        'lesson_date': today, 'video_id': practice_video, 'status': 'ready', 'caption_kind': 'automatic',
        'caption_path': '/private/source', 'cookie': 'never expose',
        'sentences': [{'source_quote': 'A source sentence.', 'timestamp': '01:00', 'patterns': [],
                       'url': 'https://www.youtube.com/watch?v=abcdefghijk&t=60', 'secret': 'never expose'}],
    }))
    practice = store.workbench('podcast')['long_sentence_practice']
    assert (practice is not None) is visible
    if visible:
        assert practice['sentences'][0]['source_quote'] == 'A source sentence.'
        assert 'never expose' not in json.dumps(practice)
        assert 'caption_path' not in practice


def test_weekend_review_workbench_exposes_current_week_sources_without_private_fields(store):
    from datetime import datetime
    today = datetime.now(observatory_module.TZ).date().isoformat()
    root = store.home / 'data/english-podcast/watched'
    root.mkdir(parents=True)
    (root / 'review.json').write_text(json.dumps({
        'lesson_date': today, 'week_start': today, 'status': 'ready', 'private_path': '/private',
        'episodes': [{'title': 'Weekday podcast', 'url': 'https://www.youtube.com/watch?v=abcdefghijk',
                      'source_dates': [today], 'secret': 'never expose'}],
    }))
    review = store.workbench('podcast')['podcast_review']
    assert review['episodes'][0]['title'] == 'Weekday podcast'
    assert 'never expose' not in json.dumps(review)
    assert 'private_path' not in review


def test_podcast_workbench_distinguishes_authenticated_login_from_pending_collection(store):
    root = store.home / 'data/youtube-history'
    root.mkdir(parents=True)
    (root / 'authentication.json').write_text(json.dumps({
        'version': 1, 'verified_at': '2026-10-03T18:00:00-07:00', 'cookie': 'never expose',
    }))
    state = store.workbench('podcast')['watch_history']
    assert state['authenticated'] is True
    assert state['connected'] is False
    assert state['authentication_verified_at'] == '2026-10-03T18:00:00-07:00'
    assert 'never expose' not in json.dumps(state)


@pytest.mark.parametrize('status', ['awaiting_login', 'verifying', 'connected', 'stopped', 'failed',
                                  'private-cookie-value', None])
def test_podcast_workbench_exposes_only_safe_interactive_login_state(store, status):
    root = store.home / 'data/youtube-history'
    root.mkdir(parents=True)
    (root / 'login-status.json').write_text(json.dumps({
        'status': status, 'cookie': 'never expose', 'browser_url': 'https://private.example',
    }))
    state = store.workbench('podcast')['watch_history']
    expected = status if status in ('awaiting_login', 'verifying', 'connected', 'stopped', 'failed') else None
    assert state['interactive_login_status'] == expected
    assert 'never expose' not in json.dumps(state)
    assert 'private-cookie-value' not in json.dumps(state)
    assert 'private.example' not in json.dumps(state)


def test_coding_workbench_refreshes_account_without_creating_coach_completions(store, monkeypatch):
    monkeypatch.setattr(store, 'refresh_leetcode_sources', lambda: None)
    root = store.home / 'data/interview'
    root.mkdir(parents=True)
    (root / 'leetcode_session.json').write_text('{}')
    calls = []
    def helper(name, args):
        calls.append((name, args))
        if name == 'leetcode_review.py':
            return {'items': [], 'ready_count': 0}
        (root / 'leetcode_history.json').write_text(json.dumps({
            'version': 1, 'username': 'david', 'total_solved': 99,
            'synced_at': '2026-10-04T00:00:00+00:00',
        }))
        return {'synced': True}
    monkeypatch.setattr(store, 'helper', helper)
    for _ in range(2):
        data = store.workbench('coding')
        assert data['leetcode_history']['total_solved'] == 99
        assert data['completed'] == []
        assert data['leetcode_refresh']['status'] == 'updated'
    assert calls == [('leetcode_sync.py', ['sync', '--stats-only']),
                     ('leetcode_review.py', ['list']), ('leetcode_review.py', ['list'])]


def test_coding_workbench_reports_stale_snapshot_on_account_failure(store, monkeypatch):
    monkeypatch.setattr(store, 'refresh_leetcode_sources', lambda: None)
    root = store.home / 'data/interview'
    root.mkdir(parents=True)
    (root / 'leetcode_session.json').write_text('{}')
    (root / 'leetcode_history.json').write_text(json.dumps({
        'version': 1, 'username': 'david', 'total_solved': 9,
    }))
    def helper(*_args):
        raise ValueError('private credential error')
    monkeypatch.setattr(store, 'helper', helper)
    data = store.workbench('coding')
    assert data['leetcode_history']['total_solved'] == 9
    assert data['leetcode_refresh']['status'] == 'error'
    assert 'private credential' not in json.dumps(data)


def test_character_coding_chat_uses_actual_unreported_accepted_source(store, monkeypatch):
    path = store.home / 'data/interview/leetcode_history.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'version': 1, 'accepted_solutions': [{
        'title': 'Move Zeroes', 'slug': 'move-zeroes', 'language': 'Python3',
        'accepted_at': '2026-10-03T00:00:00+00:00', 'code': 'def moveZeroes(nums): pass',
    }]}))
    calls=[]
    def agent_api(method, path, payload=None, **kwargs):
        if method == 'GET':
            return {'_status': 404}
        calls.append(payload)
        return {'message': {'content': '제출한 코드입니다.'}}
    monkeypatch.setattr(store, 'agent_api', agent_api)
    monkeypatch.setattr(store, 'telegram_send', lambda *_args: pytest.fail('Web chat sent Telegram'))
    store.office_chat({'room': 'coding', 'message': 'Move Zeroes 내 코드 설명해 줘'})
    assert 'def moveZeroes' in calls[-1]['instructions']
    assert store.coach_state()['coding'] == []


def test_background_source_refresh_runs_once_and_releases_lock(store, monkeypatch):
    root = store.home / 'data/interview'
    root.mkdir(parents=True)
    (root / 'leetcode_session.json').write_text(json.dumps({'username': 'david', 'session': 'private'}))
    calls = []
    class ImmediateThread:
        def __init__(self, target, **_kwargs): self.target = target
        def start(self): self.target()
    monkeypatch.setattr(observatory_module.threading, 'Thread', ImmediateThread)
    monkeypatch.setattr(store, 'helper', lambda name, args, **kwargs: calls.append((name, args, kwargs)))
    store.refresh_leetcode_sources()
    store.refresh_leetcode_sources()
    assert calls == [('leetcode_sync.py', ['sync', '--missing-only'], {'timeout': 180}),
                     ('leetcode_review.py', ['prepare', '--limit', '3'], {'timeout': 780})]
    assert not store.leetcode_source_lock.locked()


def test_office_stream_forwards_text_without_tool_arguments(store, monkeypatch):
    import io
    class Response(io.BytesIO):
        headers = {'Content-Type': 'text/event-stream'}
    frames = [('tool.started', {'args': {'secret': 'PRIVATE TOOL'}}),
              ('assistant.delta', {'delta': '먼저 '}),
              ('assistant.delta', {'delta': '힌트입니다.'}),
              ('assistant.completed', {'content': '먼저 힌트입니다.', 'partial': False}),
              ('done', {})]
    raw = ''.join('event: '+name+'\ndata: '+json.dumps(data)+'\n\n' for name, data in frames)
    store.agent_api_key = 'unit-test-key'
    monkeypatch.setattr(observatory_module, 'urlopen', lambda *a, **k: Response(raw.encode()))
    monkeypatch.setattr(store, 'agent_api', lambda *a, **k: {})
    monkeypatch.setattr(store, 'telegram_send', lambda *a: pytest.fail('Unexpected delivery'))
    emitted = []
    result = store.office_chat({'room': 'english', 'message': '교정해 줘'}, emit=emitted.append)
    assert result['response'] == '먼저 힌트입니다.'
    assert [e['event'] for e in emitted] == ['started', 'delta', 'delta']
    assert 'PRIVATE TOOL' not in json.dumps(emitted)
    assert not store.office_locks['english'].locked()


@pytest.mark.parametrize('frame', ['event: done\ndata: {}\n\n',
    'event: error\ndata: {"message":"PRIVATE ERROR"}\n\n',
    'event: assistant.completed\ndata: {"content":"partial","partial":true}\n\n'])
def test_office_stream_incomplete_turn_fails_without_retry(store, monkeypatch, frame):
    import io
    class Response(io.BytesIO):
        headers = {'Content-Type': 'text/event-stream'}
    calls=[]
    def opened(*args, **kwargs):
        calls.append(True)
        return Response(frame.encode())
    store.agent_api_key = 'unit-test-key'
    monkeypatch.setattr(observatory_module, 'urlopen', opened)
    monkeypatch.setattr(store, 'agent_api', lambda *a, **k: {})
    with pytest.raises(OSError) as error:
        store.office_chat({'room': 'hq', 'message': 'hello'}, emit=lambda _: None)
    assert 'PRIVATE ERROR' not in str(error.value)
    assert len(calls) == 1
    assert not store.office_locks['hq'].locked()


def test_http_stream_delivers_delta_before_model_completion(store, monkeypatch):
    release = threading.Event()
    def chat(body, emit=None):
        emit({'event': 'started'})
        emit({'event': 'delta', 'text': '첫 출력'})
        assert release.wait(3)
        return {'saved': True, 'response': '첫 출력 완료'}
    monkeypatch.setattr(store, 'office_chat', chat)
    assets = Path(__file__).resolve().parents[1] / 'browser/observatory'
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(store, assets, {'127.0.0.1'}))
    worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
    conn = HTTPConnection(*server.server_address, timeout=3)
    host = '127.0.0.1:' + str(server.server_port)
    try:
        body = json.dumps({'room': 'coding', 'message': 'hint'})
        conn.request('POST', '/api/office-chat/stream', body, {'Origin': 'http://'+host,
            'Content-Type': 'application/json', 'X-Hermes-Action': '1'})
        response = conn.getresponse()
        assert response.status == 200
        assert 'text/event-stream' in response.getheader('Content-Type')
        assert json.loads(response.readline().decode()[6:])['event'] == 'started'
        assert response.readline() == b'\n'
        assert json.loads(response.readline().decode()[6:])['text'] == '첫 출력'
        assert not release.is_set()
        release.set()
        assert 'complete' in response.read().decode()
    finally:
        release.set(); conn.close(); server.shutdown(); server.server_close(); worker.join(2)


def test_coding_source_prioritizes_new_question_over_old_problem(store):
    path = store.home / 'data/interview/leetcode_history.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'accepted_solutions': [
        {'title': 'Two Sum', 'slug': 'two-sum', 'code': 'two_sum_source', 'accepted_at': '2026-09-01'},
        {'title': 'Top K Frequent Elements', 'slug': 'top-k-frequent-elements',
         'code': 'top_k_source', 'accepted_at': '2026-10-03'}]}))
    recent = [{'role': 'user', 'content': 'Top K Frequent Elements 내 코드 설명해줘'},
              {'role': 'assistant', 'content': 'Top K Frequent Elements 답변'}]
    assert 'two_sum_source' in store.coding_source_context('Two Sum 내 코드 설명해줘', recent=recent)
    assert 'top_k_source' not in store.coding_source_context('Two Sum 내 코드 설명해줘', recent=recent)
    assert 'top_k_source' not in store.coding_source_context('Move Zeroes 내 코드 설명해줘', recent=recent)
    assert 'top_k_source' in store.coding_source_context('같은 코드의 복잡도는?', recent=recent)


@pytest.fixture
def login_http(store):
    path = store.home / 'data/interview/leetcode-login-status.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'status': 'awaiting_login'}))
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(store, Path('/unused'), {'127.0.0.1'}))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, path
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def test_login_proxy_keeps_assets_on_loopback_and_excludes_client_credentials(login_http, monkeypatch):
    from http.server import BaseHTTPRequestHandler
    requests = []
    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            requests.append((self.path, dict(self.headers)))
            body = b'login asset'
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(observatory_module, 'LEETCODE_LOGIN_PORT', upstream.server_port)
    server, status_path = login_http
    conn = HTTPConnection(*server.server_address, timeout=3)
    try:
        conn.request('GET', '/leetcode-login/app/ui.js?sample=1', headers={'Cookie': 'PRIVATE', 'Authorization': 'PRIVATE'})
        response = conn.getresponse()
        assert response.status == 200 and response.read() == b'login asset'
        assert response.getheader('Cache-Control') == 'no-store'
        assert requests[0][0] == '/app/ui.js?sample=1'
        assert 'PRIVATE' not in str(requests)
        conn.request('GET', '/leetcode-login/../secret')
        response = conn.getresponse()
        assert response.status == 404
        response.read()
        conn.request('GET', '/leetcode-login/websockify', headers={'Upgrade': 'websocket', 'Origin': 'http://evil.example'})
        response = conn.getresponse()
        assert response.status == 403
        response.read()
        status_path.write_text(json.dumps({'status': 'connected'}))
        conn.request('GET', '/leetcode-login/vnc.html')
        response = conn.getresponse()
        assert response.status == 503
        response.read()
        assert len(requests) == 1
    finally:
        conn.close()
        upstream.shutdown()
        upstream.server_close()
        thread.join(timeout=3)


def test_login_websocket_preserves_coalesced_first_frame_and_bidirectional_bytes(login_http, monkeypatch):
    import socket
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    listener.settimeout(3)
    monkeypatch.setattr(observatory_module, 'LEETCODE_LOGIN_PORT', listener.getsockname()[1])
    server, _ = login_http
    headers_seen, received, errors = [], [], []
    first_frame = b'\x82\x0cRFB 003.008\n'
    client_frame = b'\x82\x80MASK'
    reply = b'\x82\x02OK'
    def backend():
        try:
            with listener.accept()[0] as peer:
                peer.settimeout(3)
                header = b''
                while b'\r\n\r\n' not in header:
                    header += peer.recv(4096)
                headers_seen.append(header)
                peer.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n' + first_frame)
                received.append(peer.recv(len(client_frame)))
                peer.sendall(reply)
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=backend, daemon=True)
    thread.start()
    try:
        with socket.create_connection(server.server_address, timeout=3) as client:
            host = '%s:%s' % server.server_address
            client.sendall(('GET /leetcode-login/websockify HTTP/1.1\r\nHost: ' + host + '\r\nOrigin: http://' + host + '\r\nUpgrade: websocket\r\nSec-WebSocket-Key: test-key\r\nSec-WebSocket-Version: 13\r\nCookie: PRIVATE\r\n\r\n').encode())
            data = b''
            while b'\r\n\r\n' not in data:
                data += client.recv(4096)
            assert data.startswith(b'HTTP/1.1 101 ')
            frame = data.split(b'\r\n\r\n', 1)[1]
            while len(frame) < len(first_frame):
                frame += client.recv(4096)
            assert frame == first_frame
            client.sendall(client_frame)
            data = b''
            while len(data) < len(reply):
                data += client.recv(4096)
            assert data == reply
        thread.join(timeout=3)
        assert not errors and received == [client_frame]
        assert b'GET /websockify HTTP/1.1' in headers_seen[0]
        assert b'Sec-WebSocket-Key: test-key' in headers_seen[0]
        assert b'PRIVATE' not in headers_seen[0]
    finally:
        listener.close()
        thread.join(timeout=3)
