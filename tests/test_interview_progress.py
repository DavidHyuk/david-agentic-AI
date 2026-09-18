# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Offline coach scheduling, evidence, hint gating, reporting, and staged CLI tests."""
from collections import Counter
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
    ordered_problems = sorted(catalog['problems'], key=lambda item: item['recommended_order'])
    for order, problem in enumerate(ordered_problems, 1):
        assert problem['id'] not in seen
        assert set(problem['prerequisites']) <= seen
        seen.add(problem['id'])
        assert problem['recommended_order'] == order
        assert problem['difficulty'] in ('Easy', 'Medium', 'Hard')
        assert problem['name'] and problem['pattern'] and problem['goal']
        assert isinstance(problem['leetcode_id'], int)
        for key, domain in [('neetcode_url', 'neetcode.io'), ('leetcode_url', 'leetcode.com')]:
            parsed = urlparse(problem[key])
            assert parsed.scheme == 'https' and parsed.netloc == domain
            assert parsed.path.startswith('/problems/') and not parsed.query
    assert len(catalog['coding_curriculum']) == 48
    blocks = {}
    for slot in catalog['coding_curriculum']:
        blocks.setdefault(slot['pattern_block'], []).append(slot)
    assert list(blocks) == ['HashMap', 'Two Pointers', 'Sliding Window', 'Stack',
                            'Binary Search', 'Tree / BFS / DFS', 'Heap', 'Graph']
    assert all(len(slots) == 6 for slots in blocks.values())
    assert all([slot['block_index'] for slot in slots] == list(range(1, 7))
               and all(slot['block_size'] == 6 for slot in slots)
               for slots in blocks.values())
    design = catalog['system_design']
    assert Counter(item['track'] for item in design) == {
        'general': 6, 'ml': 4, 'agent': 5,
    }
    assert [item['recommended_order'] for item in design] == list(range(1, 16))
    assert len({item['id'] for item in design}) == len(design)
    for item in design:
        assert item['track'] in ip.DESIGN_TRACK_TARGETS
        assert item['difficulty_level'] in ip.DESIGN_DIFFICULTIES
        assert item['target_minutes'] == 45
        assert 3 <= len(item['clarification_questions']) <= 5
        assert item['prompt'] and item['topics'] and item['hidden_constraints']
        assert item['reference_solution']
        assert 'reference_solution' not in item['prompt'].lower()


def test_plan_retries_and_missed_days_do_not_count_as_completion(catalog):
    state = ip.empty_state()
    first = deepcopy(ip.plan(state, catalog, 'coding', '2026-09-08'))
    assert first == ip.plan(state, catalog, 'coding', '2026-09-08')
    assert ip.plan(state, catalog, 'coding', '2026-10-08')['item_id'] == 'contains-duplicate'
    assert state['coding'] == []
    assert ip.weekly_report(state, catalog, '2026-10-11')['coding_sessions_completed'] == 0


def test_explicit_next_plan_tracks_a_second_same_day_problem(catalog):
    state = ip.empty_state()
    first = ip.plan(state, catalog, 'coding', '2026-09-08')
    ip.record_session(state, catalog, first['id'], '2026-09-08', feedback())

    second = ip.plan(state, catalog, 'coding', '2026-09-08', next_assignment=True)

    assert second['id'] == 'coding:2026-09-08:2'
    assert second['item_id'] == 'valid-anagram'
    assert not second['completed']
    assert ip.plan(state, catalog, 'coding', '2026-09-08', next_assignment=True) == second
    assert ip.plan(state, catalog, 'coding', '2026-09-08') == first


def test_curriculum_change_supersedes_open_problem_that_skips_active_block(catalog):
    state = ip.empty_state()
    for offset in range(4):
        complete(state, catalog, f'2026-09-{8 + offset:02d}')
    stale = ip.plan(state, catalog, 'coding', '2026-09-12', next_assignment=True)
    stale['item_id'] = 'valid-palindrome'

    replacement = ip.plan(state, catalog, 'coding', '2026-09-12', next_assignment=True)

    assert stale['superseded'] is True
    assert replacement['item_id'] == 'top-k-frequent-elements'
    assert replacement['pattern_block'] == 'HashMap'
    assert replacement['block_index'] == 5 and replacement['block_size'] == 6
    assert 'Pattern block: HashMap · 5/6' in ip.render_message(replacement, catalog)
    assert ip.plan(state, catalog, 'coding', '2026-09-13', next_assignment=True) == replacement


def test_explicit_next_plan_skips_due_review_for_next_unseen_problem(catalog):
    state = ip.empty_state()
    complete(state, catalog, '2026-09-08')
    complete(state, catalog, '2026-09-09')
    complete(state, catalog, '2026-09-10')
    # A weak earlier attempt is due, but asking for another problem is an
    # explicit request for a new curriculum item rather than a review slot.
    state['coding'][0].update(confidence=1, next_review_date='2026-09-10')

    next_assignment = ip.plan(state, catalog, 'coding', '2026-09-10', next_assignment=True)

    assert next_assignment['item_id'] == 'group-anagrams'
    assert next_assignment['reason'] == 'next new curriculum item'
    assert next_assignment['session_type'] == 'new'


def test_explicit_review_plan_returns_prior_problem_only_on_review_request(catalog):
    state = ip.empty_state()
    complete(state, catalog, '2026-09-08', confidence=2)

    review = ip.plan(state, catalog, 'coding', '2026-09-10', review_assignment=True)

    assert review['item_id'] == 'contains-duplicate'
    assert review['reason'] == 'requested review'
    assert review['session_type'] == 'review'
    with pytest.raises(ValueError, match='either a new problem or a review'):
        ip.plan(state, catalog, 'coding', '2026-09-10', next_assignment=True,
                review_assignment=True)


def test_new_and_review_requests_resume_only_their_own_assignment_type(catalog):
    state = ip.empty_state()
    first = complete(state, catalog, '2026-09-08', confidence=2)
    new_assignment = ip.plan(
        state, catalog, 'coding', '2026-09-10', next_assignment=True)
    review_assignment = ip.plan(
        state, catalog, 'coding', '2026-09-10', review_assignment=True)

    assert new_assignment['item_id'] == 'valid-anagram'
    assert new_assignment['session_type'] == 'new'
    assert review_assignment['item_id'] == first['item_id']
    assert review_assignment['session_type'] == 'review'
    assert ip.plan(
        state, catalog, 'coding', '2026-09-10', next_assignment=True
    ) == new_assignment
    assert ip.plan(
        state, catalog, 'coding', '2026-09-10', review_assignment=True
    ) == review_assignment


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
    assert ip.select_item(state, catalog, 'coding', '2026-10-20')['reason'] in {
        'due review', 'consolidation review'}


def test_scheduled_first_six_weeks_complete_three_pattern_blocks(catalog):
    state = ip.empty_state()
    start = date(2026, 9, 8)
    items = []
    for offset in range(42):
        day = start + timedelta(days=offset)
        if day.weekday() in (1, 3, 5):
            items.append(complete(state, catalog, day.isoformat())['item_id'])
    assert 'longest-substring-without-repeating-characters' in items
    assert ip.curriculum_cursor(state, 'coding', '2026-10-20') == 18
    assert items[-1] == 'sliding-window-maximum'


def test_due_weak_review_does_not_interrupt_explicit_pattern_block(catalog):
    state = ip.empty_state()
    for i in range(8):
        complete(state, catalog, f'2026-09-{i+1:02}')
    state['coding'][-1].update(confidence=2, next_review_date='2026-09-09')
    chosen = ip.plan(state, catalog, 'coding', '2026-09-09', next_assignment=True)
    assert chosen['item_id'] == '3sum'
    assert chosen['session_type'] == 'new'
    assert chosen['pattern_block'] == 'Two Pointers'
    assert chosen['block_index'] == 3


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
    assert ip.select_item(state, catalog, 'system_design', '2026-09-20')['item_id'] != row['item_id']
    report = ip.weekly_report(state, catalog, '2026-09-13')
    assert report['weakest_design_dimensions'] == ['failure_mode']
    assert report['system_design_topics_covered'] == [row['topic']]


def test_design_curriculum_balances_tracks_and_enforces_one_active_problem(catalog):
    state = ip.empty_state()
    first = ip.plan(state, catalog, 'system_design', '2026-09-06')
    assert first['item_id'] == 'notification-system'
    assert ip.plan(state, catalog, 'system_design', '2026-09-13') == first
    complete(state, catalog, '2026-09-06', 'system_design')
    second = ip.plan(state, catalog, 'system_design', '2026-09-13')
    complete(state, catalog, '2026-09-13', 'system_design')
    third = ip.plan(state, catalog, 'system_design', '2026-09-20')
    assert [first['design_track'], second['design_track'], third['design_track']] == [
        'general', 'agent', 'ml',
    ]


def design_evaluation(track='general', score=4):
    dimensions = ip.design_score_dimensions(track)
    return {
        'scores': {name: score for name in dimensions},
        'strongest_area': dimensions[0],
        'weakest_area': dimensions[-1],
        'strengths': ['Clear architecture'],
        'weaknesses': ['idempotency'],
        'mistakes': ['Did not quantify retry traffic'],
        'top_3_improvements': ['Quantify load', 'Trace one failure', 'Compare alternatives'],
        'recommended_review_topics': ['idempotency'],
    }


def test_design_interview_lifecycle_and_solution_gate(catalog):
    state = ip.empty_state()
    assignment = ip.plan(state, catalog, 'system_design', '2026-09-06')
    with pytest.raises(ValueError, match='only after feedback'):
        ip.reveal_design_solution(state, catalog, assignment['id'])
    ip.record_design_answer(state, assignment['id'], 'Use an API, queue, and workers.')
    ip.record_design_followup(state, assignment['id'], 'What if a provider times out?',
                              'Retry with an idempotency key.')
    row = ip.record_design_evaluation(
        state, catalog, assignment['id'], '2026-09-06', 45,
        design_evaluation('general'))
    assert row['overall_score'] == 4
    assert row['answer'].startswith('Use an API')
    assert row['followups'][0]['answer'].startswith('Retry')
    solution = ip.reveal_design_solution(state, catalog, assignment['id'])
    assert solution['reference_solution']
    assert state['assignments'][assignment['id']]['solution_viewed'] is True


def test_design_difficulty_changes_only_from_performance(catalog):
    state = ip.empty_state()
    for day in ('2026-09-06', '2026-09-13'):
        assignment = ip.plan(state, catalog, 'system_design', day)
        track = assignment['design_track']
        ip.record_design_answer(state, assignment['id'], 'A complete proposed design.')
        ip.record_design_followup(state, assignment['id'], 'Defend one trade-off.',
                                  'I prefer durability over lower write latency.')
        ip.record_design_evaluation(
            state, catalog, assignment['id'], day, 45,
            design_evaluation(track, score=4))
    assert ip.design_difficulty(state, '2026-09-20') == 3
    assert ip.plan(state, catalog, 'system_design', '2026-09-20')['difficulty_level'] == 3


def test_design_weakness_selects_a_different_scenario(catalog):
    state = ip.empty_state()
    assignment = ip.plan(state, catalog, 'system_design', '2026-09-06')
    ip.record_design_answer(state, assignment['id'], 'Queue notifications by channel.')
    ip.record_design_followup(state, assignment['id'], 'How do you retry?',
                              'Use an idempotency key.')
    ip.record_design_evaluation(
        state, catalog, assignment['id'], '2026-09-06', 45,
        design_evaluation('general'))

    next_assignment = ip.plan(state, catalog, 'system_design', '2026-09-13')

    assert next_assignment['item_id'] == 'distributed-task-queue'
    assert next_assignment['item_id'] != assignment['item_id']
    assert 'idempotency' in next_assignment['topics']


def test_loading_legacy_state_preserves_and_supersedes_open_design_work(tmp_path):
    path = tmp_path / 'coach_state.json'
    path.write_text(json.dumps({
        'version': 1, 'coding': [], 'system_design': [],
        'assignments': {
            'system_design:2026-09-13': {
                'id': 'system_design:2026-09-13', 'track': 'system_design',
                'date': '2026-09-13', 'completed': False,
                'item_id': 'delivery-framework', 'session_type': 'new',
            },
        },
    }))

    state = ip.load_state(path)

    legacy = state['assignments']['system_design:2026-09-13']
    assert legacy['superseded'] is True
    assert 'adaptive interview' in legacy['superseded_reason']


def test_telegram_messages_contain_actual_study_material(catalog):
    state = ip.empty_state()
    for track in ip.TRACKS:
        assignment = ip.plan(state, catalog, track, '2026-09-08')
        message = ip.render_message(assignment, catalog)
        assert len(message) < 4000
        assert 'Today:' in message
        if track == 'coding':
            assert 'https://' in message
            assert '35 min' in message and '20 minutes without AI first' in message
            assert 'Contains Duplicate' in message and 'LeetCode:' in message and 'NeetCode:' in message
            assert 'def ' not in message and 'pseudocode' not in message
        else:
            assert 'Clarification questions' in message and '/answer' in message
            assert 'Reference solution' not in message


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
