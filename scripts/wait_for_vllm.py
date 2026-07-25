#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Wait until the local vLLM model-discovery endpoint is ready.

This standalone helper is used by the Hermes gateway systemd drop-in.  It
requires a successful ``/v1/models`` response containing the configured served
model before the gateway starts, preventing scheduled jobs from racing model
startup after a reboot.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from typing import Any

DEFAULT_URL = "http://127.0.0.1:8003/v1/models"
DEFAULT_MODEL = "Qwen3.6-35B-A3B-FP8"


def response_has_model(payload: Any, expected_model: str | None) -> bool:
    """Return whether an OpenAI-compatible model list is usable."""
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return False
    model_ids = {
        str(item.get("id"))
        for item in payload["data"]
        if isinstance(item, dict) and item.get("id")
    }
    if expected_model:
        return expected_model in model_ids
    return bool(model_ids)


def fetch_models(url: str, request_timeout: float) -> Any:
    """Fetch and decode one model-discovery response."""
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=request_timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def wait_until_ready(
    url: str,
    expected_model: str | None,
    timeout: float,
    interval: float,
    *,
    fetch: Callable[[str, float], Any] = fetch_models,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> tuple[bool, str]:
    """Poll until the expected model appears or the deadline expires."""
    started = monotonic()
    last_detail = "endpoint did not return the expected model"
    while True:
        elapsed = monotonic() - started
        remaining = max(0.0, timeout - elapsed)
        try:
            payload = fetch(url, max(0.1, min(10.0, remaining or 0.1)))
            if response_has_model(payload, expected_model):
                return True, f"ready after {elapsed:.1f}s"
            last_detail = "endpoint response did not contain the expected model"
        except (
            OSError,
            RuntimeError,
            ValueError,
            json.JSONDecodeError,
            urllib.error.URLError,
        ) as exc:
            last_detail = f"{type(exc).__name__}: {exc}"

        elapsed = monotonic() - started
        if elapsed >= timeout:
            return False, last_detail
        sleeper(min(interval, max(0.0, timeout - elapsed)))


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--expected-model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--interval", type=float, default=2.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.timeout < 0 or args.interval <= 0:
        print("timeout must be >= 0 and interval must be > 0", file=sys.stderr)
        return 2
    ok, detail = wait_until_ready(
        args.url,
        args.expected_model or None,
        args.timeout,
        args.interval,
    )
    if ok:
        print(
            f"vLLM ready: {args.expected_model or 'a served model'} ({detail})",
            file=sys.stderr,
        )
        return 0
    print(f"vLLM readiness timed out: {detail}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
