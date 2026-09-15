# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for evidence-backed Career Cash rewards and quiet notifications."""
from __future__ import annotations

import json
from pathlib import Path

import reward_system as rewards


def evidence_home(tmp_path: Path) -> Path:
    home = tmp_path / "hermes"
    (home / "data/interview").mkdir(parents=True)
    (home / "data/english").mkdir(parents=True)
    (home / "data/observatory").mkdir(parents=True)
    (home / "data/interview/coach_state.json").write_text(json.dumps({
        "coding": [{"id": "coding:2026-09-15", "date": "2026-09-15",
                    "problem": "Two Sum"}],
        "system_design": [],
    }))
    (home / "data/english/srs_deck.json").write_text(json.dumps({"cards": {
        "one": {"last_review": "2026-09-15"},
        "two": {"last_review": "2026-09-15"},
    }}))
    (home / "data/observatory/workspace.json").write_text(json.dumps({
        "papers": {}, "events": [],
    }))
    return home


def test_sync_uses_verified_activity_and_is_idempotent(tmp_path):
    home = evidence_home(tmp_path)

    first, added, _ = rewards.run(home, "sync", "2026-09-15")
    second, repeated, _ = rewards.run(home, "sync", "2026-09-15")

    assert first["balance"] == 55  # coding 30 + English day 10 + combo 15
    assert first["today"] == {
        "cleared": True, "categories": ["coding", "english"], "combo": True,
    }
    assert sum(item["amount"] for item in added) == 55
    assert second["balance"] == 55
    assert repeated == []


def test_assignment_without_completion_earns_nothing(tmp_path):
    home = evidence_home(tmp_path)
    (home / "data/interview/coach_state.json").write_text(json.dumps({
        "coding": [], "system_design": [],
        "assignments": {"coding:2026-09-15": {"completed": False}},
    }))
    (home / "data/english/srs_deck.json").write_text('{"cards": {}}')

    report, added, _ = rewards.run(home, "sync", "2026-09-15")

    assert report["balance"] == 0
    assert added == []
    assert report["today"]["cleared"] is False


def test_weekly_clear_unlocks_bonus_and_virtual_offer(tmp_path):
    home = evidence_home(tmp_path)
    coach = {
        "coding": [
            {"id": f"coding:2026-09-{day}", "date": f"2026-09-{day}",
             "problem": "Problem"} for day in (14, 15, 16)
        ],
        "system_design": [{"id": "design:2026-09-20", "date": "2026-09-20",
                           "topic": "Notification System"}],
    }
    (home / "data/interview/coach_state.json").write_text(json.dumps(coach))
    (home / "data/english/srs_deck.json").write_text(json.dumps({"cards": {
        str(day): {"last_review": f"2026-09-{day}"} for day in (14, 15, 16)
    }}))
    workspace = {"papers": {"p1": {"title": "Paper", "read": True}},
                 "events": [{"action": "paper_read", "paper": "p1",
                             "time": 1789902000}]}
    (home / "data/observatory/workspace.json").write_text(json.dumps(workspace))

    report, _, _ = rewards.run(home, "sync", "2026-09-20")

    assert report["weekly"]["cleared"] is True
    assert report["balance"] >= 250
    assert report["unlocks"][0]["label"] == "Startup Recruiter Coffee Chat"
    assert "실제 현금이나 채용 제안이 아닙니다" in report["disclaimer"]


def test_notify_sends_new_rewards_once(tmp_path):
    home = evidence_home(tmp_path)

    report, _, first = rewards.run(home, "notify", "2026-09-15")
    _, _, second = rewards.run(home, "notify", "2026-09-15")

    assert "Career Cash +$55" in first
    assert f"잔액 ${report['balance']}" in first
    assert "가상 보상" in first
    assert second == "[SILENT]"


def test_streak_uses_yesterday_when_today_has_not_started():
    assert rewards.streak({"2026-09-13", "2026-09-14"}, "2026-09-15") == 2
    assert rewards.streak({"2026-09-13"}, "2026-09-15") == 0
