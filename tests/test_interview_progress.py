# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Offline coach scheduling, evidence, hint gating, reporting, and staged CLI tests."""
from copy import deepcopy
from datetime import date, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse

import pytest

import interview_progress as ip
import stage

REPO = Path(__file__).resolve().parent.parent
CATALOG = REPO / 'skills/career/interview-prep/references/coach_catalog.json'


@pytest.fixture
def catalog():
    return json.loads(CATALOG.read_text())


def feedback(**overrides):
    return dict(duration=30, independent=True, hint_level=0, confidence=5,
                solution_viewed=False, lesson='Check boundary cases') | overrides


def design_feedback(**overrides):
    return dict(duration=50, confidence=5, requirements_score=5, architecture_score=5,
                trade_off_score=5, failure_mode_score=5,
                next_improvement='Quantify peak traffic') | overrides


def complete(state, catalog, day, track='coding', **overrides):
    assignment = ip.plan(state, catalog, track, day)
    result = feedback(**overrides) if track == 'coding' else design_feedback(**overrides)
    return ip.record_session(state, catalog, assignment['id'], day, result)


@pytest.mark.parametrize('independent,hint,confidence,solution,days', [
    (True, 0, 5, True, 2), (False, 3, 1, False, 2), (True, 0, 2, False, 2),
    (False, 2, 4, False, 7), (False, 3, 5, False, 7), (True, 0, 3, False, 7),
    (True, 0, 4, False, 21), (True, 0, 5, False, 21), (False, 1, 4, False, 7),
])
def test_review_intervals(independent, hint, confidence, solution, days):
    assert ip.review_days(independent, hint, confidence, solution) == days


def test_catalog_is_ordered_and_links_are_problem_specific(catalog):
    seen = set()
    for order, problem in enumerate(catalog['problems'], 1):
        assert problem['id'] not in seen
        assert set(problem['prerequisites']) <= seen
        seen.add(problem['id'])
        assert problem['recommended_order'] == order
        assert problem['difficulty'] in ('Easy', 'Medium')
        assert problem['name'] and problem['pattern'] and problem['goal']
        assert isinstance(problem['leetcode_id'], int)
        for key, domain in [('neetcode_url', 'neetcode.io'), ('leetcode_url', 'leetcode.com')]:
            parsed = urlparse(problem[key])
            assert parsed.scheme == 'https' and parsed.netloc == domain
            assert parsed.path.startswith('/problems/') and not parsed.query
    assert len(catalog['coding_curriculum']) == 12
    assert [s.get('problem') for s in catalog['coding_curriculum']] == [
        'contains-duplicate', 'valid-anagram', 'two-sum', 'valid-palindrome',
        'two-sum-ii-input-array-is-sorted', None, 'valid-parentheses', 'binary-search',
        'min-stack', 'best-time-to-buy-and-sell-stock',
        'longest-substring-without-repeating-characters', None]
    for item in catalog['system_design']:
        assert urlparse(item['url']).netloc == 'www.hellointerview.com'
        assert 45 <= item['target_minutes'] <= 60
        assert 3 <= len(item['focus']) <= 5
        assert item['exercise'] and item['hermes_connection']


def test_plan_retries_and_missed_days_do_not_count_as_completion(catalog):
    state = ip.empty_state()
    first = deepcopy(ip.plan(state, catalog, 'coding', '2026-09-08'))
    assert first == ip.plan(state, catalog, 'coding', '2026-09-08')
    assert ip.plan(state, catalog, 'coding', '2026-10-08')['item_id'] == 'contains-duplicate'
    assert state['coding'] == []
    assert ip.weekly_report(state, catalog, '2026-10-11')['coding_sessions_completed'] == 0


def test_due_review_displaces_then_resumes_new_slot(catalog):
    state = ip.empty_state()
    first = complete(state, catalog, '2026-09-08', confidence=2)
    assert first['next_review_date'] == '2026-09-10'
    assert ip.select_item(state, catalog, 'coding', '2026-09-09')['item_id'] == 'valid-anagram'
    review = complete(state, catalog, '2026-09-10')
    assert review['item_id'] == 'contains-duplicate'
    assert review['session_type'] == 'review' and review['curriculum_slot'] is None
    assert ip.plan(state, catalog, 'coding', '2026-09-12')['item_id'] == 'valid-anagram'


def test_latest_strong_review_replaces_old_weak_outcome(catalog):
    state = ip.empty_state()
    complete(state, catalog, '2026-09-08', confidence=1, hint_level=3)
    old_assignment = deepcopy(state['assignments']['coding:2026-09-08'])
    complete(state, catalog, '2026-09-10')
    assert state['assignments']['coding:2026-09-08'] == old_assignment
    assert ip.weekly_report(state, catalog, '2026-09-13')['weak_patterns'] == {}
    assert ip.select_item(state, catalog, 'coding', '2026-09-12')['reason'] == 'new curriculum item'


def test_due_weak_items_beat_older_strong_due_items(catalog):
    state = ip.empty_state()
    complete(state, catalog, '2026-09-08')
    complete(state, catalog, '2026-09-10', confidence=1)
    assert ip.select_item(state, catalog, 'coding', '2026-10-01')['item_id'] == 'valid-anagram'


def test_seed_sequence_and_reserved_reviews(catalog):
    state = ip.empty_state()
    # Dense dates isolate curriculum ordering from the separately tested due intervals.
    for i, slot in enumerate(catalog['coding_curriculum']):
        day = (date(2026, 9, 1) + timedelta(days=i)).isoformat()
        row = complete(state, catalog, day)
        assert row['curriculum_slot'] == i
        if slot.get('review'):
            assert row['session_type'] == 'review'
        else:
            assert row['item_id'] == slot['problem']
    assert ip.select_item(state, catalog, 'coding', '2026-09-13')['reason'] == 'consolidation review'


def test_scheduled_first_four_weeks_keep_sliding_window_reachable(catalog):
    state = ip.empty_state()
    start = date(2026, 9, 8)
    items = []
    for offset in range(42):
        day = start + timedelta(days=offset)
        if day.weekday() in (1, 3, 5):
            items.append(complete(state, catalog, day.isoformat())['item_id'])
    assert 'longest-substring-without-repeating-characters' in items
    assert ip.curriculum_cursor(state, 'coding', '2026-10-20') == 12


def test_week_three_min_stack_can_be_replaced_by_due_weak_review(catalog):
    state = ip.empty_state()
    for i in range(8):
        complete(state, catalog, f'2026-09-{i+1:02}')
    state['coding'][-1].update(confidence=2, next_review_date='2026-09-09')
    chosen = ip.select_item(state, catalog, 'coding', '2026-09-09')
    assert chosen['item_id'] == 'binary-search' and chosen['curriculum_slot'] == 8


def test_prerequisite_recovery(catalog):
    state = ip.empty_state()
    complete(state, catalog, '2026-09-08')
    altered = deepcopy(catalog)
    altered['coding_curriculum'][1] = {'problem': 'min-stack'}
    chosen = ip.select_item(state, altered, 'coding', '2026-09-09')
    assert chosen['item_id'] == 'valid-parentheses'
    assert chosen['reason'] == 'prerequisite practice'
    assert chosen['curriculum_slot'] is None


def test_hint_ladder_survives_reissued_assignment_and_gates_solution(catalog):
    state = ip.empty_state()
    first = ip.plan(state, catalog, 'coding', '2026-09-08')
    with pytest.raises(ValueError, match='hints 1, 2, and 3'):
        ip.record_hint(state, first['id'], solution=True)
    assert ip.record_hint(state, first['id'])['hint_level'] == 1
    second = ip.plan(state, catalog, 'coding', '2026-09-10')
    assert second['hint_level'] == 1
    assert ip.record_hint(state, second['id'])['hint_level'] == 2
    assert ip.record_hint(state, first['id'])['hint_level'] == 3
    ip.record_hint(state, second['id'], solution=True)
    row = ip.record_session(state, catalog, first['id'], '2026-09-10', feedback())
    assert row['hint_level'] == 3 and row['solution_viewed'] and not row['independent']
    assert row['next_review_date'] == '2026-09-12'
    assert ip.record_session(state, catalog, first['id'], '2026-09-10', feedback()) == row
    with pytest.raises(ValueError, match='already completed'):
        ip.record_session(state, catalog, second['id'], '2026-09-10', feedback())


def test_feedback_retry_is_idempotent_and_conflicts_are_rejected(catalog):
    state = ip.empty_state()
    row = complete(state, catalog, '2026-09-08')
    assert ip.record_session(state, catalog, row['id'], row['date'], feedback()) == row
    assert len(state['coding']) == 1
    with pytest.raises(ValueError, match='different feedback'):
        ip.record_session(state, catalog, row['id'], row['date'], feedback(confidence=3))


@pytest.mark.parametrize('overrides', [
    {'duration': 0}, {'confidence': 6}, {'confidence': True}, {'hint_level': 4},
    {'lesson': ' '}, {'independent': 'yes'}, {'solution_viewed': 'no'},
])
def test_invalid_feedback_does_not_mutate_state(catalog, overrides):
    state = ip.empty_state()
    assignment = ip.plan(state, catalog, 'coding', '2026-09-08')
    before = deepcopy(state)
    with pytest.raises(ValueError):
        ip.record_session(state, catalog, assignment['id'], '2026-09-08', feedback(**overrides))
    assert state == before


def test_completion_before_assignment_is_rejected(catalog):
    state = ip.empty_state()
    assignment = ip.plan(state, catalog, 'coding', '2026-09-08')
    with pytest.raises(ValueError, match='precede'):
        ip.record_session(state, catalog, assignment['id'], '2026-09-07', feedback())


def test_design_progress_and_weak_dimension_review(catalog):
    state = ip.empty_state()
    row = complete(state, catalog, '2026-09-13', 'system_design', failure_mode_score=2)
    assert row['topic'] == catalog['system_design'][0]['name']
    assert row['next_review_date'] == '2026-09-15'
    assert ip.select_item(state, catalog, 'system_design', '2026-09-20')['item_id'] == 'delivery-framework'
    report = ip.weekly_report(state, catalog, '2026-09-13')
    assert report['weakest_design_dimensions'] == ['failure_mode']
    assert report['system_design_topics_covered'] == [row['topic']]


def test_design_curriculum_has_timed_notification_mock(catalog):
    state = ip.empty_state()
    for day, item in zip(('2026-09-06', '2026-09-13', '2026-09-20'), catalog['system_design']):
        assert complete(state, catalog, day, 'system_design')['item_id'] == item['id']
    # Strong review eligibility must not displace the week-four mock.
    chosen = ip.plan(state, catalog, 'system_design', '2026-09-27')
    assert chosen['item_id'] == 'notification-system'
    message = ip.render_message(chosen, catalog)
    assert '45-minute mock' in message and 'Premium' in message
    assert catalog['system_design'][-1]['url'] in message


def test_telegram_messages_contain_actual_study_material(catalog):
    state = ip.empty_state()
    for track in ip.TRACKS:
        assignment = ip.plan(state, catalog, track, '2026-09-08')
        message = ip.render_message(assignment, catalog)
        assert len(message) < 4000
        assert 'Today:' in message and 'https://' in message
        if track == 'coding':
            assert '35 min' in message and '20 minutes without AI first' in message
            assert 'Contains Duplicate' in message and 'LeetCode:' in message and 'NeetCode:' in message
            assert 'def ' not in message and 'pseudocode' not in message
        else:
            assert 'Hermes connection:' in message and 'After studying' in message


def test_weekly_report_uses_completed_sessions_and_monday_window(catalog):
    state = ip.empty_state()
    complete(state, catalog, '2026-09-06', confidence=2)
    complete(state, catalog, '2026-09-08', confidence=3, hint_level=2, duration=40)
    complete(state, catalog, '2026-09-10', duration=20)
    ip.plan(state, catalog, 'coding', '2026-09-12')
    report = ip.weekly_report(state, catalog, '2026-09-13')
    assert report['week_start'] == '2026-09-07'
    assert report['coding_sessions_completed'] == 2
    assert report['new_problems'] == 1 and report['review_problems'] == 1
    assert report['average_solving_minutes'] == 30
    assert report['hint_usage'] == {'0': 1, '1': 0, '2': 1, '3': 0}
    assert report['weak_patterns'] == {'Arrays & Hashing': 1}
    assert report['weakest_design_dimensions'] == []
    assert len(report['next_week_recommended_focus']) == 2


def test_weekly_report_empty_and_future_records(catalog):
    state = ip.empty_state()
    complete(state, catalog, '2026-09-15')
    report = ip.weekly_report(state, catalog, '2026-09-13')
    assert report['coding_sessions_completed'] == 0
    assert report['average_solving_minutes'] is None
    assert report['weak_patterns'] == {}


def test_state_roundtrip_and_corruption_is_not_overwritten(tmp_path, catalog):
    path = tmp_path / 'coach_state.json'
    state = ip.load_state(path)
    complete(state, catalog, '2026-09-08')
    ip.save_state(path, state)
    assert ip.load_state(path) == state
    path.write_text('{broken')
    assert ip.main(['--state', str(path), '--catalog', str(CATALOG), 'plan', 'coding']) == 1
    assert path.read_text() == '{broken'


def test_staged_cli_works_outside_repo_and_restage_preserves_progress(tmp_path):
    home = tmp_path / 'hermes'
    stage.stage_all(home)
    script = home / 'scripts/interview_progress.py'
    assert script.exists()
    assert (home / 'skills/career/interview-prep/references/coach_catalog.json').exists()
    env = {**os.environ, 'HERMES_HOME': str(home)}
    def run(*args):
        return subprocess.run([sys.executable, str(script), '--date', '2026-09-08', *args],
                              cwd=tmp_path, env=env, text=True, capture_output=True, check=True).stdout
    assignment = json.loads(run('plan', 'coding', '--format', 'json'))
    run('log-coding', '--assignment', assignment['id'], '--duration', '35',
        '--independent', 'yes', '--hint-level', '0', '--solution-viewed', 'no',
        '--confidence', '4', '--lesson', 'Test empty input')
    path = home / 'data/interview/coach_state.json'
    before = path.read_bytes()
    stage.stage_all(home)
    assert path.read_bytes() == before
    assert json.loads(run('weekly'))['coding_sessions_completed'] == 1
