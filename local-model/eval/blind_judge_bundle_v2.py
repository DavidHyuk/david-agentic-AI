#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Build a balanced model-blind semantic-judging bundle for benchmark v2."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any, Sequence


CASE_COUNT = 120


def canonical_digest(value: Any) -> str:
    """Match benchmark_suite_v2's canonical fixture digest."""
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_cases(path: Path) -> list[dict[str, Any]]:
    """Load the complete unique suite and index its expected fixture hashes."""
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or len(cases) != CASE_COUNT:
        raise ValueError(f"cases fixture must contain exactly {CASE_COUNT} cases")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            raise ValueError("every case must be an object with a string id")
        if case["id"] in seen:
            raise ValueError(f"duplicate case id in fixture: {case['id']}")
        seen.add(case["id"])
        if not isinstance(case.get("turns"), list) or not case["turns"]:
            raise ValueError(f"case has no turns: {case['id']}")
        if any(not isinstance(turn, dict) or not isinstance(turn.get("user"), str)
               or not isinstance(turn.get("expected_json"), dict) for turn in case["turns"]):
            raise ValueError(f"invalid turn/reference in case: {case['id']}")
    return cases


def load_results(
    path: Path, case_digests: dict[str, str], require_complete: bool = True
) -> dict[str, dict[str, Any]]:
    """Load one complete model result file, rejecting duplicates and mismatches."""
    results: dict[str, dict[str, Any]] = {}
    models: set[str] = set()
    runs: set[str] = set()
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.endswith("\n"):
                raise ValueError(f"incomplete JSONL row at {path}:{line_number}")
            if not line.strip():
                raise ValueError(f"blank JSONL row at {path}:{line_number}")
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL row at {path}:{line_number}") from exc
            if not isinstance(record, dict) or not isinstance(record.get("id"), str):
                raise ValueError(f"invalid result record at {path}:{line_number}")
            case_id = record["id"]
            if case_id in results:
                raise ValueError(f"duplicate result case id in {path}: {case_id}")
            if case_id not in case_digests:
                raise ValueError(f"unknown result case id in {path}: {case_id}")
            if record.get("case_sha256") != case_digests[case_id]:
                raise ValueError(f"case digest mismatch in {path}: {case_id}")
            model = record.get("model")
            if not isinstance(model, str) or not model.strip():
                raise ValueError(f"missing model ID in {path}: {case_id}")
            models.add(model)
            run_id = record.get("run_sha256")
            if not isinstance(run_id, str) or not run_id:
                raise ValueError(f"missing run identity in {path}: {case_id}")
            runs.add(run_id)
            results[case_id] = record
    if len(models) != 1:
        raise ValueError(f"result file must contain exactly one model ID: {path}")
    if len(runs) != 1:
        raise ValueError(f"result file must contain exactly one run identity: {path}")
    missing = set(case_digests) - set(results)
    if require_complete and missing:
        raise ValueError(f"incomplete result file {path}; missing {len(missing)} case IDs")
    if not results:
        raise ValueError(f"result file is empty: {path}")
    return results


def _candidate_trace(record: dict[str, Any]) -> dict[str, Any]:
    """Project only semantic response and tool details, excluding result metadata."""
    trace = record.get("trace")
    events = record.get("tool_events")
    if not isinstance(trace, list) or not isinstance(events, list):
        raise ValueError(f"result {record.get('id')} lacks trace/tool events")
    clean_trace: list[dict[str, Any]] = []
    for item in trace:
        if not isinstance(item, dict):
            raise ValueError(f"result {record.get('id')} has an invalid trace item")
        calls = item.get("tool_calls") or []
        if not isinstance(calls, list):
            raise ValueError(f"result {record.get('id')} has invalid tool calls")
        clean_calls = []
        for call in calls:
            function = call.get("function") if isinstance(call, dict) else None
            function = function if isinstance(function, dict) else {}
            clean_calls.append({
                "name": function.get("name"),
                "arguments": function.get("arguments"),
            })
        clean_trace.append({
            "turn": item.get("turn"),
            "step": item.get("step"),
            "content": item.get("content") or "",
            "finish_reason": item.get("finish_reason"),
            "tool_calls": clean_calls,
        })
    clean_events = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError(f"result {record.get('id')} has an invalid tool event")
        clean_events.append({key: event.get(key) for key in ("name", "arguments", "result")})
    return {"trace": clean_trace, "tool_events": clean_events}


def _case_prompt(case: dict[str, Any]) -> dict[str, Any]:
    """Project prompt/reference material without generated long-context filler."""
    prompt: dict[str, Any] = {
        "id": case["id"],
        "bucket": case.get("bucket"),
        "workflow": case.get("workflow"),
        "system": case.get("system", ""),
        "turns": [
            {"user": turn["user"], "reference": turn["expected_json"]}
            for turn in case["turns"]
        ],
    }
    if case.get("tools"):
        prompt["tools"] = case["tools"]
        prompt["tool_script"] = case.get("tool_script") or []
    if case.get("context_spec"):
        spec = case["context_spec"]
        prompt["context_spec"] = {
            key: spec[key] for key in ("target_tokens", "facts", "distractors") if key in spec
        }
    return prompt


def build_artifacts(
    cases: list[dict[str, Any]],
    left: dict[str, dict[str, Any]],
    right: dict[str, dict[str, Any]],
    salt: str,
    expected_count: int = CASE_COUNT,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build per-case HMAC-balanced A/B assignments and anonymous judge inputs."""
    if not salt:
        raise ValueError("salt must not be empty")
    case_ids = [case["id"] for case in cases]
    if len(case_ids) != expected_count or len(set(case_ids)) != expected_count:
        raise ValueError(f"fixture must have exactly {expected_count} unique case IDs")
    expected_ids = set(case_ids)
    if set(left) != expected_ids or set(right) != expected_ids:
        raise ValueError("both result files must contain the same complete fixture case IDs")
    case_digests = {case["id"]: canonical_digest(case) for case in cases}
    for case_id in case_ids:
        if left[case_id].get("case_sha256") != case_digests[case_id]:
            raise ValueError(f"left case digest mismatch: {case_id}")
        if right[case_id].get("case_sha256") != case_digests[case_id]:
            raise ValueError(f"right case digest mismatch: {case_id}")

    salt_bytes = salt.encode("utf-8")
    ranked_ids = sorted(
        case_ids,
        key=lambda case_id: (
            hmac.new(salt_bytes, case_id.encode("utf-8"), hashlib.sha256).digest(), case_id
        ),
    )
    left_as_a = set(ranked_ids[: expected_count // 2])
    mapping: dict[str, dict[str, str]] = {}
    bundle: list[dict[str, Any]] = []
    for case in cases:
        case_id = case["id"]
        left_record = left[case_id]
        right_record = right[case_id]
        if case_id in left_as_a:
            a_record, b_record = left_record, right_record
        else:
            a_record, b_record = right_record, left_record
        mapping[case_id] = {"A": a_record["model"], "B": b_record["model"]}
        item = _case_prompt(case)
        item["A"] = _candidate_trace(a_record)
        item["B"] = _candidate_trace(b_record)
        bundle.append(item)
    return bundle, {
        "assignments": mapping,
        "balance": {
            "A_from_left": len(left_as_a),
            "A_from_right": expected_count - len(left_as_a),
        },
    }


def create_bundle(args: argparse.Namespace) -> None:
    """Validate both full runs before writing new blind and sealed files."""
    if args.bundle.resolve() == args.mapping.resolve():
        raise ValueError("bundle and mapping must be different files")
    cases = load_cases(args.cases)
    case_digests = {case["id"]: canonical_digest(case) for case in cases}
    allow_partial = getattr(args, "allow_partial", False)
    left = load_results(args.left, case_digests, require_complete=not allow_partial)
    right = load_results(args.right, case_digests, require_complete=not allow_partial)
    if next(iter(left.values()))["model"] == next(iter(right.values()))["model"]:
        raise ValueError("paired result files must come from different models")
    if allow_partial:
        paired_ids = set(left) & set(right)
        if not paired_ids:
            raise ValueError("no paired case IDs available for partial audit")
        excluded_ids = [case["id"] for case in cases if case["id"] not in paired_ids]
        cases = [case for case in cases if case["id"] in paired_ids]
        left = {case_id: left[case_id] for case_id in paired_ids}
        right = {case_id: right[case_id] for case_id in paired_ids}
    else:
        excluded_ids = []
    bundle, mapping = build_artifacts(cases, left, right, args.salt, expected_count=len(cases))
    mapping["excluded_ids"] = excluded_ids
    destinations = (args.bundle, args.mapping)
    for path in destinations:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing file: {path}")
    args.bundle.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.mapping.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"created blind bundle for {len(bundle)} cases; keep {args.mapping} sealed until grading is saved")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse paths and the private HMAC assignment salt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--left", required=True, type=Path)
    parser.add_argument("--right", required=True, type=Path)
    parser.add_argument("--salt", required=True)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--allow-partial", action="store_true", help="audit only paired completed cases; record all exclusions")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run blind bundle creation from paired, complete benchmark results."""
    create_bundle(parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
