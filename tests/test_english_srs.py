# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for the Leitner spaced-repetition deck (english_srs.py)."""
from datetime import date, timedelta

import english_srs as srs


def test_add_card_dedup():
    deck = {"cards": {}}
    deck, added1 = srs.add_card(deck, "I have 25 years", "I am 25 years old")
    deck, added2 = srs.add_card(deck, "I have 25 years", "I am 25 years old")
    assert added1 is True and added2 is False
    assert len(deck["cards"]) == 1


def test_new_card_is_due_today():
    deck = {"cards": {}}
    deck, _ = srs.add_card(deck, "wrong", "right", today="2026-06-02")
    due = srs.due_cards(deck, today="2026-06-02")
    assert len(due) == 1


def test_correct_review_promotes_and_pushes_due_out():
    deck = {"cards": {}}
    deck, _ = srs.add_card(deck, "wrong", "right", today="2026-06-02")
    cid = next(iter(deck["cards"]))
    srs.review_card(deck, cid, correct=True, today="2026-06-02")
    card = deck["cards"][cid]
    assert card["box"] == 2
    # box 2 -> interval 2 days, so not due the next day
    assert srs.due_cards(deck, today="2026-06-03") == []
    assert len(srs.due_cards(deck, today="2026-06-04")) == 1


def test_wrong_review_resets_to_box_1():
    deck = {"cards": {}}
    deck, _ = srs.add_card(deck, "wrong", "right", today="2026-06-02")
    cid = next(iter(deck["cards"]))
    srs.review_card(deck, cid, correct=True, today="2026-06-02")   # -> box 2
    srs.review_card(deck, cid, correct=False, today="2026-06-04")  # back to box 1
    assert deck["cards"][cid]["box"] == 1
    due = date.fromisoformat(deck["cards"][cid]["due"])
    assert due == date(2026, 6, 5)  # box 1 -> +1 day


def test_box_capped_at_max():
    deck = {"cards": {}}
    deck, _ = srs.add_card(deck, "w", "r", today="2026-06-02")
    cid = next(iter(deck["cards"]))
    for _ in range(10):
        srs.review_card(deck, cid, correct=True, today="2026-06-02")
    assert deck["cards"][cid]["box"] == srs.MAX_BOX


def test_stats_and_drill_format():
    deck = {"cards": {}}
    deck, _ = srs.add_card(deck, "I go store", "I went to the store", today="2026-06-02")
    st = srs.stats(deck, today="2026-06-02")
    assert st["total"] == 1 and st["due"] == 1
    drill = srs.format_drill(srs.due_cards(deck, today="2026-06-02"))
    assert "I go store" in drill and "I went to the store" in drill


def test_empty_drill_message():
    assert "Nothing due" in srs.format_drill([])
