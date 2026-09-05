#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Select concrete interview lessons and persist evidence-backed progress.

Standalone, standard-library CLI. Catalog defaults to the staged interview-prep
references; state defaults to $HERMES_HOME/data/interview/coach_state.json.
Plans are retry-safe daily assignments, never completed sessions. Only explicit
feedback advances the curriculum. CLI writes use a lock and atomic replacement.
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


def empty_state() -> dict:
    return {'version': 1, 'coding': [], 'system_design': [], 'assignments': {}}


def load_state(path: Path) -> dict:
    if not path.exists():
        return empty_state()
    state = json.loads(path.read_text())
    if (not isinstance(state, dict) or state.get('version') != 1 or
            any(not isinstance(state.get(k), list) for k in TRACKS) or
            not isinstance(state.get('assignments'), dict)):
        raise ValueError('Unsupported or malformed coach state; preserve it for recovery.')
    return state


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


def select_item(state: dict, catalog: dict, track: str, today: str) -> dict:
    """Due weak items first; interrupted new slots resume after the review."""
    latest = latest_sessions(state, track, today)
    items = catalog['problems' if track == 'coding' else 'system_design']
    by_id = {p['id']: p for p in items}
    cursor = curriculum_cursor(state, track, today)
    curriculum = catalog['coding_curriculum'] if track == 'coding' else [
        {'problem': p['id']} for p in items]
    slot = curriculum[cursor] if cursor < len(curriculum) else None
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


def plan(state: dict, catalog: dict, track: str, today: str) -> dict:
    date.fromisoformat(today)
    assignment_id = f'{track}:{today}'
    if assignment_id in state['assignments']:
        return state['assignments'][assignment_id]
    selection = select_item(state, catalog, track, today)
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
        return (f"💻 Coding Interview — 35 min\nPattern: {item['pattern']}\n"
                f"Today: {item['name']} ({assignment['session_type']})\n\n"
                f"🎯 Goal\n{item['goal']}\n\nNeetCode:\n{item['neetcode_url']}\n\n"
                f"LeetCode:\n{item['leetcode_url']}\n\n"
                "Rule: Try for 20 minutes without AI first.\nIf stuck, ask me for a hint.\n"
                "Use the remaining 15 minutes to test edge cases and explain time/space complexity.\n"
                "Open the problem statement first; leave editorials and videos closed.\n\n"
                "Afterward, reply with minutes, solved independently yes/no, highest hint 0–3, "
                "solution viewed yes/no, confidence 1–5, and one lesson/mistake.")
    item = next(p for p in catalog['system_design'] if p['id'] == assignment['item_id'])
    focus = '\n'.join(f'- {point}' for point in item['focus'])
    message = (f"🏗 System Design — {item['target_minutes']} min\nToday: {item['name']}\n\n"
               f"Hello Interview:\n{item['url']}\n\nStudy task:\n{item['exercise']}\n\n"
               f"🎯 After studying, be able to explain:\n{focus}\n\n"
               f"Hermes connection: {item['hermes_connection']}\n\n"
               "Reply with minutes, requirements/architecture/trade-off/failure-mode scores "
               "(each 1–5), confidence (1–5), and one next improvement.")
    if item.get('access_note'):
        message += '\n\n' + item['access_note'] + '\n' + '\n'.join(item['supporting_urls'])
    return message


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
    averages = {d: round(sum(s[d + '_score'] for s in design) / len(design), 2)
                for d in DIMENSIONS} if design else {}
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
                result = plan(state, catalog, args.track, args.date)
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
