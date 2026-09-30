# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Test completeness, balanced blinding, and metadata stripping for judge bundles."""

from __future__ import annotations

import importlib.util
import json
from argparse import Namespace
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parent.parent / "local-model" / "eval" / "blind_judge_bundle_v2.py"
SPEC = importlib.util.spec_from_file_location("blind_judge_bundle_v2", SCRIPT)
assert SPEC and SPEC.loader
blind = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(blind)


def _inputs() -> tuple[list[dict], dict[str, dict], dict[str, dict]]:
    cases = []
    left = {}
    right = {}
    for index in range(120):
        case_id = f"case-{index:03d}"
        case = {
            "id": case_id,
            "bucket": "multi_tool" if index == 1 else "context_heavy" if index == 2 else "short_task",
            "workflow": "synthetic",
            "system": "Use only fixture facts.",
            "turns": [{"user": f"Question {index}", "expected_json": {"value": f"v{index}"}}],
        }
        if index == 1:
            case["tools"] = [{"type": "function", "function": {"name": "read_mock"}}]
            case["tool_script"] = [{"name": "read_mock", "arguments": {}, "result": {"value": "fixture"}}]
        if index == 2:
            case["context_spec"] = {
                "target_tokens": 8192,
                "facts": [{"key": "value", "value": "v2", "position": 0.5}],
                "distractors": ["unverified",],
                "filler": "large generated filler must not be included",
            }
        cases.append(case)
        digest = blind.canonical_digest(case)
        for side, model in ((left, "model-left"), (right, "model-right")):
            side[case_id] = {
                "id": case_id,
                "model": model,
                "case_sha256": digest,
                "run_sha256": "run-hash",
                "case_pass": True,
                "turn_pass": [True],
                "tool_sequence_pass": True,
                "wall_s": 1.23,
                "ttft_s": 0.4,
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "trace": [{
                    "turn": 0,
                    "step": 0,
                    "content": '{"value":"answer"}',
                    "finish_reason": "stop",
                    "wall_s": 0.8,
                    "ttft_s": 0.2,
                    "usage": {"prompt_tokens": 100},
                    "tool_calls": [{
                        "id": "provider-call-id",
                        "function": {"name": "read_mock", "arguments": "{}"},
                    }],
                }],
                "tool_events": [{
                    "name": "read_mock", "arguments": "{}", "result": {"value": "fixture"},
                    "correct": True,
                }],
                "result_path": "/private/run/result.jsonl",
            }
    return cases, left, right


def test_hmac_mapping_is_deterministic_balanced_and_separate() -> None:
    cases, left, right = _inputs()
    bundle_a, mapping_a = blind.build_artifacts(cases, left, right, "fixed-salt")
    bundle_b, mapping_b = blind.build_artifacts(cases, left, right, "fixed-salt")
    assert mapping_a == mapping_b
    assert bundle_a == bundle_b
    assignments = mapping_a["assignments"]
    assert len(assignments) == 120
    assert sum(item["A"] == "model-left" for item in assignments.values()) == 60
    assert sum(item["A"] == "model-right" for item in assignments.values()) == 60
    assert mapping_a["balance"] == {"A_from_left": 60, "A_from_right": 60}


def test_bundle_keeps_grading_material_but_strips_result_metadata() -> None:
    cases, left, right = _inputs()
    bundle, mapping = blind.build_artifacts(cases, left, right, "fixed-salt")
    encoded_bundle = json.dumps(bundle, ensure_ascii=False)
    assert "model-left" not in encoded_bundle and "model-right" not in encoded_bundle
    assert "case_sha256" not in encoded_bundle and "run_sha256" not in encoded_bundle
    assert "case_pass" not in encoded_bundle and "turn_pass" not in encoded_bundle
    assert "tool_sequence_pass" not in encoded_bundle and "correct" not in encoded_bundle
    assert "wall_s" not in encoded_bundle and "ttft_s" not in encoded_bundle
    assert "usage" not in encoded_bundle and "result_path" not in encoded_bundle
    assert "provider-call-id" not in encoded_bundle
    assert "model-left" in json.dumps(mapping)

    tool_case = bundle[1]
    assert tool_case["turns"][0]["reference"] == {"value": "v1"}
    assert tool_case["tools"][0]["function"]["name"] == "read_mock"
    assert tool_case["tool_script"][0]["result"] == {"value": "fixture"}
    candidate = tool_case["A"]
    assert candidate["trace"][0]["tool_calls"] == [{"name": "read_mock", "arguments": "{}"}]
    assert candidate["tool_events"] == [{
        "name": "read_mock", "arguments": "{}", "result": {"value": "fixture"}
    }]

    context_case = bundle[2]
    assert context_case["context_spec"]["facts"] == cases[2]["context_spec"]["facts"]
    assert "filler" not in context_case["context_spec"]


def test_incomplete_or_mismatched_result_sets_fail_closed() -> None:
    cases, left, right = _inputs()
    del left["case-119"]
    with pytest.raises(ValueError, match="complete fixture case IDs"):
        blind.build_artifacts(cases, left, right, "salt")

    cases, left, right = _inputs()
    right["case-010"]["case_sha256"] = "wrong"
    with pytest.raises(ValueError, match="right case digest mismatch"):
        blind.build_artifacts(cases, left, right, "salt")


def test_jsonl_loader_requires_all_cases_and_rejects_duplicate_rows(tmp_path: Path) -> None:
    cases, left, _ = _inputs()
    fixture = {case["id"]: blind.canonical_digest(case) for case in cases}
    path = tmp_path / "results.jsonl"
    path.write_text("\n".join(json.dumps(left[case_id]) for case_id in left) + "\n", encoding="utf-8")
    loaded = blind.load_results(path, fixture)
    assert len(loaded) == 120

    path.write_text(json.dumps(left["case-000"]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="incomplete result file"):
        blind.load_results(path, fixture)

    path.write_text(
        json.dumps(left["case-000"]) + "\n" + json.dumps(left["case-000"]) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate result case id"):
        blind.load_results(path, fixture)

    path.write_text(json.dumps(left["case-000"]), encoding="utf-8")
    with pytest.raises(ValueError, match="incomplete JSONL row"):
        blind.load_results(path, fixture)


def test_cli_writes_distinct_new_bundle_and_mapping_files(tmp_path: Path) -> None:
    cases, left, right = _inputs()
    cases_path = tmp_path / "cases.json"
    left_path = tmp_path / "left.jsonl"
    right_path = tmp_path / "right.jsonl"
    bundle_path = tmp_path / "out" / "blind.json"
    mapping_path = tmp_path / "out" / "sealed.json"
    cases_path.write_text(json.dumps(cases), encoding="utf-8")
    for path, rows in ((left_path, left), (right_path, right)):
        path.write_text("\n".join(json.dumps(row) for row in rows.values()) + "\n", encoding="utf-8")
    args = Namespace(
        cases=cases_path, left=left_path, right=right_path, salt="salt",
        bundle=bundle_path, mapping=mapping_path,
    )
    blind.create_bundle(args)
    assert len(json.loads(bundle_path.read_text(encoding="utf-8"))) == 120
    assert len(json.loads(mapping_path.read_text(encoding="utf-8"))["assignments"]) == 120
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        blind.create_bundle(args)

    for record in right.values():
        record["model"] = "model-left"
    right_path.write_text("\n".join(json.dumps(row) for row in right.values()) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="different models"):
        blind.create_bundle(args)


def test_partial_audit_records_exclusions_without_imputing_missing_cases(tmp_path: Path) -> None:
    cases, left, right = _inputs()
    cases_path = tmp_path / "cases.json"
    left_path = tmp_path / "left.jsonl"
    right_path = tmp_path / "right.jsonl"
    cases_path.write_text(json.dumps(cases), encoding="utf-8")
    left_path.write_text("\n".join(json.dumps(row) for row in left.values()) + "\n", encoding="utf-8")
    del right["case-118"]
    del right["case-119"]
    right_path.write_text("\n".join(json.dumps(row) for row in right.values()) + "\n", encoding="utf-8")
    args = Namespace(
        cases=cases_path, left=left_path, right=right_path, salt="fixed-salt",
        bundle=tmp_path / "blind.json", mapping=tmp_path / "mapping.json",
        allow_partial=True,
    )
    blind.create_bundle(args)
    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
    assert len(bundle) == 118
    assert len(mapping["assignments"]) == 118
    assert mapping["balance"] == {"A_from_left": 59, "A_from_right": 59}
    assert mapping["excluded_ids"] == ["case-118", "case-119"]
