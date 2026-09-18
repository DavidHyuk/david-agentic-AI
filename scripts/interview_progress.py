#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Select interview work and persist evidence-backed coding/design progress.

Standalone, standard-library CLI. Catalog defaults to the staged interview-prep
references; state defaults to $HERMES_HOME/data/interview/coach_state.json.
Coding plans are retry-safe daily assignments. System design is a gated weekly
interview with saved answers, follow-ups, rubric feedback, and delayed reference
solutions. Only explicit feedback advances either curriculum. CLI writes use a
lock and atomic replacement.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
import fcntl
import json
import os
import sys
from pathlib import Path
import tempfile

DIMENSIONS = ('requirements', 'architecture', 'trade_off', 'failure_mode')
TRACKS = ('coding', 'system_design')
DESIGN_CORE_DIMENSIONS = (
    'requirement_clarification', 'high_level_architecture', 'data_model',
    'api_design', 'scalability', 'reliability', 'failure_handling',
    'trade_off_reasoning', 'observability', 'communication',
)
DESIGN_TRACK_DIMENSIONS = {
    'general': (),
    'ml': ('ml_problem_formulation', 'data_strategy', 'model_choice',
           'evaluation', 'serving', 'monitoring'),
    'agent': ('agent_loop_design', 'tool_execution', 'context_management',
              'memory', 'retry_recovery', 'evaluation', 'safety_sandboxing',
              'cost_latency_awareness'),
}
DESIGN_TRACK_TARGETS = {'general': 0.40, 'ml': 0.25, 'agent': 0.35}
DESIGN_DIFFICULTIES = {
    1: 'Fundamentals', 2: 'Standard senior interview',
    3: 'Senior deep dive', 4: 'Staff-level trade-offs',
}


def empty_state() -> dict:
    return {'version': 1, 'coding': [], 'system_design': [], 'assignments': {}}


def normalize_state(state: dict) -> dict:
    """Preserve old evidence while retiring pre-interview design assignments."""
    for assignment in state['assignments'].values():
        if (assignment.get('track') == 'system_design'
                and not assignment.get('completed')
                and 'phase' not in assignment):
            assignment['superseded'] = True
            assignment['superseded_reason'] = 'replaced by adaptive interview workflow'
    return state


def load_state(path: Path) -> dict:
    if not path.exists():
        return empty_state()
    state = json.loads(path.read_text())
    if (not isinstance(state, dict) or state.get('version') != 1 or
            any(not isinstance(state.get(k), list) for k in TRACKS) or
            not isinstance(state.get('assignments'), dict)):
        raise ValueError('Unsupported or malformed coach state; preserve it for recovery.')
    return normalize_state(state)


def save_state(path: Path, state: dict) -> None:
    """Replace state atomically; malformed existing JSON is never silently reset."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(state, handle, indent=2, ensure_ascii=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def review_days(independent: bool, hint_level: int, confidence: int,
                solution_viewed: bool = False) -> int:
    if solution_viewed or confidence <= 2:
        return 2
    if hint_level >= 2 or confidence == 3:
        return 7
    if independent and confidence >= 4:
        return 21
    return 7


def latest_sessions(state: dict, track: str, today: str) -> dict:
    latest = {}
    for session in sorted(state[track], key=lambda s: s['date']):
        if session['date'] <= today:
            latest[session['item_id']] = session
    return latest


def weakness(session: dict, track: str) -> tuple:
    if track == 'coding':
        days = review_days(session['independent'], session['hint_level'],
                           session['confidence'], session['solution_viewed'])
        return days, session['confidence'], -session['hint_level']
    return min(session['confidence'], *(session[d + '_score'] for d in DIMENSIONS)), session['confidence']


def curriculum_cursor(state: dict, track: str, today: str) -> int:
    completed = {s['curriculum_slot'] for s in state[track]
                 if s['date'] <= today and s['curriculum_slot'] is not None}
    cursor = 0
    while cursor in completed:
        cursor += 1
    return cursor


def design_score_dimensions(track: str) -> tuple[str, ...]:
    if track not in DESIGN_TRACK_DIMENSIONS:
        raise ValueError(f'Unknown system-design track: {track}')
    return DESIGN_CORE_DIMENSIONS + DESIGN_TRACK_DIMENSIONS[track]


def design_difficulty(state: dict, today: str) -> int:
    """Advance only on repeated strong evidence; regress after a weak session."""
    completed = [row for row in state['system_design'] if row['date'] <= today]
    recent = sorted(completed, key=lambda row: row['date'])[-3:]
    if not recent:
        return 2
    levels = [int(row.get('difficulty_level', 2)) for row in recent]
    scores = [float(row.get('overall_score', 0)) for row in recent
              if row.get('overall_score') is not None]
    current = levels[-1]
    if scores and scores[-1] < 2.75:
        return max(1, current - 1)
    if len(scores) >= 2 and all(score >= 4.0 for score in scores[-2:]):
        return min(4, current + 1)
    return current


def recurring_design_weaknesses(state: dict, today: str) -> Counter:
    weaknesses = Counter()
    for row in state['system_design']:
        if row['date'] > today:
            continue
        for value in row.get('weaknesses', []):
            weaknesses[str(value).strip().lower()] += 1
        for value in row.get('recommended_review_topics', []):
            weaknesses[str(value).strip().lower()] += 1
        for name, score in row.get('scores', {}).items():
            if score <= 2:
                weaknesses[name.replace('_', ' ')] += 1
    return weaknesses


def design_progress(state: dict, catalog: dict, today: str) -> dict:
    completed = [row for row in state['system_design'] if row['date'] <= today]
    track_counts = Counter(row.get('design_track', 'general') for row in completed)
    score_totals = Counter()
    score_counts = Counter()
    for row in completed:
        for name, score in row.get('scores', {}).items():
            score_totals[name] += score
            score_counts[name] += 1
    averages = {name: round(score_totals[name] / score_counts[name], 2)
                for name in score_totals}
    recent_scores = [row.get('overall_score') for row in completed[-4:]
                     if row.get('overall_score') is not None]
    return {
        'sessions_completed': len(completed),
        'track_counts': dict(track_counts),
        'target_mix': DESIGN_TRACK_TARGETS,
        'current_difficulty_level': design_difficulty(state, today),
        'current_difficulty': DESIGN_DIFFICULTIES[design_difficulty(state, today)],
        'recent_average': (round(sum(recent_scores) / len(recent_scores), 2)
                           if recent_scores else None),
        'dimension_averages': averages,
        'recurring_weaknesses': recurring_design_weaknesses(state, today).most_common(8),
    }


def select_design_problem(state: dict, catalog: dict, today: str) -> dict:
    """Select deterministically from balance, weakness overlap, and demonstrated level."""
    items = catalog['system_design']
    completed = [row for row in state['system_design'] if row['date'] <= today]
    used = {row['item_id'] for row in completed}
    candidates = [item for item in items if item['id'] not in used]
    if not candidates:
        recent_ids = {row['item_id'] for row in completed[-3:]}
        candidates = [item for item in items if item['id'] not in recent_ids] or items
    difficulty = design_difficulty(state, today)
    same_level = [item for item in candidates if item['difficulty_level'] == difficulty]
    if same_level:
        candidates = same_level

    track_counts = Counter(row.get('design_track', 'general') for row in completed)
    next_total = len(completed) + 1
    weakness_counts = recurring_design_weaknesses(state, today)

    def rank(item: dict) -> tuple:
        track = item['track']
        balance_deficit = DESIGN_TRACK_TARGETS[track] * next_total - track_counts[track]
        topic_match = sum(weakness_counts.get(topic.lower(), 0)
                          for topic in item.get('topics', []))
        # Prefer a different scenario sharing a weak concept, then restore mix.
        return (topic_match, round(balance_deficit, 4), -item['recommended_order'])

    return max(candidates, key=rank)


def active_design_assignment(state: dict, today: str) -> dict | None:
    active = [assignment for assignment in state['assignments'].values()
              if assignment.get('track') == 'system_design'
              and assignment['date'] <= today
              and not assignment.get('completed')
              and not assignment.get('superseded')
              and assignment.get('session_type') == 'new']
    return sorted(active, key=lambda assignment: (assignment['date'], assignment['id']))[-1] if active else None


def plan_design(state: dict, catalog: dict, today: str) -> dict:
    """Return the sole active weekly interview, never opening a second one."""
    date.fromisoformat(today)
    active = active_design_assignment(state, today)
    if active:
        return active
    week = date.fromisoformat(today).isocalendar()[:2]
    same_week = [assignment for assignment in state['assignments'].values()
                 if assignment.get('track') == 'system_design'
                 and date.fromisoformat(assignment['date']).isocalendar()[:2] == week
                 and not assignment.get('superseded')
                 and assignment.get('session_type') == 'new']
    if same_week:
        return sorted(same_week, key=lambda assignment: assignment['id'])[-1]
    item = select_design_problem(state, catalog, today)
    assignment_id = f'system_design:{today}'
    sequence = 2
    while assignment_id in state['assignments']:
        assignment_id = f'system_design:{today}:{sequence}'
        sequence += 1
    assignment = {
        'id': assignment_id, 'track': 'system_design', 'date': today,
        'completed': False, 'superseded': False, 'item_id': item['id'],
        'reason': 'adaptive weekly selection', 'curriculum_slot': None,
        'session_type': 'new', 'design_track': item['track'],
        'difficulty_level': item['difficulty_level'],
        'topics': item['topics'], 'phase': 'problem', 'answer': '',
        'followups': [], 'feedback': None, 'solution_viewed': False,
    }
    state['assignments'][assignment_id] = assignment
    return assignment


def _design_assignment(state: dict, assignment_id: str) -> dict:
    assignment = state['assignments'].get(assignment_id)
    if not assignment or assignment.get('track') != 'system_design':
        raise ValueError('Unknown system-design assignment.')
    return assignment


def record_design_answer(state: dict, assignment_id: str, answer: str) -> dict:
    assignment = _design_assignment(state, assignment_id)
    if assignment.get('completed'):
        raise ValueError('This interview already has feedback.')
    answer = answer.strip()
    if not answer:
        raise ValueError('Answer must not be empty.')
    if assignment.get('answer') and assignment['answer'] != answer:
        raise ValueError('An answer is already saved; append through a follow-up instead.')
    assignment['answer'] = answer
    assignment['phase'] = 'followup'
    return assignment


def record_design_followup(state: dict, assignment_id: str, question: str,
                           answer: str = '') -> dict:
    assignment = _design_assignment(state, assignment_id)
    if not assignment.get('answer'):
        raise ValueError('Save the proposed design before interviewer follow-ups.')
    if assignment.get('completed'):
        raise ValueError('This interview already has feedback.')
    question = question.strip()
    answer = answer.strip()
    if not question:
        raise ValueError('Follow-up question must not be empty.')
    row = {'question': question, 'answer': answer}
    if (assignment['followups'] and assignment['followups'][-1]['question'] == question
            and not assignment['followups'][-1]['answer']):
        assignment['followups'][-1]['answer'] = answer
    elif not assignment['followups'] or assignment['followups'][-1] != row:
        assignment['followups'].append(row)
    return assignment


def record_design_evaluation(state: dict, catalog: dict, assignment_id: str,
                             today: str, duration: int, evaluation: dict) -> dict:
    assignment = _design_assignment(state, assignment_id)
    date.fromisoformat(today)
    if today < assignment['date']:
        raise ValueError('Completion cannot precede the assignment date.')
    if not assignment.get('answer'):
        raise ValueError('Feedback requires a saved proposed design.')
    if not any(row.get('answer') for row in assignment.get('followups', [])):
        raise ValueError('Feedback requires at least one answered interviewer follow-up.')
    _integer(duration, 'duration in minutes', 1, 180)
    item = next(item for item in catalog['system_design']
                if item['id'] == assignment['item_id'])
    expected = design_score_dimensions(item['track'])
    scores = evaluation.get('scores')
    if not isinstance(scores, dict) or set(scores) != set(expected):
        raise ValueError('Evaluation scores must contain exactly the rubric dimensions for this track.')
    for name in expected:
        _integer(scores[name], name + ' score', 1, 5)
    for key in ('strengths', 'weaknesses', 'mistakes', 'recommended_review_topics'):
        values = evaluation.get(key)
        if not isinstance(values, list) or not all(isinstance(value, str) and value.strip()
                                                   for value in values):
            raise ValueError(f'{key} must be a list of non-empty strings.')
    top = evaluation.get('top_3_improvements')
    if not isinstance(top, list) or len(top) != 3 or not all(
            isinstance(value, str) and value.strip() for value in top):
        raise ValueError('top_3_improvements must contain exactly three items.')
    strongest = evaluation.get('strongest_area')
    weakest = evaluation.get('weakest_area')
    if strongest not in expected or weakest not in expected:
        raise ValueError('strongest_area and weakest_area must name scored rubric dimensions.')
    overall = round(sum(scores.values()) / len(scores), 2)
    row = {
        'id': assignment_id, 'date': today, 'item_id': item['id'],
        'topic': item['name'], 'design_track': item['track'],
        'difficulty_level': assignment['difficulty_level'],
        'difficulty': DESIGN_DIFFICULTIES[assignment['difficulty_level']],
        'topics': item['topics'], 'duration': duration,
        'answer': assignment['answer'], 'followups': assignment['followups'],
        'scores': scores, 'overall_score': overall,
        'strongest_area': strongest, 'weakest_area': weakest,
        'strengths': evaluation['strengths'], 'weaknesses': evaluation['weaknesses'],
        'mistakes': evaluation['mistakes'],
        'top_3_improvements': top,
        'recommended_review_topics': evaluation['recommended_review_topics'],
        'session_type': 'new', 'curriculum_slot': None,
    }
    minimum = min(scores.values())
    interval = 2 if minimum <= 2 else 7 if minimum == 3 else 21
    row['next_review_date'] = (date.fromisoformat(today) + timedelta(days=interval)).isoformat()
    existing = next((current for current in state['system_design']
                     if current['id'] == assignment_id), None)
    if existing:
        if existing != row:
            raise ValueError('This assignment is already logged with different feedback.')
        return existing
    state['system_design'].append(row)
    assignment['feedback'] = evaluation
    assignment['overall_score'] = overall
    assignment['phase'] = 'feedback'
    assignment['completed'] = True
    return row


def reveal_design_solution(state: dict, catalog: dict, assignment_id: str) -> dict:
    assignment = _design_assignment(state, assignment_id)
    if not assignment.get('completed') or not assignment.get('feedback'):
        raise ValueError('Reference solution unlocks only after feedback is saved.')
    item = next(item for item in catalog['system_design']
                if item['id'] == assignment['item_id'])
    assignment['solution_viewed'] = True
    assignment['phase'] = 'solution'
    return {'assignment': assignment_id, 'problem': item['name'],
            'reference_solution': item['reference_solution']}


def design_review_exercise(state: dict, today: str) -> dict:
    weaknesses = recurring_design_weaknesses(state, today)
    focus = weaknesses.most_common(1)[0][0] if weaknesses else 'trade-off reasoning'
    return {
        'focus': focus,
        'exercise': (f'In 10 minutes, revisit {focus}. State one concrete design choice, '
                     'one rejected alternative, one failure scenario, and one observable signal.'),
        'counts_as_weekly_problem': False,
    }


def select_item(state: dict, catalog: dict, track: str, today: str,
                prefer_new: bool = False) -> dict:
    """Choose a scheduled item, or the next unseen curriculum item on request."""
    if track == 'system_design':
        item = select_design_problem(state, catalog, today)
        return {'item_id': item['id'], 'reason': 'adaptive weekly selection',
                'curriculum_slot': None, 'session_type': 'new'}
    latest = latest_sessions(state, track, today)
    items = catalog['problems' if track == 'coding' else 'system_design']
    by_id = {p['id']: p for p in items}
    cursor = curriculum_cursor(state, track, today)
    curriculum = catalog['coding_curriculum'] if track == 'coding' else [
        {'problem': p['id']} for p in items]
    slot = curriculum[cursor] if cursor < len(curriculum) else None
    if prefer_new:
        completed_slots = {s['curriculum_slot'] for s in state[track]
                           if s['date'] <= today and s['curriculum_slot'] is not None}
        next_new = next(((index, candidate) for index, candidate in enumerate(curriculum)
                         if candidate.get('problem') and index not in completed_slots), None)
        if next_new:
            slot_index, candidate = next_new
            item_id = candidate['problem']
            missing = [p for p in by_id[item_id]['prerequisites'] if p not in latest]
            if missing:
                item_id, reason, slot_index = missing[0], 'prerequisite practice', None
            else:
                reason = 'next new curriculum item'
            return {'item_id': item_id, 'reason': reason, 'curriculum_slot': slot_index,
                    'session_type': 'review' if item_id in latest else 'new'}
    ranked = sorted(latest.values(), key=lambda s: (
        weakness(s, track), s['next_review_date'], by_id[s['item_id']].get('recommended_order', 0)))
    due = [s for s in ranked if s['next_review_date'] <= today]
    weak_due = [s for s in due if weakness(s, track)[0] <= (7 if track == 'coding' else 3)]
    # Strong reviews wait for reserved/consolidation slots so the seed curriculum
    # stays reachable. Only weak due reviews interrupt a new lesson.
    priority = weak_due or (due if not slot or slot.get('review') else [])
    if priority:
        item_id, reason = priority[0]['item_id'], 'due review'
        slot_index = cursor if slot and slot.get('review') else None
        # The week-three optional Min Stack slot can be a due weak review.
        if (slot and slot.get('problem') == 'min-stack' and
                weakness(priority[0], track)[0] <= 7):
            slot_index = cursor
    elif slot and slot.get('review'):
        item_id, reason, slot_index = ranked[0]['item_id'], 'curriculum weak review', cursor
    elif slot:
        item_id, reason, slot_index = slot['problem'], 'new curriculum item', cursor
        missing = [p for p in by_id[item_id]['prerequisites'] if p not in latest]
        if missing:
            item_id, reason, slot_index = missing[0], 'prerequisite practice', None
    else:
        # After the seed curriculum, keep sending concrete consolidation exercises.
        item_id, reason, slot_index = ranked[0]['item_id'], 'consolidation review', None
    return {'item_id': item_id, 'reason': reason, 'curriculum_slot': slot_index,
            'session_type': 'review' if item_id in latest else 'new'}


def select_review_item(state: dict, catalog: dict, track: str, today: str) -> dict:
    """Return the highest-value prior exercise for an explicit review request."""
    latest = latest_sessions(state, track, today)
    if not latest:
        raise ValueError('Complete one problem before requesting a review.')
    items = catalog['problems' if track == 'coding' else 'system_design']
    by_id = {item['id']: item for item in items}
    ranked = sorted(latest.values(), key=lambda session: (
        session['next_review_date'] > today, weakness(session, track),
        session['next_review_date'], by_id[session['item_id']].get('recommended_order', 0)))
    return {'item_id': ranked[0]['item_id'], 'reason': 'requested review',
            'curriculum_slot': None, 'session_type': 'review'}


def plan(state: dict, catalog: dict, track: str, today: str,
         next_assignment: bool = False, review_assignment: bool = False) -> dict:
    """Return the daily assignment or an explicit new/review follow-up.

    Normal scheduled planning stays idempotent for the whole day.  An explicit
    new-problem request never replaces itself with an old review; an explicit
    review request is the only follow-up path that selects a completed problem.
    """
    if next_assignment and review_assignment:
        raise ValueError('Choose either a new problem or a review, not both.')
    if track == 'system_design' and not review_assignment:
        return plan_design(state, catalog, today)
    date.fromisoformat(today)
    daily_id = f'{track}:{today}'
    if not next_assignment and not review_assignment and daily_id in state['assignments']:
        return state['assignments'][daily_id]
    track_assignments = [assignment for assignment in state['assignments'].values()
                         if assignment['track'] == track and assignment['date'] <= today]
    today_assignments = [assignment for assignment in track_assignments
                         if assignment['date'] == today]
    if next_assignment or review_assignment:
        unfinished = [assignment for assignment in track_assignments
                      if not assignment['completed'] and
                      not assignment.get('superseded') and
                      (assignment.get('session_type') == 'review') == review_assignment]
        if unfinished:
            if not next_assignment:
                return unfinished[-1]
            expected = select_item(state, catalog, track, today, prefer_new=True)
            matching = [assignment for assignment in unfinished
                        if assignment['item_id'] == expected['item_id']]
            if matching:
                return matching[-1]
            # A versioned curriculum change may make an open assignment
            # jump ahead of the active pattern block. Preserve it for history,
            # but remove it from the active workbench instead of calling it done.
            for current in unfinished:
                current['superseded'] = True
    assignment_id = daily_id
    sequence = 2
    while assignment_id in state['assignments']:
        assignment_id = f'{daily_id}:{sequence}'
        sequence += 1
    selection = (select_review_item(state, catalog, track, today) if review_assignment
                 else select_item(state, catalog, track, today, prefer_new=next_assignment))
    if track == 'coding' and selection['curriculum_slot'] is not None:
        slot = catalog['coding_curriculum'][selection['curriculum_slot']]
        selection.update(pattern_block=slot['pattern_block'],
                         block_index=slot['block_index'], block_size=slot['block_size'])
    # Preserve hint/solution exposure if an unfinished exercise is pushed again.
    previous = [a for a in state['assignments'].values()
                if a['track'] == track and a['item_id'] == selection['item_id']
                and a['date'] <= today and not a['completed']]
    assignment = dict(id=assignment_id, track=track, date=today, completed=False,
                      hint_level=max((a['hint_level'] for a in previous), default=0),
                      solution_viewed=any(a['solution_viewed'] for a in previous),
                      **selection)
    state['assignments'][assignment_id] = assignment
    return assignment


def render_message(assignment: dict, catalog: dict) -> str:
    if assignment['track'] == 'coding':
        item = next(p for p in catalog['problems'] if p['id'] == assignment['item_id'])
        block = (f"Pattern block: {assignment['pattern_block']} · "
                 f"{assignment['block_index']}/{assignment['block_size']}\n"
                 if assignment.get('pattern_block') else '')
        return (f"💻 Coding Interview — 35 min\n{block}Pattern: {item['pattern']}\n"
                f"Today: {item['name']} ({assignment['session_type']})\n\n"
                f"🎯 Goal\n{item['goal']}\n\nNeetCode:\n{item['neetcode_url']}\n\n"
                f"LeetCode:\n{item['leetcode_url']}\n\n"
                "Rule: Try for 20 minutes without AI first.\nIf stuck, ask me for a hint.\n"
                "Use the remaining 15 minutes to test edge cases and explain time/space complexity.\n"
                "Open the problem statement first; leave editorials and videos closed.\n\n"
                "Afterward, reply with minutes, solved independently yes/no, highest hint 0–3, "
                "solution viewed yes/no, confidence 1–5, and one lesson/mistake.")
    item = next(p for p in catalog['system_design'] if p['id'] == assignment['item_id'])
    if assignment.get('completed'):
        return (f"✅ This week's system-design interview is complete: {item['name']}.\n"
                "Use /review for a short weakness drill or /progress for the current summary. "
                "A new interview opens next week.")
    questions = '\n'.join(f'{index}. {question}' for index, question in
                          enumerate(item['clarification_questions'], 1))
    return (f"🏗 Weekly System Design Interview — 45 min\n"
            f"Today: {item['name']}\n"
            f"Track: {item['track']} · Difficulty: "
            f"{DESIGN_DIFFICULTIES[assignment['difficulty_level']]}\n\n"
            f"Problem\n{item['prompt']}\n\n"
            "Clarification questions an interviewer expects you to consider\n"
            f"{questions}\n\n"
            "Do not look for a solution yet. Ask your clarification questions, then submit "
            "your proposed design with /answer. I will interview you before giving feedback.")


def record_hint(state: dict, assignment_id: str, solution: bool = False) -> dict:
    assignment = state['assignments'][assignment_id]
    if assignment['track'] != 'coding' or assignment['completed']:
        raise ValueError('Hints require an unfinished coding assignment.')
    related = [a for a in state['assignments'].values()
               if a['track'] == 'coding' and a['item_id'] == assignment['item_id']
               and not a['completed']]
    highest = max(a['hint_level'] for a in related)
    if solution:
        if highest < 3:
            raise ValueError('Give hints 1, 2, and 3 before an explicitly requested solution.')
        for other in related:
            other['solution_viewed'] = True
    else:
        highest = min(3, highest + 1)
    for other in related:
        other['hint_level'] = highest
    return assignment


def _integer(value: int, name: str, lower: int, upper: int) -> None:
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f'{name} must be an integer from {lower} to {upper}.')


def record_session(state: dict, catalog: dict, assignment_id: str,
                   today: str, feedback: dict) -> dict:
    date.fromisoformat(today)
    assignment = state['assignments'][assignment_id]
    track = assignment['track']
    if today < assignment['date']:
        raise ValueError('Completion cannot precede the assignment date.')
    _integer(feedback['duration'], 'duration in minutes', 1, 1440)
    _integer(feedback['confidence'], 'confidence', 1, 5)
    row = dict(id=assignment_id, date=today, item_id=assignment['item_id'],
               curriculum_slot=assignment['curriculum_slot'], **feedback)
    if track == 'coding':
        _integer(feedback['hint_level'], 'hint level', 0, 3)
        if any(type(feedback[k]) is not bool for k in ('independent', 'solution_viewed')):
            raise ValueError('independent and solution_viewed must be booleans.')
        if not feedback['lesson'].strip():
            raise ValueError('Record one actual lesson/mistake.')
        related = [a for a in state['assignments'].values()
                   if a['track'] == track and a['item_id'] == assignment['item_id']
                   and a['date'] <= today and (not a['completed'] or a['id'] == assignment_id)]
        row['hint_level'] = max(feedback['hint_level'], *(a['hint_level'] for a in related))
        row['solution_viewed'] = feedback['solution_viewed'] or any(a['solution_viewed'] for a in related)
        row['independent'] = feedback['independent'] and row['hint_level'] == 0 and not row['solution_viewed']
        item = next(p for p in catalog['problems'] if p['id'] == row['item_id'])
        row.update(problem=item['name'], pattern=item['pattern'])
        interval = review_days(row['independent'], row['hint_level'], row['confidence'], row['solution_viewed'])
    else:
        for dimension in DIMENSIONS:
            _integer(feedback[dimension + '_score'], dimension + ' score', 1, 5)
        if not feedback['next_improvement'].strip():
            raise ValueError('Record one concrete next improvement.')
        item = next(p for p in catalog['system_design'] if p['id'] == row['item_id'])
        row['topic'] = item['name']
        row['design_track'] = item.get('track', 'general')
        row['difficulty_level'] = item.get('difficulty_level', 2)
        row['topics'] = item.get('topics', [])
        score = min(row[d + '_score'] for d in DIMENSIONS)
        interval = review_days(score >= 4, 0, min(score, row['confidence']))
    row['next_review_date'] = (date.fromisoformat(today) + timedelta(days=interval)).isoformat()
    prior = [s for s in state[track] if s['id'] != assignment_id]
    row['session_type'] = 'review' if any(s['item_id'] == row['item_id'] for s in prior) else 'new'
    existing = next((s for s in state[track] if s['id'] == assignment_id), None)
    if existing:
        # An assignment ID doubles as the completion idempotency key.
        row['session_type'] = existing['session_type']
        if row != existing:
            raise ValueError('This assignment is already logged with different feedback.')
        return existing
    if any(s['date'] > today for s in prior):
        raise ValueError('Log sessions chronologically; backdated feedback needs manual reconciliation.')
    if assignment['completed']:
        raise ValueError('This exercise was already completed through another daily assignment.')
    state[track].append(row)
    # Close earlier copies of the same unfinished exercise as well.
    for other in state['assignments'].values():
        if (other['track'] == track and other['item_id'] == row['item_id']
                and other['date'] <= today and not other['completed']):
            other['completed'] = True
            if track == 'coding':
                other['hint_level'] = row['hint_level']
                other['solution_viewed'] = row['solution_viewed']
    return row


def weekly_report(state: dict, catalog: dict, today: str) -> dict:
    end = date.fromisoformat(today)
    start = (end - timedelta(days=end.weekday())).isoformat()
    sessions = {track: [s for s in state[track] if start <= s['date'] <= today] for track in TRACKS}
    coding, design = sessions['coding'], sessions['system_design']
    latest = latest_sessions(state, 'coding', today)
    weak_patterns = Counter(s['pattern'] for s in latest.values() if weakness(s, 'coding')[0] <= 7)
    score_rows = [s.get('scores', {}) for s in design]
    score_names = sorted({name for scores in score_rows for name in scores})
    averages = {
        name: round(sum(scores[name] for scores in score_rows if name in scores)
                    / sum(name in scores for scores in score_rows), 2)
        for name in score_names
    }
    if design and not averages:
        averages = {d: round(sum(s[d + '_score'] for s in design) / len(design), 2)
                    for d in DIMENSIONS}
    weakest = [d for d in averages if averages[d] == min(averages.values())]
    next_coding = select_item(state, catalog, 'coding', today)
    next_design = select_item(state, catalog, 'system_design', today)
    coding_name = next(p['name'] for p in catalog['problems'] if p['id'] == next_coding['item_id'])
    design_name = next(p['name'] for p in catalog['system_design'] if p['id'] == next_design['item_id'])
    focus = [f"Coding: {', '.join(weak_patterns) or coding_name}.",
             f"System design: {', '.join(weakest) or design_name}."]
    return {'week_start': start, 'through': today, 'coding_sessions_completed': len(coding),
            'new_problems': sum(s['session_type'] == 'new' for s in coding),
            'review_problems': sum(s['session_type'] == 'review' for s in coding),
            'weak_patterns': dict(weak_patterns),
            'average_solving_minutes': round(sum(s['duration'] for s in coding) / len(coding), 1) if coding else None,
            'hint_usage': {str(level): sum(s['hint_level'] == level for s in coding) for level in range(4)},
            'solutions_viewed': sum(s['solution_viewed'] for s in coding),
            'system_design_topics_covered': list(dict.fromkeys(s['topic'] for s in design)),
            'design_dimension_averages': averages, 'weakest_design_dimensions': weakest,
            'design_progress': design_progress(state, catalog, today),
            'next_week_recommended_focus': focus}


def parse_args(argv=None) -> argparse.Namespace:
    home = Path(os.environ.get('HERMES_HOME', '~/.hermes')).expanduser()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=home / 'data/interview/coach_state.json')
    parser.add_argument('--catalog', type=Path, default=home / 'skills/career/interview-prep/references/coach_catalog.json')
    parser.add_argument('--date', default=date.today().isoformat(), help='Local date YYYY-MM-DD')
    sub = parser.add_subparsers(dest='command', required=True)
    select = sub.add_parser('plan')
    select.add_argument('track', choices=TRACKS)
    follow_up = select.add_mutually_exclusive_group()
    follow_up.add_argument('--next', action='store_true', dest='next_assignment',
                           help='open the next uncompleted curriculum problem')
    follow_up.add_argument('--review', action='store_true', dest='review_assignment',
                           help='open the highest-value completed problem for review')
    select.add_argument('--format', choices=('text', 'json'), default='text')
    for command in ('hint', 'solution'):
        assistance = sub.add_parser(command)
        assistance.add_argument('--assignment', required=True)
        if command == 'solution':
            assistance.add_argument('--explicit-request', required=True, action='store_true')
    for command in ('log-coding', 'log-design'):
        log = sub.add_parser(command)
        log.add_argument('--assignment', required=True)
        log.add_argument('--duration', required=True, type=int)
        log.add_argument('--confidence', required=True, type=int)
        if command == 'log-coding':
            log.add_argument('--independent', required=True, choices=('yes', 'no'))
            log.add_argument('--hint-level', required=True, type=int)
            log.add_argument('--solution-viewed', required=True, choices=('yes', 'no'))
            log.add_argument('--lesson', required=True)
        else:
            for dimension in DIMENSIONS:
                log.add_argument('--' + dimension.replace('_', '-') + '-score', required=True, type=int)
            log.add_argument('--next-improvement', required=True)
    answer = sub.add_parser('design-answer')
    answer.add_argument('--assignment', required=True)
    answer.add_argument('--answer', required=True)
    followup = sub.add_parser('design-followup')
    followup.add_argument('--assignment', required=True)
    followup.add_argument('--question', required=True)
    followup.add_argument('--answer', default='')
    evaluation = sub.add_parser('design-feedback')
    evaluation.add_argument('--assignment', required=True)
    evaluation.add_argument('--duration', required=True, type=int)
    evaluation.add_argument('--evaluation-json', required=True)
    solution = sub.add_parser('design-solution')
    solution.add_argument('--assignment', required=True)
    for command in ('design-history', 'design-weakness', 'design-progress', 'design-review'):
        sub.add_parser(command)
    sub.add_parser('weekly')
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        date.fromisoformat(args.date)
        catalog = json.loads(args.catalog.expanduser().read_text())
        path = args.state.expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = load_state(path)
            before = deepcopy(state)
            if args.command == 'plan':
                result = plan(state, catalog, args.track, args.date, args.next_assignment,
                              args.review_assignment)
                output = render_message(result, catalog) if args.format == 'text' else json.dumps(result, indent=2)
            elif args.command in ('hint', 'solution'):
                result = record_hint(state, args.assignment, args.command == 'solution')
                output = json.dumps(result, indent=2)
            elif args.command.startswith('log-'):
                expected = 'coding' if args.command == 'log-coding' else 'system_design'
                if state['assignments'][args.assignment]['track'] != expected:
                    raise ValueError('Assignment does not match the requested track.')
                feedback = {k: v for k, v in vars(args).items() if k in (
                    'duration', 'confidence', 'independent', 'hint_level', 'solution_viewed',
                    'lesson', 'next_improvement', *(d + '_score' for d in DIMENSIONS))}
                for key in ('independent', 'solution_viewed'):
                    if key in feedback:
                        feedback[key] = feedback[key] == 'yes'
                result = record_session(state, catalog, args.assignment, args.date, feedback)
                output = json.dumps(result, indent=2, ensure_ascii=False)
            elif args.command == 'design-answer':
                result = record_design_answer(state, args.assignment, args.answer)
                output = json.dumps(result, indent=2, ensure_ascii=False)
            elif args.command == 'design-followup':
                result = record_design_followup(
                    state, args.assignment, args.question, args.answer)
                output = json.dumps(result, indent=2, ensure_ascii=False)
            elif args.command == 'design-feedback':
                evaluation = json.loads(args.evaluation_json)
                result = record_design_evaluation(
                    state, catalog, args.assignment, args.date, args.duration, evaluation)
                output = json.dumps(result, indent=2, ensure_ascii=False)
            elif args.command == 'design-solution':
                result = reveal_design_solution(state, catalog, args.assignment)
                output = json.dumps(result, indent=2, ensure_ascii=False)
            elif args.command == 'design-history':
                output = json.dumps(state['system_design'], indent=2, ensure_ascii=False)
            elif args.command == 'design-weakness':
                output = json.dumps(recurring_design_weaknesses(state, args.date).most_common(),
                                    indent=2, ensure_ascii=False)
            elif args.command == 'design-progress':
                output = json.dumps(design_progress(state, catalog, args.date),
                                    indent=2, ensure_ascii=False)
            elif args.command == 'design-review':
                output = json.dumps(design_review_exercise(state, args.date),
                                    indent=2, ensure_ascii=False)
            else:
                output = json.dumps(weekly_report(state, catalog, args.date), indent=2, ensure_ascii=False)
            if state != before:
                save_state(path, state)
        print(output)
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'Interview coach error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
