# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Ensure visible TTFT cannot be mistaken for the first hidden reasoning token."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

directory = Path(__file__).resolve().parents[1] / "local-model/eval"
sys.path.insert(0, str(directory))
spec = importlib.util.spec_from_file_location("leetcode_benchmark", directory / "leetcode_latency.py")
benchmark = importlib.util.module_from_spec(spec);spec.loader.exec_module(benchmark)


def test_visible_text_waits_for_split_thinking_close(monkeypatch):
    stamps = iter([1, 2, 3, 4])
    monkeypatch.setattr(benchmark.time, 'monotonic', lambda: next(stamps))
    lines = ['data: ' + json.dumps(value) for value in [
        {'content':'hidden'}, {'content':'</thi'}, {'content':'nk>\n'},
        {'content':'힌트'}, {'stop':True,'timings':{'predicted_n':4}}]]
    text, raw, visible, final = benchmark.parse(lines, 0, True)
    assert text == '힌트' and raw == 1 and visible == 4
    assert final['timings']['predicted_n'] == 4


def test_missing_visible_answer_or_final_is_not_success():
    assert benchmark.visible('hidden without closing tag', True) == ''
    assert benchmark.visible('answer', False) == 'answer'
    with pytest.raises(RuntimeError, match='authoritative'):
        benchmark.parse(['data: {"content":"partial"}'], 0, False)


def test_concurrent_replay_keeps_distinct_cloud_trace_and_score_ids(monkeypatch):
    import io
    import urllib.request
    import experiment_tracker as tracker
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: io.BytesIO())
    timings = {'prompt_n': 10, 'cache_n': 0, 'predicted_n': 5,
               'prompt_ms': 100, 'predicted_ms': 200,
               'prompt_per_second': 100, 'predicted_per_second': 25}
    monkeypatch.setattr(benchmark, 'parse', lambda *a, **k:
        ('힌트', .2, .2, {'timings': timings}))
    rows = [benchmark.request('prompt', benchmark.QUESTIONS[0], 0, 'cold', slot, concurrency)[0]
            for concurrency, slot in [(1, 0), (2, 0), (2, 1)]]
    payload = tracker.langfuse_payload([{'run_id': 'fixture', 'source': 'fixture',
        'label': 'fixture', 'model': 'fixture', 'records': rows}])
    spans = payload['resourceSpans'][0]['scopeSpans'][0]['spans']
    assert len({s['traceId'] for s in spans}) == 3
    scores = tracker.langfuse_scores([{'records': rows}], payload)
    assert len({s['body']['id'] for s in scores['batch']}) == len(scores['batch'])
