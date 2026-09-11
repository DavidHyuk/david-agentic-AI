#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""A small Leitner spaced-repetition deck for English sentence corrections.

Purpose
-------
The ``english-practice`` skill extracts "you said X / better: Y" correction pairs
from David's tutor feedback and adds them here as flashcards. This module implements
a simple, dependency-free Leitner box scheduler so corrections resurface for review
on an expanding cadence until they stick — turning one-off corrections into a
durable practice routine.

Box -> interval (days): 1->1, 2->2, 3->4, 4->7, 5->15. A correct review promotes the
card one box (capped at 5); an incorrect review resets it to box 1.

Deck is a JSON file (default ``~/.hermes/data/english/srs_deck.json``).
"""
from __future__ import annotations

import argparse
import hashlib
import fcntl
import json
import os
from pathlib import Path
import tempfile
from datetime import date, datetime, timedelta
from typing import Sequence

DEFAULT_DECK_PATH = os.path.expanduser("~/.hermes/data/english/srs_deck.json")
BOX_INTERVALS = {1: 1, 2: 2, 3: 4, 4: 7, 5: 15}
MAX_BOX = 5


def _today(today: str | None = None) -> date:
    return date.fromisoformat(today) if today else date.today()


def make_card_id(wrong: str, correct: str) -> str:
    """Stable id from the correction pair so duplicates are de-duplicated."""
    raw = f"{wrong.strip().lower()}->{correct.strip().lower()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def load_deck(deck_path: str) -> dict:
    if os.path.exists(deck_path):
        try:
            with open(deck_path, encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            pass
    return {"cards": {}}


def save_deck(deck_path: str, deck: dict) -> None:
    path = Path(deck_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as fh:
        tmp = Path(fh.name)
        try:
            json.dump(deck, fh, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def add_card(
    deck: dict,
    wrong: str,
    correct: str,
    note: str = "",
    today: str | None = None,
) -> tuple[dict, bool]:
    """Add a correction card. Returns (deck, added) — added is False if duplicate."""
    cid = make_card_id(wrong, correct)
    if cid in deck.get("cards", {}):
        return deck, False
    deck.setdefault("cards", {})[cid] = {
        "id": cid,
        "wrong": wrong.strip(),
        "correct": correct.strip(),
        "note": note.strip(),
        "box": 1,
        "due": _today(today).isoformat(),
        "created": _today(today).isoformat(),
        "reviews": 0,
    }
    return deck, True


def due_cards(deck: dict, today: str | None = None) -> list[dict]:
    """Cards whose due date is on or before today, lowest box (weakest) first."""
    ref = _today(today)
    cards = [
        c
        for c in deck.get("cards", {}).values()
        if date.fromisoformat(c["due"]) <= ref
    ]
    return sorted(cards, key=lambda c: (c["box"], c["due"]))


def review_card(deck: dict, card_id: str, correct: bool, today: str | None = None) -> dict:
    """Apply a review result, moving the card between Leitner boxes."""
    card = deck["cards"][card_id]
    card["box"] = min(card["box"] + 1, MAX_BOX) if correct else 1
    outcome_key = "correct_reviews" if correct else "wrong_reviews"
    card[outcome_key] = card.get(outcome_key, 0) + 1
    interval = BOX_INTERVALS[card["box"]]
    card["due"] = (_today(today) + timedelta(days=interval)).isoformat()
    card["reviews"] = card.get("reviews", 0) + 1
    card["last_review"] = _today(today).isoformat()
    return deck


def weakness_cards(deck: dict, limit: int = 5) -> list[dict]:
    """Return the least-mastered cards, prioritizing repeated wrong reviews."""
    if limit < 1:
        return []
    cards = deck.get("cards", {}).values()
    return sorted(
        cards,
        key=lambda card: (
            card.get("box", 1),
            -card.get("wrong_reviews", 0),
            -card.get("reviews", 0),
            card.get("due", ""),
            card.get("created", ""),
        ),
    )[:limit]


def stats(deck: dict, today: str | None = None) -> dict:
    cards = deck.get("cards", {}).values()
    by_box = {b: 0 for b in BOX_INTERVALS}
    for c in cards:
        by_box[c["box"]] = by_box.get(c["box"], 0) + 1
    return {
        "total": len(cards),
        "due": len(due_cards(deck, today)),
        "by_box": by_box,
    }


def format_drill(cards: Sequence[dict]) -> str:
    """Render due cards as a quiz-style WhatsApp drill (prompts hide the answer)."""
    if not cards:
        return "*English drill*\n\n_Nothing due today — nice work staying on top of it._"
    lines = [f"*English drill* — {len(cards)} due", ""]
    for i, c in enumerate(cards, 1):
        lines.append(f"{i}. Rewrite correctly: _{c['wrong']}_")
    lines.append("")
    lines.append("*Answers*")
    for i, c in enumerate(cards, 1):
        extra = f" — {c['note']}" if c.get("note") else ""
        lines.append(f"{i}. {c['correct']}{extra}")
    return "\n".join(lines)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deck", default=os.environ.get("ENGLISH_DECK_PATH", DEFAULT_DECK_PATH))
    parser.add_argument('--date', default=None, help='Optional local review date YYYY-MM-DD')
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="add a correction card")
    p_add.add_argument("--wrong", required=True)
    p_add.add_argument("--correct", required=True)
    p_add.add_argument("--note", default="")

    sub.add_parser("due", help="print today's drill")

    p_rev = sub.add_parser("review", help="record a review result")
    p_rev.add_argument("--id", required=True)
    p_rev.add_argument("--result", choices=["correct", "wrong"], required=True)
    p_rev.add_argument('--expected-reviews', type=int, default=None,
                       help='Reject a stale or repeated UI review submission')

    p_weak = sub.add_parser(
        "weaknesses", help="print least-mastered cards for personalized coaching"
    )
    p_weak.add_argument("--limit", type=int, default=5)

    sub.add_parser("stats", help="print deck stats")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.cmd in ('add', 'review'):
        path = Path(args.deck)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            # A malformed deck must never become an empty replacement on write.
            deck = json.loads(path.read_text()) if path.exists() else {'cards': {}}
            if not isinstance(deck, dict) or not isinstance(deck.get('cards'), dict):
                raise ValueError('Invalid SRS deck; existing data preserved.')
            if args.cmd == 'add':
                deck, added = add_card(deck, args.wrong, args.correct, args.note, args.date)
                output = 'added' if added else 'duplicate (skipped)'
            else:
                card = deck['cards'][args.id]
                if args.expected_reviews is not None and card.get('reviews', 0) != args.expected_reviews:
                    raise ValueError('Card already changed; refresh before reviewing again.')
                review_card(deck, args.id, args.result == 'correct', args.date)
                output = json.dumps(stats(deck, args.date))
            save_deck(args.deck, deck)
        print(output)
        return 0
    deck = load_deck(args.deck)
    if args.cmd == "due":
        print(format_drill(due_cards(deck)))
    elif args.cmd == "weaknesses":
        print(
            json.dumps(
                {"weaknesses": weakness_cards(deck, args.limit)},
                indent=2,
                ensure_ascii=False,
            )
        )
    elif args.cmd == "stats":
        print(json.dumps(stats(deck), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
