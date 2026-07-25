# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for the standalone vLLM readiness gate."""
from __future__ import annotations

import wait_for_vllm as wait


def test_response_has_expected_model():
    payload = {"data": [{"id": "Qwen3.6-35B-A3B-FP8"}]}

    assert wait.response_has_model(payload, "Qwen3.6-35B-A3B-FP8") is True
    assert wait.response_has_model(payload, "other-model") is False
    assert wait.response_has_model({"data": []}, None) is False


def test_wait_until_ready_retries_then_succeeds():
    responses = iter(
        [
            OSError("connection refused"),
            {"data": [{"id": "Qwen3.6-35B-A3B-FP8"}]},
        ]
    )
    times = iter([0.0, 0.0, 0.2, 0.2])
    sleeps: list[float] = []

    def fetch(_url, _timeout):
        result = next(responses)
        if isinstance(result, Exception):
            raise result
        return result

    ok, detail = wait.wait_until_ready(
        wait.DEFAULT_URL,
        wait.DEFAULT_MODEL,
        timeout=10,
        interval=0.2,
        fetch=fetch,
        monotonic=lambda: next(times),
        sleeper=sleeps.append,
    )

    assert ok is True
    assert "ready" in detail
    assert sleeps == [0.2]


def test_wait_until_ready_reports_timeout():
    times = iter([0.0, 0.0, 1.0])

    ok, detail = wait.wait_until_ready(
        wait.DEFAULT_URL,
        wait.DEFAULT_MODEL,
        timeout=1,
        interval=0.5,
        fetch=lambda _url, _timeout: {"data": []},
        monotonic=lambda: next(times),
        sleeper=lambda _seconds: None,
    )

    assert ok is False
    assert "expected model" in detail
