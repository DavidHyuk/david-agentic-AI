# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for agenda.py calendar formatting, conflict + free-slot detection."""
import agenda


def _ev(summary, start, end, **kw):
    return {"summary": summary, "start": start, "end": end, **kw}


def test_sort_events():
    evs = [
        _ev("b", "2026-06-02T11:00:00", "2026-06-02T12:00:00"),
        _ev("a", "2026-06-02T09:00:00", "2026-06-02T10:00:00"),
    ]
    assert [e["summary"] for e in agenda.sort_events(evs)] == ["a", "b"]


def test_is_priority_keywords():
    assert agenda.is_priority(_ev("Onsite interview", "2026-06-02T09:00:00", "2026-06-02T10:00:00"))
    assert not agenda.is_priority(_ev("Lunch", "2026-06-02T12:00:00", "2026-06-02T13:00:00"))


def test_detect_conflicts_overlap():
    evs = [
        _ev("A", "2026-06-02T09:00:00", "2026-06-02T10:00:00"),
        _ev("B", "2026-06-02T09:30:00", "2026-06-02T10:30:00"),
        _ev("C", "2026-06-02T11:00:00", "2026-06-02T12:00:00"),
    ]
    conflicts = agenda.detect_conflicts(evs)
    assert len(conflicts) == 1
    assert {conflicts[0][0]["summary"], conflicts[0][1]["summary"]} == {"A", "B"}


def test_no_conflicts_when_back_to_back():
    evs = [
        _ev("A", "2026-06-02T09:00:00", "2026-06-02T10:00:00"),
        _ev("B", "2026-06-02T10:00:00", "2026-06-02T11:00:00"),
    ]
    assert agenda.detect_conflicts(evs) == []


def test_free_slots_finds_gaps():
    evs = [
        _ev("A", "2026-06-02T10:00:00", "2026-06-02T11:00:00"),
        _ev("B", "2026-06-02T14:00:00", "2026-06-02T15:00:00"),
    ]
    slots = agenda.free_slots(evs, day_start="09:00", day_end="18:00", min_minutes=45)
    # 09:00-10:00, 11:00-14:00, 15:00-18:00
    assert len(slots) == 3
    assert slots[0]["start"].endswith("09:00:00")


def test_free_slots_respects_min_minutes():
    evs = [
        _ev("A", "2026-06-02T09:00:00", "2026-06-02T09:30:00"),
        _ev("B", "2026-06-02T10:00:00", "2026-06-02T18:00:00"),
    ]
    # gap 09:30-10:00 is only 30 min -> excluded with min 45
    slots = agenda.free_slots(evs, day_start="09:00", day_end="18:00", min_minutes=45)
    assert slots == []


def test_to_brief_contains_sections():
    evs = [
        _ev("ML system design interview", "2026-06-02T10:00:00", "2026-06-02T11:00:00"),
        _ev("Standup", "2026-06-02T10:30:00", "2026-06-02T10:45:00"),
    ]
    brief = agenda.to_brief(evs)
    assert "Today's agenda" in brief
    assert "Don't miss" in brief        # priority interview
    assert "Overlaps" in brief          # standup overlaps interview


def test_empty_agenda():
    assert "No events" in agenda.to_brief([])
