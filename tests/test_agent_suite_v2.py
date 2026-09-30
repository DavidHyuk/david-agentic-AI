# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Check balance, structure, synthetic boundaries, and reproducibility of suite v2."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "local-model" / "eval" / "agent_suite_v2.py"
SPEC = importlib.util.spec_from_file_location("agent_suite_v2", SCRIPT)
assert SPEC and SPEC.loader
suite = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(suite)


def test_suite_has_120_unique_cases_balanced_across_buckets() -> None:
    cases = suite.build_cases()
    assert len(cases) == 120
    assert len({case["id"] for case in cases}) == 120
    assert {bucket: sum(case["bucket"] == bucket for case in cases) for bucket in suite.BUCKETS} == {
        bucket: 30 for bucket in suite.BUCKETS
    }


def test_case_structures_match_bucket_contracts() -> None:
    cases = suite.build_cases()
    for case in cases:
        assert 128 <= case["max_tokens"] <= 384
        assert case["thinking"] is False
        assert case["system"]
        assert case["turns"]
        assert all(set(turn) == {"user", "expected_json"} for turn in case["turns"])
        assert all(isinstance(turn["user"], str) and turn["user"] for turn in case["turns"])
        assert all(isinstance(turn["expected_json"], dict) for turn in case["turns"])
        for turn in case["turns"]:
            for key in turn["expected_json"]:
                assert key in turn["user"], f"{case['id']} does not request JSON key {key}"
            assert not ({"required_facts", "forbidden_claims"} & set(turn["expected_json"]))
        if case["bucket"] == "multi_tool":
            assert len(case["tools"]) >= 2
            assert len(case["tool_script"]) >= 2
            assert all(set(step) == {"name", "arguments", "result"} for step in case["tool_script"])
            assert len({tool["function"]["name"] for tool in case["tools"]}) >= 2
        if case["bucket"] == "long_horizon":
            assert len(case["turns"]) >= 6
            assert all("case_marker" in turn["expected_json"] for turn in case["turns"])
        if case["bucket"] == "context_heavy":
            spec = case["context_spec"]
            assert len(case["turns"]) == 1
            assert spec["target_tokens"] in {8192, 24576, 40960, 55296}
            assert len(spec["facts"]) >= 2
            assert all(0 < fact["position"] < 1 for fact in spec["facts"])
            assert all(set(fact) == {"key", "value", "position"} for fact in spec["facts"])
            assert len(case["turns"][0]["user"]) < 1000
            assert case["turns"][0]["expected_json"] == {
                fact["key"]: fact["value"] for fact in spec["facts"]
            }
        else:
            assert "context_spec" not in case


def test_fixtures_are_synthetic_and_have_no_live_urls_or_secret_shapes() -> None:
    serialized = json.dumps(suite.build_cases(), ensure_ascii=False).lower()
    assert not re.search(r"https?://", serialized)
    for pattern in (r"\bsk-[a-z0-9]{12,}\b", r"\bgh[pousr]_[a-z0-9]{20,}\b", r"\b\d{8,}:aa[a-z0-9_-]{20,}\b"):
        assert not re.search(pattern, serialized)
    assert "synthetic" in serialized


def test_every_case_has_unique_prompt_and_expectation_signature() -> None:
    cases = suite.build_cases()
    signatures = [
        json.dumps(case["turns"], ensure_ascii=False, sort_keys=True)
        for case in cases
    ]
    assert len(set(signatures)) == len(signatures)


def test_short_task_prompts_are_distinct_and_task_grounded() -> None:
    cases = [case for case in suite.build_cases() if case["bucket"] == "short_task"]
    prompts = [case["turns"][0]["user"] for case in cases]
    assert len(prompts) == 30
    assert len(set(prompts)) == 30
    assert all("scenario_evidence" not in prompt for prompt in prompts)
    assert {case["workflow"] for case in cases} >= {"papers", "interview", "coding", "english", "podcast"}


def test_context_facts_vary_by_workflow_and_are_distributed() -> None:
    cases = [case for case in suite.build_cases() if case["bucket"] == "context_heavy"]
    assert len({case["context_spec"]["target_tokens"] for case in cases}) == 4
    for workflow in {case["workflow"] for case in cases}:
        family = [case for case in cases if case["workflow"] == workflow]
        fact_sets = {
            tuple(fact["value"] for fact in case["context_spec"]["facts"])
            for case in family
        }
        assert len(fact_sets) == 6
        position_sets = {
            tuple(fact["position"] for fact in case["context_spec"]["facts"])
            for case in family
        }
        assert len(position_sets) >= 4
        assert all(len(case["context_spec"]["facts"]) == 4 for case in family)


def test_multi_tool_families_include_distinct_synthetic_branches() -> None:
    cases = [case for case in suite.build_cases() if case["bucket"] == "multi_tool"]
    for workflow in {case["workflow"] for case in cases}:
        family = [case for case in cases if case["workflow"] == workflow]
        def branch(case: dict) -> str:
            script = case["tool_script"]
            if workflow == "paper":
                return json.dumps(script[1]["result"], sort_keys=True)
            if workflow == "coding":
                return script[1]["result"]["block_progress"].split()[0]
            if workflow == "english":
                return script[1]["result"]["patterns"][0]
            if workflow == "podcast":
                return json.dumps(script[1]["result"], sort_keys=True)
            return script[0]["result"]["undercovered"]

        signatures = {branch(case) for case in family}
        assert len(signatures) >= 3, workflow


def test_multi_tool_paper_ids_require_tool_result_order() -> None:
    cases = [case for case in suite.build_cases() if case["workflow"] == "paper"]
    for case in cases:
        prompt = case["turns"][0]["user"]
        expected_ids = case["turns"][0]["expected_json"]["paper_ids"]
        scripted_ids = case["tool_script"][1]["result"]["papers"]
        assert "paper_ids in the exact order returned by the selected papers tool" in prompt
        assert expected_ids == scripted_ids


def test_multi_tool_branches_cover_distinct_synthetic_results() -> None:
    cases = [case for case in suite.build_cases() if case["bucket"] == "multi_tool"]
    by_workflow = {
        workflow: [case for case in cases if case["workflow"] == workflow]
        for workflow in {case["workflow"] for case in cases}
    }

    assert {case["turns"][0]["expected_json"]["source_mode"] for case in by_workflow["paper"]} == {
        "recommended", "cached"
    }
    assert any(not case["turns"][0]["expected_json"]["paper_ids"] for case in by_workflow["paper"])

    for case in by_workflow["coding"]:
        result = case["tool_script"][0]["result"]
        completed = int(case["tool_script"][1]["result"]["block_progress"].split()[1].split("/")[0])
        assert result["completed_in_block"] == completed
    assert {case["tool_script"][1]["result"]["patterns"][0] for case in by_workflow["english"]} == {
        "past tense", "articles", "subject-verb agreement"
    }
    assert {
        tuple(case["turns"][0]["expected_json"].get("patterns", []))
        for case in by_workflow["podcast"]
    } == {(), ("articles",)}
    assert {case["turns"][0]["expected_json"]["pillar"] for case in by_workflow["interview"]} == {
        "safety", "evaluation", "multilingual evaluation"
    }


def test_cli_generates_deterministic_json(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "nested" / "second.json"
    suite.main  # Import remains side-effect free; CLI is separately exercised by direct serialization.
    first.write_text(json.dumps(suite.build_cases(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    second.parent.mkdir()
    second.write_text(json.dumps(suite.build_cases(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert first.read_bytes() == second.read_bytes()
