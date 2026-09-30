# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Test deterministic grading, synthetic tool loops, and crash-safe bookkeeping."""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parent.parent / "local-model" / "eval" / "benchmark_suite_v2.py"
SPEC = importlib.util.spec_from_file_location("benchmark_suite_v2", SCRIPT)
assert SPEC and SPEC.loader
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def _base_case(bucket: str = "short_task") -> dict:
    return {
        "id": "fixture-1",
        "bucket": bucket,
        "workflow": "papers",
        "system": "Return JSON only.",
        "turns": [{"user": "Return value=ok.", "expected_json": {"value": "ok"}}],
        "max_tokens": 64,
        "thinking": False,
    }


def _response(content: str = "", calls: list | None = None, finish: str = "stop") -> dict:
    return {
        "content": content,
        "tool_calls": calls or [],
        "usage": {"prompt_tokens": 10, "completion_tokens": 3},
        "finish_reason": finish,
        "ttft_s": None,
        "wall_s": 0.01,
    }


def test_expected_json_subset_and_fenced_json() -> None:
    assert benchmark.expected_subset({"b": 2, "a": ["x", "y"]}, {"a": ["x", "y"]})
    assert not benchmark.expected_subset({"a": ["x"]}, {"a": ["x", "y"]})
    assert benchmark.expected_subset(
        {"evidence": "21% simulated KV reduction on synthetic prompts"},
        {"evidence": {"$contains": "synthetic prompts"}},
    )
    assert not benchmark.expected_subset(
        {"evidence": "opposite result"}, {"evidence": {"$contains": "synthetic prompts"}}
    )
    assert benchmark.expected_subset({"summary": "근거가 부족합니다."}, {"summary": {"$language": "ko"}})
    assert not benchmark.expected_subset({"summary": "insufficient evidence"}, {"summary": {"$language": "ko"}})
    assert not benchmark.expected_subset({"completed": 0}, {"completed": False})
    assert benchmark.expected_subset({"evidence": ["full phrase about synthetic prompts"]},
                                     {"evidence": {"$contains": "synthetic prompts"}})
    with pytest.raises(ValueError, match="operator"):
        benchmark.validate_expectation({"summary": {"$language": "fr"}})
    assert benchmark.parse_json_answer('```json\n{"value":"ok"}\n```') == {"value": "ok"}
    with pytest.raises(json.JSONDecodeError):
        benchmark.parse_json_answer('prose {"value":"ok"}')


def test_synthetic_multi_tool_loop_uses_results_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    case = _base_case("multi_tool")
    case["tools"] = [
        {"type": "function", "function": {"name": "read_status", "parameters": {"type": "object"}}},
        {"type": "function", "function": {"name": "read_detail", "parameters": {"type": "object"}}},
    ]
    case["tool_script"] = [
        {"name": "read_status", "arguments": {"id": "x"}, "result": {"rev": "r1"}},
        {"name": "read_detail", "arguments": {"rev": "r1"}, "result": {"value": "ok"}},
    ]
    replies = iter([
        _response(calls=[{"id": "call_1", "function": {"name": "read_status", "arguments": '{"id":"x"}'}}]),
        _response(calls=[{"id": "call_2", "function": {"name": "read_detail", "arguments": '{"rev":"r1"}'}}]),
        _response(content='{"value":"ok"}'),
    ])
    requests: list[list[dict]] = []

    def fake_request(messages, *_args):
        requests.append(json.loads(json.dumps(messages)))
        return next(replies)

    monkeypatch.setattr(benchmark, "request_completion", fake_request)
    result = benchmark.run_case(case, "mock-model", "http://127.0.0.1:8000/v1", 10, "run-digest")
    assert result["case_pass"] is True
    assert result["tool_sequence_pass"] is True
    assert [event["name"] for event in result["tool_events"]] == ["read_status", "read_detail"]
    assert json.loads(requests[1][-1]["content"]) == {"rev": "r1"}
    assert json.loads(requests[2][-1]["content"]) == {"value": "ok"}
    assert result["prompt_tokens"] == 30


def test_wrong_tool_call_fails_even_if_final_answer_is_correct(monkeypatch: pytest.MonkeyPatch) -> None:
    case = _base_case("multi_tool")
    case["tools"] = [{"type": "function", "function": {"name": name}} for name in ("first", "second")]
    case["tool_script"] = [
        {"name": "first", "arguments": {"x": 1}, "result": {"value": "a"}},
        {"name": "second", "arguments": {"x": 2}, "result": {"value": "ok"}},
    ]
    replies = iter([
        _response(calls=[{"function": {"name": "second", "arguments": '{"x":2}'}}]),
        _response(content='{"value":"ok"}'),
    ])
    monkeypatch.setattr(benchmark, "request_completion", lambda *_args: next(replies))
    result = benchmark.run_case(case, "mock-model", "http://127.0.0.1:8000/v1", 10, "run-digest")
    assert result["turn_pass"] == [True]
    assert result["tool_sequence_pass"] is False
    assert result["case_pass"] is False
    assert result["tool_events"][0]["result"]["error"]


def test_parallel_dependent_tool_calls_fail_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    case = _base_case("multi_tool")
    case["tools"] = [{"type": "function", "function": {"name": name}} for name in ("first", "second")]
    case["tool_script"] = [
        {"name": "first", "arguments": {}, "result": {"revision": "r1"}},
        {"name": "second", "arguments": {"revision": "r1"}, "result": {"value": "ok"}},
    ]
    replies = iter([
        _response(calls=[
            {"id": "one", "function": {"name": "first", "arguments": "{}"}},
            {"id": "two", "function": {"name": "second", "arguments": '{"revision":"r1"}'}},
        ]),
        _response(content='{"value":"ok"}'),
    ])
    monkeypatch.setattr(benchmark, "request_completion", lambda *_args: next(replies))
    result = benchmark.run_case(case, "mock-model", "http://127.0.0.1:8000/v1", 10, "run-digest")
    assert result["turn_pass"] == [True]
    assert result["tool_sequence_pass"] is False
    assert result["case_pass"] is False


def test_long_horizon_carries_history_and_scores_each_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    case = _base_case("long_horizon")
    case["turns"] = [
        {"user": f"Turn {index}", "expected_json": {"state": index}}
        for index in range(4)
    ]
    replies = iter([_response(content=json.dumps({"state": index})) for index in range(4)])
    history_sizes: list[int] = []

    def fake_request(messages, *_args):
        history_sizes.append(len(messages))
        return next(replies)

    monkeypatch.setattr(benchmark, "request_completion", fake_request)
    result = benchmark.run_case(case, "mock-model", "http://127.0.0.1:8000/v1", 10, "run-digest")
    assert result["case_pass"] is True
    assert result["turn_pass"] == [True] * 4
    assert history_sizes == [2, 4, 6, 8]


def test_context_materialization_inserts_distributed_facts() -> None:
    case = _base_case("context_heavy")
    case["context_spec"] = {
        "target_tokens": 8192,
        "facts": [
            {"key": "first", "value": "alpha", "position": 0.2},
            {"key": "last", "value": "omega", "position": 0.8},
        ],
        "distractors": ["not evidence"],
    }
    prompt = benchmark.user_text(case, 0)
    assert prompt.count("FACT first = alpha") == 1
    assert prompt.count("FACT last = omega") == 1
    assert prompt.index("FACT first") < prompt.index("FACT last")
    assert prompt.endswith("Question: Return value=ok.")


def test_save_fsync_and_reject_corrupt_or_duplicate_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "records.jsonl"
    calls: list[int] = []
    monkeypatch.setattr(benchmark.os, "fsync", lambda fd: calls.append(fd))
    benchmark.save_record(path, {"id": "one", "case_pass": True})
    assert len(calls) == 2
    assert benchmark.load_records(path)[0]["case_pass"] is True
    with path.open("a", encoding="utf-8") as output:
        output.write('{"id":"two"')
    with pytest.raises(ValueError, match="incomplete"):
        benchmark.load_records(path)
    path.write_text('{"id":"one"}\n{"id":"one"}\n')
    with pytest.raises(ValueError, match="duplicate"):
        benchmark.load_records(path)


def test_stream_parser_records_first_token_and_usage() -> None:
    stream = io.BytesIO(
        b'data: {"choices":[{"delta":{"content":"{\\"a\\":1}"},"finish_reason":"stop"}]}\n\n'
        b'data: {"choices":[],"usage":{"prompt_tokens":5,"completion_tokens":3}}\n\n'
        b'data: [DONE]\n\n'
    )
    result = benchmark.parse_stream(stream, 0.0)
    assert result["content"] == '{"a":1}'
    assert result["usage"] == {"prompt_tokens": 5, "completion_tokens": 3}
    assert result["ttft_s"] is not None


def test_resume_preserves_bounded_tool_loop_failure_and_runs_next_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = [_base_case("multi_tool"), {**_base_case("multi_tool"), "id": "fixture-2"}]
    output = tmp_path / "records.jsonl"
    args = argparse.Namespace(
        cases=tmp_path / "cases.json", bucket=None, ids=None, limit=None,
        model="mock-model", base_url="http://127.0.0.1:8000/v1", output=output,
        run_label="test engine", timeout=10,
    )
    run_id = benchmark.digest({
        "version": benchmark.RUNNER_VERSION, "model": args.model,
        "base_url": args.base_url, "run_label": args.run_label,
        "temperature": 0, "top_p": 1, "thinking": False,
    })
    benchmark.save_record(output, {
        "id": cases[0]["id"], "case_sha256": benchmark.digest(cases[0]),
        "run_sha256": run_id, "case_pass": False,
        "error": benchmark.BOUNDED_TOOL_LOOP_ERROR,
    })
    monkeypatch.setattr(benchmark, "load_cases", lambda *_args: cases)
    monkeypatch.setattr(benchmark, "verify_model", lambda *_args: None)
    called: list[str] = []

    def fake_run_case(case: dict, *_args: object) -> dict:
        called.append(case["id"])
        return {
            "id": case["id"], "case_sha256": benchmark.digest(case),
            "run_sha256": run_id, "case_pass": True, "error": None, "wall_s": 0.1,
        }

    monkeypatch.setattr(benchmark, "run_case", fake_run_case)
    benchmark.run(args)
    assert called == ["fixture-2"]
    records = benchmark.load_records(output)
    assert len(records) == 2
    assert records[0]["error"] == benchmark.BOUNDED_TOOL_LOOP_ERROR
    assert records[1]["case_pass"] is True
