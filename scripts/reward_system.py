#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Turn verified learning activity into idempotent Career Cash rewards.

Career Cash is a motivational game currency with no monetary value. Evidence is
read from existing coach, English SRS, and Observatory paper state; assignments
or generated agent messages alone never count as completion.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import fcntl
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Sequence


DEFAULT_HOME = Path(os.path.expanduser("~/.hermes"))
AWARDS = {"coding": 30, "design": 45, "english": 10, "paper": 20}
DAILY_COMBO = 15
WEEKLY_BONUS = 150
WEEKLY_GOALS = {"coding": 3, "design": 1, "english": 3, "paper": 1}
OFFER_LEVELS = (
    (250, "Startup Recruiter Coffee Chat"),
    (500, "Big Tech Recruiter Screen"),
    (1000, "Virtual Onsite Invitation"),
    (2000, "Competing Offer Finale"),
)


def empty_state() -> dict[str, Any]:
    return {"version": 1, "ledger": [], "unlocks": [], "notified_ids": []}


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def load_state(path: Path) -> dict[str, Any]:
    state = read_json(path, empty_state())
    if (not isinstance(state, dict) or state.get("version") != 1
            or not isinstance(state.get("ledger"), list)
            or not isinstance(state.get("unlocks"), list)
            or not isinstance(state.get("notified_ids"), list)):
        raise ValueError("Invalid reward state; existing data preserved.")
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False,
    ) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(state, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _paper_dates(workspace: dict[str, Any]) -> dict[str, str]:
    latest: dict[str, float] = {}
    for event in workspace.get("events", []):
        if event.get("action") == "paper_read" and event.get("paper"):
            latest[str(event["paper"])] = float(event.get("time", 0))
    return {
        paper_id: datetime.fromtimestamp(timestamp).astimezone().date().isoformat()
        for paper_id, timestamp in latest.items()
        if workspace.get("papers", {}).get(paper_id, {}).get("read")
    }


def collect_evidence(home: Path) -> list[dict[str, str]]:
    """Return deterministic completion evidence from user-owned progress data."""
    evidence: list[dict[str, str]] = []
    coach = read_json(
        home / "data/interview/coach_state.json",
        {"coding": [], "system_design": []},
    )
    for category, key, label_key in (
        ("coding", "coding", "problem"),
        ("design", "system_design", "topic"),
    ):
        for row in coach.get(key, []):
            if row.get("id") and row.get("date"):
                evidence.append({
                    "id": f"{category}:{row['id']}",
                    "category": category,
                    "date": str(row["date"]),
                    "label": str(row.get(label_key) or row.get("item_id") or category),
                })
    deck = read_json(home / "data/english/srs_deck.json", {"cards": {}})
    english_days = sorted({
        str(card["last_review"])
        for card in deck.get("cards", {}).values() if card.get("last_review")
    })
    evidence.extend({
        "id": f"english:{day}", "category": "english", "date": day,
        "label": "English SRS review",
    } for day in english_days)
    workspace = read_json(
        home / "data/observatory/workspace.json", {"papers": {}, "events": []},
    )
    for paper_id, day in _paper_dates(workspace).items():
        title = workspace.get("papers", {}).get(paper_id, {}).get("title") or paper_id
        evidence.append({
            "id": f"paper:{paper_id}", "category": "paper", "date": day,
            "label": str(title),
        })
    return sorted(evidence, key=lambda item: (item["date"], item["id"]))


def week_start(day: str) -> str:
    current = date.fromisoformat(day)
    return (current - timedelta(days=current.weekday())).isoformat()


def _activity_counts(entries: list[dict[str, Any]], start: str) -> dict[str, int]:
    end = (date.fromisoformat(start) + timedelta(days=6)).isoformat()
    by_category = {category: set() for category in WEEKLY_GOALS}
    for entry in entries:
        if entry.get("kind") == "activity" and start <= entry["date"] <= end:
            value = entry["date"] if entry["category"] == "english" else entry["id"]
            by_category[entry["category"]].add(value)
    return {category: len(values) for category, values in by_category.items()}


def sync_state(state: dict[str, Any], evidence: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Add unseen evidence, daily combos, weekly bonuses, and offer unlocks."""
    known = {entry["id"] for entry in state["ledger"]}
    added: list[dict[str, Any]] = []
    for item in evidence:
        if item["id"] in known:
            continue
        entry = {**item, "kind": "activity", "amount": AWARDS[item["category"]]}
        state["ledger"].append(entry)
        added.append(entry)
        known.add(item["id"])

    activity_days = sorted({entry["date"] for entry in state["ledger"]
                            if entry.get("kind") == "activity"})
    for day in activity_days:
        categories = {entry["category"] for entry in state["ledger"]
                      if entry.get("kind") == "activity" and entry["date"] == day}
        entry_id = f"daily-combo:{day}"
        if len(categories) >= 2 and entry_id not in known:
            entry = {"id": entry_id, "kind": "daily_combo", "date": day,
                     "category": "combo", "label": "Daily mission combo",
                     "amount": DAILY_COMBO}
            state["ledger"].append(entry)
            added.append(entry)
            known.add(entry_id)

    for start in sorted({week_start(day) for day in activity_days}):
        counts = _activity_counts(state["ledger"], start)
        entry_id = f"weekly-clear:{start}"
        if all(counts[key] >= goal for key, goal in WEEKLY_GOALS.items()) and entry_id not in known:
            entry = {"id": entry_id, "kind": "weekly_clear", "date": start,
                     "category": "weekly", "label": "Weekly mission clear",
                     "amount": WEEKLY_BONUS}
            state["ledger"].append(entry)
            added.append(entry)
            known.add(entry_id)

    balance = sum(int(entry["amount"]) for entry in state["ledger"])
    unlocked = {item["threshold"] for item in state["unlocks"]}
    for threshold, label in OFFER_LEVELS:
        if balance >= threshold and threshold not in unlocked:
            state["unlocks"].append({
                "threshold": threshold, "label": label,
                "unlocked_on": max(activity_days, default=date.today().isoformat()),
            })
    state["ledger"].sort(key=lambda item: (item["date"], item["id"]))
    return added


def streak(activity_days: set[str], today: str) -> int:
    current = date.fromisoformat(today)
    if current.isoformat() not in activity_days:
        current -= timedelta(days=1)
    count = 0
    while current.isoformat() in activity_days:
        count += 1
        current -= timedelta(days=1)
    return count


def status(state: dict[str, Any], today: str) -> dict[str, Any]:
    activities = [entry for entry in state["ledger"] if entry.get("kind") == "activity"]
    activity_days = {entry["date"] for entry in activities}
    start = week_start(today)
    counts = _activity_counts(activities, start)
    balance = sum(int(entry["amount"]) for entry in state["ledger"])
    next_offer = next(({"threshold": threshold, "label": label,
                        "remaining": threshold - balance}
                       for threshold, label in OFFER_LEVELS if threshold > balance), None)
    today_categories = sorted({entry["category"] for entry in activities
                               if entry["date"] == today})
    return {
        "currency": "Career Cash",
        "disclaimer": "게임용 가상 보상이며 실제 현금이나 채용 제안이 아닙니다.",
        "balance": balance,
        "streak": streak(activity_days, today),
        "today": {"cleared": bool(today_categories), "categories": today_categories,
                  "combo": len(today_categories) >= 2},
        "weekly": {"week_start": start, "counts": counts, "goals": WEEKLY_GOALS,
                   "cleared": all(counts[key] >= goal for key, goal in WEEKLY_GOALS.items())},
        "unlocks": state["unlocks"],
        "next_offer": next_offer,
        "recent": list(reversed(state["ledger"][-8:])),
    }


def notification(state: dict[str, Any], report: dict[str, Any]) -> str:
    notified = set(state["notified_ids"])
    fresh = [entry for entry in state["ledger"] if entry["id"] not in notified]
    if not fresh:
        return "[SILENT]"
    earned = sum(int(entry["amount"]) for entry in fresh)
    labels = ", ".join(entry["label"] for entry in fresh[-3:])
    weekly = report["weekly"]
    progress = " · ".join(
        f"{key} {min(weekly['counts'][key], goal)}/{goal}"
        for key, goal in weekly["goals"].items()
    )
    next_line = (f"다음 게임 보상: {report['next_offer']['label']}까지 "
                 f"${report['next_offer']['remaining']}" if report["next_offer"]
                 else "모든 게임 보상 카드를 해금했습니다.")
    state["notified_ids"] = [entry["id"] for entry in state["ledger"]]
    return (f"💰 Career Cash +${earned}\n{labels}\n\n"
            f"잔액 ${report['balance']} · 연속 {report['streak']}일\n"
            f"이번 주: {progress}\n{next_line}\n"
            "※ Career Cash와 제안 카드는 동기부여용 가상 보상입니다.")


def run(home: Path, command: str, today: str) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    state_path = home / "data/rewards/state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with (state_path.parent / "state.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = load_state(state_path)
        before = json.dumps(state, sort_keys=True)
        added = sync_state(state, collect_evidence(home))
        report = status(state, today)
        message = notification(state, report) if command == "notify" else None
        if not state_path.exists() or json.dumps(state, sort_keys=True) != before:
            save_state(state_path, state)
    return report, added, message


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=DEFAULT_HOME)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("command", choices=("status", "sync", "notify"))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    date.fromisoformat(args.date)
    report, added, message = run(args.home.expanduser(), args.command, args.date)
    if args.command == "notify":
        print(message)
    else:
        print(json.dumps({**report, "earned": sum(item["amount"] for item in added),
                          "new_rewards": added}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
