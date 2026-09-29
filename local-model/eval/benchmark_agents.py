#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Run a small, reproducible agent-task benchmark against a local OpenAI API."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Sequence


DEFAULT_CASES = Path(__file__).with_name("agent_cases.json")


def load_cases(path: Path) -> list[dict[str, Any]]:
    """Load and validate the version-controlled, synthetic task fixture."""
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a non-empty JSON array")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            raise ValueError("every case needs a string id")
        if case["id"] in seen:
            raise ValueError(f"duplicate case id: {case['id']}")
        seen.add(case["id"])
        if any(key not in case for key in ("workflow", "system", "user", "max_tokens", "thinking")):
            raise ValueError(f"case {case['id']} lacks required fields")
        if case.get("kind") not in {"text", "tool", "vision", "long"}:
            raise ValueError(f"invalid kind for {case['id']}")
        if case["kind"] == "tool":
            if not case.get("tool") or not case.get("expected_tool"):
                raise ValueError(f"tool case {case['id']} lacks a tool or expectation")
        elif not case.get("rubric"):
            raise ValueError(f"case {case['id']} lacks a rubric")
    return cases


def case_digest(case: dict[str, Any]) -> str:
    """Record fixture identity so results cannot silently mix prompt revisions."""
    return hashlib.sha256(
        json.dumps(case, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def long_context_prompt() -> str:
    """Build a roughly 20K-token mock operations note with one central answer."""
    filler = (
        "Operations note: the agent queue was healthy, the browser worker had "
        "normal CPU use, and the Telegram delivery path did not drop messages. "
        "These observations were routine checks, not a diagnosed regression.\n"
    )
    needle = (
        "WEEK THREE FINDING: The named cause of the agent latency regression "
        "was prefix-cache invalidation after tool calls.\n"
    )
    return filler * 250 + needle + filler * 250 + (
        "Question: What was the named cause of the week-three agent latency "
        "regression? Answer in one sentence."
    )


def chart_data_url() -> str:
    """Create a deterministic chart in memory without storing an image asset."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (480, 320), "white")
    draw = ImageDraw.Draw(image)
    draw.line((40, 270, 445, 270), fill="black", width=3)
    bars = (("A", 60, 170, "red"), ("B", 190, 75, "blue"), ("C", 320, 130, "green"))
    for label, left, top, color in bars:
        draw.rectangle((left, top, left + 75, 269), fill=color)
        draw.text((left + 30, 283), label, fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def messages_for(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the same messages for either model, including the fixed vision cue."""
    user: Any = case["user"]
    if case["kind"] == "long":
        user = long_context_prompt()
    elif case["kind"] == "vision":
        user = [
            {"type": "text", "text": case["user"]},
            {"type": "image_url", "image_url": {"url": chart_data_url()}},
        ]
    return [{"role": "system", "content": case["system"]}, {"role": "user", "content": user}]


def request_payload(case: dict[str, Any], model: str) -> dict[str, Any]:
    """Pin sampling and output cap; let tool choice remain a capability test."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages_for(case),
        "temperature": 0,
        "max_tokens": case["max_tokens"],
        "chat_template_kwargs": {"enable_thinking": case["thinking"]},
        "stream": case["kind"] != "tool",
    }
    if case["kind"] == "tool":
        payload["tools"] = [case["tool"]]
        payload["tool_choice"] = "auto"
    else:
        payload["stream_options"] = {"include_usage": True}
    return payload


def parse_sse(lines: Any, start: float) -> dict[str, Any]:
    """Collect OpenAI-compatible stream chunks and time the first output token."""
    content: list[str] = []
    reasoning: list[str] = []
    tool_calls: dict[int, dict[str, Any]] = {}
    usage: dict[str, Any] = {}
    first_token: float | None = None
    finish_reason: str | None = None
    for raw in lines:
        line = raw.decode("utf-8").strip()
        if not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            break
        chunk = json.loads(data)
        if chunk.get("usage"):
            usage = chunk["usage"]
        for choice in chunk.get("choices", []):
            finish_reason = choice.get("finish_reason") or finish_reason
            delta = choice.get("delta") or {}
            text = delta.get("content") or ""
            thought = delta.get("reasoning_content") or ""
            if text or thought or delta.get("tool_calls"):
                first_token = first_token or time.monotonic()
            content.append(text)
            reasoning.append(thought)
            for call in delta.get("tool_calls") or []:
                item = tool_calls.setdefault(call["index"], {"function": {"name": "", "arguments": ""}})
                function = call.get("function") or {}
                item["function"]["name"] += function.get("name") or ""
                item["function"]["arguments"] += function.get("arguments") or ""
    return {
        "output_text": "".join(content),
        "reasoning_chars": sum(map(len, reasoning)),
        "tool_calls": list(tool_calls.values()),
        "usage": usage,
        "finish_reason": finish_reason,
        "ttft_s": None if first_token is None else round(first_token - start, 3),
    }


def run_case(case: dict[str, Any], model: str, base_url: str, timeout: int) -> dict[str, Any]:
    """Run one sample and retain raw answer, usage, and comparable wall timings."""
    payload = request_payload(case, model)
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.monotonic()
    record: dict[str, Any] = {
        "id": case["id"],
        "workflow": case["workflow"],
        "kind": case["kind"],
        "model": model,
        "case_sha256": case_digest(case),
    }
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if payload["stream"]:
                record.update(parse_sse(response, start))
            else:
                body = json.load(response)
                message = body["choices"][0]["message"]
                record.update(
                    output_text=message.get("content") or "",
                    reasoning_chars=len(message.get("reasoning_content") or ""),
                    tool_calls=message.get("tool_calls") or [],
                    usage=body.get("usage") or {},
                    finish_reason=body["choices"][0].get("finish_reason"),
                    ttft_s=None,
                )
                if body.get("timings"):
                    record["server_timings"] = body["timings"]
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    record["wall_s"] = round(time.monotonic() - start, 3)
    tokens = record.get("usage", {}).get("completion_tokens")
    ttft = record.get("ttft_s")
    if isinstance(tokens, int) and ttft is not None and record["wall_s"] > ttft:
        record["decode_tok_s"] = round(max(tokens - 1, 0) / (record["wall_s"] - ttft), 2)
    return record


def tool_success(case: dict[str, Any], record: dict[str, Any]) -> bool:
    """Compare parsed function name and arguments, not JSON character order."""
    expected = case["expected_tool"]
    calls = record.get("tool_calls") or []
    if len(calls) != 1:
        return False
    function = calls[0].get("function") or {}
    try:
        arguments = json.loads(function.get("arguments") or "{}")
    except json.JSONDecodeError:
        return False
    return function.get("name") == expected["name"] and arguments == expected["arguments"]


def load_records(path: Path) -> list[dict[str, Any]]:
    """Read JSONL results without treating generated text as instructions."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def save_record(path: Path, record: dict[str, Any]) -> None:
    """Append one completed result to an ignored runtime JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, ensure_ascii=False) + "\n")


def run(args: argparse.Namespace) -> None:
    """Run the fixture sequentially to avoid contention in timing comparisons."""
    cases = load_cases(args.cases)
    if args.ids:
        wanted = set(args.ids.split(","))
        cases = [case for case in cases if case["id"] in wanted]
        if len(cases) != len(wanted):
            raise ValueError("one or more requested case ids are unknown")
    if args.limit:
        cases = cases[: args.limit]
    completed = {record["id"]: record for record in load_records(args.output)} if args.output.exists() else {}
    for case in cases:
        if case["id"] in completed:
            previous = completed[case["id"]]
            if previous["model"] != args.model or previous["case_sha256"] != case_digest(case):
                raise ValueError(f"existing result is for a different model or case revision: {case['id']}")
            print(f"skip {case['id']}: already recorded", flush=True)
            continue
        record = run_case(case, args.model, args.base_url, args.timeout)
        if case["kind"] == "tool":
            record["tool_success"] = tool_success(case, record)
        save_record(args.output, record)
        status = "ERROR" if record.get("error") else "OK"
        print(f"{case['id']}: {status}, {record['wall_s']:.2f}s, {record.get('usage', {}).get('completion_tokens', '?')} tokens", flush=True)


def blind(args: argparse.Namespace) -> None:
    """Make a model-name-free grading bundle and a separate sealed mapping."""
    cases = load_cases(args.cases)
    left = {record["id"]: record for record in load_records(args.left)}
    right = {record["id"]: record for record in load_records(args.right)}
    bundle: list[dict[str, Any]] = []
    mapping: dict[str, Any] = {}
    for case in cases:
        case_id = case["id"]
        if case["kind"] == "tool" or case_id not in left or case_id not in right:
            continue
        if left[case_id]["case_sha256"] != case_digest(case) or right[case_id]["case_sha256"] != case_digest(case):
            raise ValueError(f"fixture changed after recording {case_id}")
        swap = hashlib.sha256((args.salt + case_id).encode()).digest()[0] % 2 == 1
        a, b = (right[case_id], left[case_id]) if swap else (left[case_id], right[case_id])
        bundle.append({
            "id": case_id,
            "workflow": case["workflow"],
            "system": case["system"],
            "user": case["user"],
            "rubric": case["rubric"],
            "A": a.get("output_text", ""),
            "B": b.get("output_text", ""),
        })
        mapping[case_id] = {"A": a["model"], "B": b["model"]}
    args.bundle.parent.mkdir(parents=True, exist_ok=True)
    args.mapping.parent.mkdir(parents=True, exist_ok=True)
    args.bundle.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.mapping.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"blinded {len(bundle)} cases; do not open {args.mapping} until grading is saved")


def summarize(args: argparse.Namespace) -> None:
    """Aggregate speed and audited rubric decisions after blinding is broken."""
    cases = {case["id"]: case for case in load_cases(args.cases)}
    mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
    judgments = json.loads(args.judgments.read_text(encoding="utf-8"))
    records = load_records(args.left) + load_records(args.right)
    by_model: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if record["case_sha256"] != case_digest(cases[record["id"]]):
            raise ValueError(f"fixture mismatch for {record['id']}")
        by_model.setdefault(record["model"], []).append(record)
    for model, items in by_model.items():
        quality: list[int] = []
        tool_results: list[bool] = []
        ttfts: list[float] = []
        decodes: list[float] = []
        for item in items:
            case_id = item["id"]
            if item["kind"] == "tool":
                tool_results.append(item.get("tool_success", False))
            else:
                label = next(label for label in ("A", "B") if mapping[case_id][label] == model)
                marks = judgments[case_id][label]
                if len(marks) != len(cases[case_id]["rubric"]) or any(mark not in (0, 1) for mark in marks):
                    raise ValueError(f"invalid rubric marks for {case_id}/{label}")
                quality.extend(marks)
            if isinstance(item.get("ttft_s"), (int, float)):
                ttfts.append(item["ttft_s"])
            if isinstance(item.get("decode_tok_s"), (int, float)):
                decodes.append(item["decode_tok_s"])
        print(json.dumps({
            "model": model,
            "cases": len(items),
            "rubric_pass": f"{sum(quality)}/{len(quality)}",
            "tool_success": f"{sum(tool_results)}/{len(tool_results)}",
            "median_wall_s": round(statistics.median(item["wall_s"] for item in items), 2),
            "median_ttft_s": round(statistics.median(ttfts), 2) if ttfts else None,
            "median_decode_tok_s": round(statistics.median(decodes), 2) if decodes else None,
            "failures": [item["id"] for item in items if item.get("error")],
        }, ensure_ascii=False))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Keep endpoint, model, and runtime paths explicit for safe model switching."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    runner = sub.add_parser("run")
    runner.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    runner.add_argument("--model", required=True)
    runner.add_argument("--base-url", default="http://127.0.0.1:8003/v1")
    runner.add_argument("--output", required=True, type=Path)
    runner.add_argument("--timeout", type=int, default=300)
    runner.add_argument("--ids", help="Comma-separated case ids")
    runner.add_argument("--limit", type=int)
    blinded = sub.add_parser("blind")
    blinded.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    blinded.add_argument("--left", type=Path, required=True)
    blinded.add_argument("--right", type=Path, required=True)
    blinded.add_argument("--bundle", type=Path, required=True)
    blinded.add_argument("--mapping", type=Path, required=True)
    blinded.add_argument("--salt", required=True)
    summary = sub.add_parser("summarize")
    summary.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    summary.add_argument("--left", type=Path, required=True)
    summary.add_argument("--right", type=Path, required=True)
    summary.add_argument("--mapping", type=Path, required=True)
    summary.add_argument("--judgments", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "run":
        run(args)
    elif args.command == "blind":
        blind(args)
    else:
        summarize(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
