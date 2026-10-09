# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Render topic/skip controls and HQ connection notices with real workbench JS."""
import json
from pathlib import Path
import subprocess


def render(function, data):
    source = Path(__file__).resolve().parents[1] / 'browser/observatory/workbench.js'
    script = '''const fs=require('fs'), vm=require('vm');
const data=JSON.parse(fs.readFileSync(0,'utf8'));
const context={$:()=>({}),window:{},setInterval:()=>0,
esc:value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),context);
process.stdout.write(context[process.argv[2]](data));'''
    return subprocess.run(['node', '-e', script, str(source), function], input=json.dumps(data),
                          capture_output=True, text=True, check=True, timeout=10).stdout


def test_topic_lists_show_difficulty_progress_and_saved_problem_actions():
    data = {'pending': [{'id': 'coding:first'}], 'coding_navigation': {
        'selected_topic': 'Two Pointers', 'previous_topic': 'HashMap',
        'topics': [{'name': 'Two Pointers', 'completed_count': 1, 'problems': [
            {'item_id': 'valid-palindrome', 'name': 'Valid Palindrome', 'difficulty': 'Easy', 'status': 'completed'},
            {'item_id': 'trapping-rain-water', 'name': 'Trapping Rain Water <img>', 'difficulty': 'Hard',
             'status': 'skipped', 'assignment': 'coding:first"onclick="bad'},
            {'item_id': 'move-zeroes', 'name': 'Move Zeroes', 'difficulty': 'Easy',
             'status': 'paused', 'assignment': 'coding:second'}]}],
        'skip_history': [{'assignment': 'coding:first', 'item_id': 'trapping-rain-water',
                          'name': 'Trapping Rain Water', 'difficulty': 'Hard', 'topic': 'Two Pointers',
                          'skip_dates': ['2026-10-08', '2026-10-09'], 'status': 'skipped'}]}}
    html = render('codingNavigationCard', data)
    assert '1 / 3 완료' in html and 'Hard · 스킵' in html
    assert 'data-coding-topic="HashMap"' in html
    assert 'data-coding-resume="coding:second"' in html
    assert '스킵 기록 · 1문제' in html and '최근 스킵 2026-10-09 · 2회' in html
    assert '&lt;img&gt;' in html and '<img>' not in html
    assert '"onclick=' not in html


def test_completed_skip_history_retains_record_without_resume_button():
    html = render('codingNavigationCard', {'coding_navigation': {
        'topics': [{'name': 'HashMap', 'completed_count': 1, 'problems': []}],
        'skip_history': [{'assignment': 'coding:old', 'name': 'Contains Duplicate',
                          'skip_dates': ['2026-10-09'], 'status': 'completed'}]}})
    assert 'Contains Duplicate' in html and '완료' in html
    assert 'data-coding-resume' not in html


def test_mission_shows_skip_only_for_new_problem_and_keeps_topic_controls():
    item = {'name': 'Hard Problem', 'goal': 'Try it', 'pattern': 'Two Pointers'}
    assignment = {'id': 'coding:first', 'date': '2026-10-09', 'session_type': 'new', 'item': item}
    data = {'room': 'coding', 'track': 'coding', 'pending': [assignment], 'completed': [],
            'coding_reviews': {'items': [], 'ready_count': 0}, 'coding_navigation': {
                'topics': [{'name': 'Two Pointers', 'completed_count': 0, 'problems': []}]}}
    assert '잠시 스킵 · 다음 문제' in render('coachDesk', data)
    assignment['session_type'] = 'review'
    assert '잠시 스킵 · 다음 문제' not in render('coachDesk', data)
    assert '최신 문제로 돌아가기' in render('coachDesk', data)


def test_hq_connection_card_distinguishes_delivery_failure_and_unverified_recovery():
    html = render('connectionHealthCard', {'checked_at': '2026-10-09', 'last_delivery_ok': False,
        'pending_count': 1, 'services': [{'service': 'chatgpt_sync', 'status': 'failed', 'reason': 'sync_failed'},
            {'service': 'kakao', 'status': 'unknown', 'incident_open': True}],
        'events': [{'service': 'chatgpt_sync', 'kind': 'failed', 'time': '2026-10-09', 'reason': 'sync_failed'}]})
    assert '전송 대기 알림' in html and '다음 검사에서 다시 전송' in html
    assert '자료 갱신 실패' in html and '기존 장애 · 복구 미확인' in html
    assert 'Hermes Telegram 채팅룸' in html and '최근 장애·복구 기록 1건' in html
