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


def _metric_snapshot(count: int, prefill: float, decode: float, ttft: float,
                     prompt: int, generated: int) -> dict:
    values = [prefill, decode, ttft, prompt, generated]
    return {f"{name}_{suffix}": (count if suffix == "count" else value)
            for name, value in zip(benchmark.SERVER_METRICS, values)
            for suffix in ("sum", "count")}


def test_server_phase_rates_exclude_queue_and_first_generated_token() -> None:
    before = _metric_snapshot(2, 3.0, 4.0, 5.0, 100, 20)
    after = _metric_snapshot(3, 3.5, 6.0, 5.8, 1100, 121)
    metrics = benchmark.server_metric_delta(before, after)
    assert metrics["available"]
    assert metrics["prefill_tps"] == 2000
    assert metrics["decode_tps"] == 50
    assert metrics["ttft_s"] == pytest.approx(0.8)
    assert metrics["prefill_s"] == 0.5


def test_vllm_prefill_rate_uses_computed_tokens_when_prefix_is_cached() -> None:
    before = _metric_snapshot(2, 3, 4, 5, 100, 20)
    after = _metric_snapshot(3, 3.5, 6, 5.8, 1100, 121)
    before.update(request_prefill_kv_computed_tokens_count=2,
                  request_prefill_kv_computed_tokens_sum=100)
    after.update(request_prefill_kv_computed_tokens_count=3,
                 request_prefill_kv_computed_tokens_sum=200)
    result = benchmark.server_metric_delta(before, after)
    assert result["prompt_tokens"] == 1000
    assert result["processed_prompt_tokens"] == 100
    assert result["prefill_tps"] == 200


@pytest.mark.parametrize("count", [2, 4])
def test_server_metrics_reject_missing_or_concurrent_requests(count: int) -> None:
    before = _metric_snapshot(2, 3, 4, 5, 100, 20)
    after = _metric_snapshot(count, 4, 5, 6, 1100, 121)
    assert not benchmark.server_metric_delta(before, after)["available"]
    assert not benchmark.server_metric_delta(before, {})["available"]


def test_prometheus_histogram_parser_sums_engine_labels() -> None:
    parsed = benchmark.parse_server_metrics('''# irrelevant comment
vllm:request_prefill_time_seconds_sum{engine="0",model_name="local"} 2.5
vllm:request_prefill_time_seconds_sum{engine="1",model_name="local"} 1e-1
vllm:request_prefill_time_seconds_count{engine="0"} 1
vllm:request_prefill_time_seconds_bucket{le="2"} 9
''')
    assert parsed == {"request_prefill_time_seconds_sum": 2.6,
                      "request_prefill_time_seconds_count": 1.0}


def test_client_rates_do_not_invent_nonstreaming_ttft() -> None:
    assert benchmark.client_rates(_response())["decode_tps_estimate"] is None
    response = {**_response(), "ttft_s": 0.25, "wall_s": 0.75}
    assert benchmark.client_rates(response)["decode_tps_estimate"] == 4


def test_metrics_export_failure_preserves_valid_task_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benchmark, "request_completion", lambda *_args: _response('{"value":"ok"}'))

    def unavailable(_url: str) -> dict:
        raise OSError("exporter unavailable")

    monkeypatch.setattr(benchmark, "fetch_server_metrics", unavailable)
    record = benchmark.run_case(_base_case(), "mock", "http://local/v1", 10, "run", "http://local/metrics")
    assert record["case_pass"]
    assert record["error"] is None
    assert not record["trace"][0]["performance"]["server"]["available"]


def test_stream_keeps_native_phase_timings_and_cached_prompt_work() -> None:
    timings = {"prompt_n": 8, "cache_n": 92, "prompt_ms": 200,
               "predicted_n": 5, "predicted_ms": 400,
               "prompt_per_second": 40, "predicted_per_second": 10}
    stream = io.BytesIO(('data: '+json.dumps({"choices": [], "timings": timings,
                                             "usage": {"prompt_tokens": 100, "completion_tokens": 5}})+'\n\ndata: [DONE]\n').encode())
    response = benchmark.parse_stream(stream, 0)
    measured = benchmark.native_server_rates(response)
    assert measured["available"]
    assert measured["prompt_tokens"] == 100
    assert measured["processed_prompt_tokens"] == 8
    assert measured["cached_prompt_tokens"] == 92
    assert measured["prefill_tps"] == 40
    assert measured["decode_tps"] == 10
    assert measured["ttft_s"] is None


def test_telemetry_collection_is_excluded_from_case_latency(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [0.0]
    monkeypatch.setattr(benchmark.time, "monotonic", lambda: clock[0])

    def snapshot(_url: str) -> dict:
        clock[0] += 4
        return {}

    def collect(_url: str, _before: dict) -> dict:
        clock[0] += 4
        return {"available": False, "reason": "fixture"}

    def response(*_args: object) -> dict:
        clock[0] += 2
        return {**_response('{"value":"ok"}'), "wall_s": 2}

    monkeypatch.setattr(benchmark, "fetch_server_metrics", snapshot)
    monkeypatch.setattr(benchmark, "collect_server_metrics", collect)
    monkeypatch.setattr(benchmark, "request_completion", response)
    record = benchmark.run_case(_base_case(), "mock", "http://local/v1", 10, "run", "http://local/metrics")
    assert record["wall_s"] == 2
    assert record["telemetry_wall_s"] == 8


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
