# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Check cache accounting, log attribution, privacy, and historical export times."""
import importlib.util
import io
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1] / "local-model" / "eval"


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


latency = load("interactive_latency")
tracker = load("experiment_tracker")


def record(started=True):
    row = {"id": "one", "case": "coding_hint", "workflow": "coding", "phase": "cold",
        "concurrency": 1, "prompt": "PRIVATE PROMPT", "output_text": "PRIVATE ANSWER",
        "metrics": {"ttft_s": 2, "wall_s": 5, "full_input_tokens": 16000, "output_tokens": 90,
                    "prompt": "PRIVATE PROMPT"}, "telemetry": {"min_available_gib": 33, "private_path": "PRIVATE PATH"}}
    if started:
        row.update(started_at="2026-10-03T22:00:00+00:00", completed_at="2026-10-03T22:00:05+00:00")
    return {"run_id": "run-one", "label": "baseline", "source": "synthetic_coaching_api",
        "model": "test-model", "dataset_digest": "local-fixture", "mtp": "off",
        "context_per_request": 131072, "slots": 2, "records": [row]}


def attrs(span):
    return {a["key"]: next(iter(a["value"].values())) for a in span["attributes"]}


def test_cache_tokens_are_not_prefill_tokens():
    t = {"prompt_n": 40, "cache_n": 16000, "prompt_ms": 200, "predicted_n": 101,
         "predicted_ms": 4000, "predicted_per_second": 25}
    m = latency.metrics_from_timings(t, 0.3, 4.3)
    assert m["full_input_tokens"] == 16040
    assert m["processed_input_tokens"] == 40
    assert m["cached_input_tokens"] == 16000
    assert m["prefill_s"] == 0.2
    assert m["client_decode_tps"] == pytest.approx(25)


def test_ttft_ignores_empty_events_and_keeps_final_timings(monkeypatch):
    clock = iter([12.0])
    monkeypatch.setattr(latency.time, "monotonic", lambda: next(clock))
    lines = [b'data: {"content":""}\n', b'data: {"content":"hello"}\n',
             b'data: {"stop":true,"timings":{"prompt_n":40}}\n']
    text, first, final = latency.parse_stream(lines, 10)
    assert text == "hello" and first == 2
    assert final["timings"]["prompt_n"] == 40


def test_incomplete_or_error_stream_is_not_success():
    with pytest.raises(RuntimeError, match="missing"):
        latency.parse_stream([], 0)
    with pytest.raises(RuntimeError, match="stream error"):
        latency.parse_stream([b'data: {"error":"PRIVATE ERROR"}'], 0)


def test_export_discards_original_prompts_and_paths():
    clean = tracker.sanitize(record())
    payload = json.dumps(tracker.langfuse_payload([clean]))
    assert "PRIVATE" not in payload
    span = tracker.langfuse_payload([clean])["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    values = attrs(span)
    assert values["langfuse.observation.type"] == "generation"
    assert values["langfuse.observation.completion_start_time"] == "2026-10-03T22:00:02+00:00"
    assert values["langfuse.trace.public"] is False
    assert values["langfuse.experiment.item.root_observation_id"] == span["spanId"]


def test_historical_measurements_do_not_invent_generation_times():
    payload = tracker.langfuse_payload([tracker.sanitize(record(False))])
    span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    values = attrs(span)
    assert values["langfuse.observation.type"] == "span"
    assert values["langfuse.observation.metadata.historical_import"] is True
    assert "langfuse.observation.completion_start_time" not in values
    assert span["startTimeUnixNano"] == span["endTimeUnixNano"]


def test_duplicate_import_is_rejected(tmp_path):
    path = tmp_path / "data.json"
    path.write_text(json.dumps([record(), record()]))
    with pytest.raises(ValueError, match="duplicate"):
        tracker.load_runs([path])


def test_cached_journal_total_does_not_hide_existing_context():
    def event(tail, pid="123"):
        return json.dumps({"_PID": pid, "__REALTIME_TIMESTAMP": "1791064800000000",
            "MESSAGE": "slot print_timing: id 0 | task 2 | " + tail})
    lines = [event("prompt eval time = 200.00 ms / 40 tokens (5.00 ms per token, 200.00 tokens per second)"),
        event("eval time = 4000.00 ms / 101 tokens (40.00 ms per token, 25.00 tokens per second)"),
        event("total time = 4200.00 ms / 141 tokens"),
        event("stop processing: n_tokens = 16140, truncated = 0"),
        event("stop processing: n_tokens = 99999, truncated = 0", "OTHER-PID")]
    rows = tracker.parse_journal(lines, pid="123")
    assert len(rows) == 1
    assert rows[0]["metrics"]["full_input_tokens"] == 16040
    assert rows[0]["metrics"]["cached_input_tokens"] == 16000
    assert rows[0]["metrics"]["ttft_s"] is None
    assert rows[0]["metrics"]["wall_s"] is None


def test_dashboard_escapes_script_delimiters(tmp_path):
    from argparse import Namespace
    run = record()
    run["label"] = '</script><script>alert("private")</script>'
    source, output = tmp_path / "source.json", tmp_path / "report.html"
    source.write_text(json.dumps(run))
    tracker.report(Namespace(input=[source], output=output))
    html = output.read_text()
    assert run["label"] not in html
    assert "__EXPERIMENT_DATA__" not in html
    assert "\\u003c/script>" in html


def test_langfuse_dry_run_needs_no_credentials_and_makes_no_network_calls(tmp_path, monkeypatch):
    from argparse import Namespace
    monkeypatch.setattr(tracker.urllib.request, "urlopen", lambda *a, **kw: pytest.fail("network used"))
    source, output = tmp_path / "source.json", tmp_path / "otlp.json"
    source.write_text(json.dumps(record()))
    tracker.publish_langfuse(Namespace(input=[source], dry_run=output))
    assert json.loads(output.read_text())["resourceSpans"]


def test_output_cap_uses_token_count_when_stop_flag_is_false(monkeypatch):
    final = {"timings": {"prompt_n": 40, "cache_n": 16000, "prompt_ms": 200,
        "predicted_n": 256, "predicted_ms": 10000}, "stopped_limit": False}
    monkeypatch.setattr(latency.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO())
    monkeypatch.setattr(latency, "parse_stream", lambda *a: ("설명", .3, final))
    row, _ = latency.request("http://unused", "synthetic", latency.CASES[0], 0, "warm_followup", 0)
    assert row["quality"]["output_limit_reached"] is True


@pytest.mark.parametrize("phase,cache,error", [("cold", 100, "unexpectedly"), ("warm_followup", 0, "lost")])
def test_phase_rejects_contradicting_cache_timings(monkeypatch, phase, cache, error):
    final = {"timings": {"prompt_n": 40, "cache_n": cache, "predicted_n": 1}}
    monkeypatch.setattr(latency.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO())
    monkeypatch.setattr(latency, "parse_stream", lambda *a: ("reply", .3, final))
    with pytest.raises(RuntimeError, match=error):
        latency.request("http://unused", "synthetic", latency.CASES[0], 0, phase, 0)


def test_langsmith_export_has_real_ttft_and_cache_usage(tmp_path, monkeypatch):
    import sys
    from argparse import Namespace
    from types import SimpleNamespace
    calls = []
    source = tmp_path / "source.json"
    run = record()
    run["records"][0]["metrics"]["cached_input_tokens"] = 12000
    source.write_text(json.dumps(run))
    monkeypatch.setenv("LANGSMITH_API_KEY", "fake-for-unit-test")
    client = SimpleNamespace(create_run=lambda **kwargs: calls.append(kwargs), flush=lambda: None)
    monkeypatch.setitem(sys.modules, "langsmith", SimpleNamespace(Client=lambda: client))
    tracker.publish_langsmith(Namespace(input=[source], project="test"))
    assert len(calls) == 1
    assert calls[0]["events"][0]["time"] == "2026-10-03T22:00:02+00:00"
    assert calls[0]["outputs"]["usage_metadata"]["input_token_details"]["cache_read"] == 12000
    assert "PRIVATE" not in json.dumps(calls, default=str)


def test_credentials_file_is_private_and_never_executes_values(tmp_path, monkeypatch, capsys):
    from argparse import Namespace
    path = tmp_path / 'langfuse.env'
    path.write_text('LANGFUSE_BASE_URL=https://us.cloud.langfuse.com\n'
                    'LANGFUSE_PUBLIC_KEY=FAKE_PUBLIC\nLANGFUSE_SECRET_KEY="$(PRIVATE_SECRET)"\n')
    path.chmod(0o644)
    with pytest.raises(ValueError, match='private'):
        tracker.langfuse_credentials(path)
    path.chmod(0o600)
    assert tracker.langfuse_credentials(path)['LANGFUSE_SECRET_KEY'] == '$(PRIVATE_SECRET)'
    tracker.status_langfuse(Namespace(credentials=path))
    output = capsys.readouterr().out
    assert 'PRIVATE_SECRET' not in output and 'FAKE_PUBLIC' not in output
    assert json.loads(output)['configured'] is True


def test_performance_scores_attach_to_item_root_with_stable_recording_times():
    run = tracker.sanitize(record(False))
    run['recorded_at'] = '2026-10-03T22:01:00+00:00'
    first = tracker.langfuse_scores([run], tracker.langfuse_payload([run]))
    second = tracker.langfuse_scores([run], tracker.langfuse_payload([run]))
    assert first == second
    assert {e['body']['name'] for e in first['batch']} == {'ttft_s','wall_s','min_available_gib'}
    assert all(e['timestamp'] == run['recorded_at'] for e in first['batch'])
    assert all(e['body']['observationId'] for e in first['batch'])
    assert 'PRIVATE' not in json.dumps(first)


def test_score_rejection_is_not_reported_as_success(tmp_path, monkeypatch):
    from argparse import Namespace
    source = tmp_path / 'run.json'; source.write_text(json.dumps(record()))
    for name,value in [('LANGFUSE_BASE_URL','https://test.example'),
                       ('LANGFUSE_PUBLIC_KEY','fake-public'),('LANGFUSE_SECRET_KEY','fake-secret')]:
        monkeypatch.setenv(name,value)
    replies = iter([{}, {'successes': [], 'errors': [{'message': 'PRIVATE SERVER ERROR'}]}])
    monkeypatch.setattr(tracker.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(json.dumps(next(replies)).encode()))
    with pytest.raises(RuntimeError, match='rejected performance') as error:
        tracker.publish_langfuse(Namespace(input=[source],dry_run=None,credentials=None))
    assert 'PRIVATE SERVER ERROR' not in str(error.value)


def test_experiment_import_rejects_duplicate_item_ids(tmp_path):
    run = record()
    run['records'].append(dict(run['records'][0]))
    path = tmp_path / 'duplicate.json'
    path.write_text(json.dumps(run))
    with pytest.raises(ValueError, match='duplicate experiment items'):
        tracker.load_runs([path])
