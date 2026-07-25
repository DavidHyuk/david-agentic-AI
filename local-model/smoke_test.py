#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Smoke-test the local vLLM endpoint and Qwen tool-calling response shape."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from typing import Any, Sequence


def request_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: int = 180,
) -> dict[str, Any]:
    """Send a JSON request using only the Python standard library."""
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError(f"request failed for {url}: {exc}") from exc


def validate_model_listing(response: dict[str, Any], expected_model: str) -> None:
    """Require the expected served model ID in a /v1/models response."""
    model_ids = {
        item.get("id")
        for item in response.get("data", [])
        if isinstance(item, dict)
    }
    if expected_model not in model_ids:
        raise ValueError(
            f"expected model {expected_model!r}; endpoint returned {sorted(model_ids)}"
        )


def validate_tool_call(
    response: dict[str, Any],
    *,
    expected_name: str,
    expected_arguments: dict[str, Any],
) -> None:
    """Require a valid OpenAI-style function call with matching arguments."""
    try:
        calls = response["choices"][0]["message"]["tool_calls"]
        function = calls[0]["function"]
        arguments = json.loads(function["arguments"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("response does not contain a valid tool call") from exc

    if function.get("name") != expected_name:
        raise ValueError(
            f"expected tool {expected_name!r}; got {function.get('name')!r}"
        )
    if arguments != expected_arguments:
        raise ValueError(
            f"expected arguments {expected_arguments!r}; got {arguments!r}"
        )


def run_smoke_test(base_url: str, model: str, timeout: int = 180) -> None:
    """Check model discovery and a deterministic forced tool call."""
    base_url = base_url.rstrip("/")
    models = request_json(f"{base_url}/models", timeout=timeout)
    validate_model_listing(models, model)
    print(f"Model endpoint OK: {model}")

    response = request_json(
        f"{base_url}/chat/completions",
        timeout=timeout,
        payload={
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": "Use the weather tool to get the weather in Seoul.",
                }
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get weather for a city",
                        "parameters": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"],
                        },
                    },
                }
            ],
            "tool_choice": {
                "type": "function",
                "function": {"name": "get_weather"},
            },
            "max_tokens": 256,
            "temperature": 0,
        },
    )
    validate_tool_call(
        response,
        expected_name="get_weather",
        expected_arguments={"city": "Seoul"},
    )
    print("Tool calling OK: get_weather(city='Seoul')")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8003/v1")
    parser.add_argument("--model", default="Qwen3.6-35B-A3B-FP8")
    parser.add_argument("--timeout", type=int, default=180)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        run_smoke_test(args.base_url, args.model, args.timeout)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
