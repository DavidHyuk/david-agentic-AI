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
