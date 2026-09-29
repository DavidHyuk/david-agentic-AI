# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Validate synthetic agent cases, API payloads, and unbiased result bookkeeping."""

from __future__ import annotations

import importlib.util
import io
import json
from argparse import Namespace
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parent.parent / "local-model" / "eval" / "benchmark_agents.py"
SPEC = importlib.util.spec_from_file_location("benchmark_agents", SCRIPT)
assert SPEC and SPEC.loader
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def test_case_fixture_is_unique_and_covers_agent_workflows() -> None:
    cases = benchmark.load_cases(benchmark.DEFAULT_CASES)
    assert len(cases) == 14
    assert {case["workflow"] for case in cases} == {
        "papers", "interview", "system_design", "coding", "english",
        "podcast", "tools", "vision", "long_context",
    }
    assert len({case["id"] for case in cases}) == len(cases)


def test_duplicate_case_is_rejected(tmp_path: Path) -> None:
    case = benchmark.load_cases(benchmark.DEFAULT_CASES)[0]
    fixture = tmp_path / "cases.json"
    fixture.write_text(json.dumps([case, case]))
    with pytest.raises(ValueError, match="duplicate"):
        benchmark.load_cases(fixture)


def test_payload_keeps_sampling_equal_and_tool_choice_unforced() -> None:
    cases = {case["id"]: case for case in benchmark.load_cases(benchmark.DEFAULT_CASES)}
    paper = benchmark.request_payload(cases["papers_digest"], "test-model")
    assert paper["temperature"] == 0
    assert paper["chat_template_kwargs"] == {"enable_thinking": False}
    assert paper["stream"] is True
    tool = benchmark.request_payload(cases["tool_papers"], "test-model")
    assert tool["tool_choice"] == "auto"
    assert tool["stream"] is False


def test_tool_scoring_parses_json_semantics_not_key_order() -> None:
    case = next(case for case in benchmark.load_cases(benchmark.DEFAULT_CASES) if case["id"] == "tool_papers")
    record = {"tool_calls": [{"function": {"name": "query_papers", "arguments": '{"limit":8,"days":4,"mode":"recommended"}'}}]}
    assert benchmark.tool_success(case, record)
    record["tool_calls"][0]["function"]["arguments"] = '{"limit":7,"days":4,"mode":"recommended"}'
    assert not benchmark.tool_success(case, record)
    record["tool_calls"][0]["function"]["arguments"] = '{"limit":8,"days":4,"mode":"recommended"}'
    record["tool_calls"].append(record["tool_calls"][0])
    assert not benchmark.tool_success(case, record)


def test_sse_parser_records_first_token_and_usage() -> None:
    lines = io.BytesIO(
        b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'
        b'data: {"choices":[],"usage":{"completion_tokens":1}}\n\n'
        b'data: [DONE]\n\n'
    )
    result = benchmark.parse_sse(lines, 0.0)
    assert result["output_text"] == "hello"
    assert result["usage"]["completion_tokens"] == 1
    assert result["ttft_s"] is not None


def test_long_prompt_has_single_middle_answer() -> None:
    prompt = benchmark.long_context_prompt()
    assert prompt.count("prefix-cache invalidation after tool calls") == 1
    assert len(prompt) > 50000


def test_blind_bundle_hides_model_names_and_seals_mapping(tmp_path: Path) -> None:
    case = benchmark.load_cases(benchmark.DEFAULT_CASES)[0]
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps([case]))
    left = tmp_path / "left.jsonl"
    right = tmp_path / "right.jsonl"
    benchmark.save_record(left, {"id": case["id"], "model": "first-model", "case_sha256": benchmark.case_digest(case), "output_text": "first answer"})
    benchmark.save_record(right, {"id": case["id"], "model": "second-model", "case_sha256": benchmark.case_digest(case), "output_text": "second answer"})
    bundle = tmp_path / "blind.json"
    mapping = tmp_path / "mapping.json"
    benchmark.blind(Namespace(cases=cases_path, left=left, right=right, bundle=bundle, mapping=mapping, salt="fixed"))
    blinded = bundle.read_text()
    assert "first-model" not in blinded
    assert "second-model" not in blinded
    assert "first answer" in blinded and "second answer" in blinded
    assert set(json.loads(mapping.read_text())[case["id"]].values()) == {"first-model", "second-model"}
