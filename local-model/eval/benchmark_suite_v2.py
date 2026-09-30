#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Run a reproducible, fully synthetic four-bucket agent benchmark locally."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Sequence


DEFAULT_CASES = Path(__file__).with_name("agent_cases_v2.json")
BUCKETS = ("short_task", "multi_tool", "long_horizon", "context_heavy")
RUNNER_VERSION = "2.2"
BOUNDED_TOOL_LOOP_ERROR = "synthetic tool loop exceeded step limit"
CONTEXT_CHARS_PER_TARGET_TOKEN = 3.7
FILLER = (
    "Archive note: queue healthy, browser idle, delivery confirmed; "
    "this routine observation is not a diagnosed regression.\n"
)


def digest(value: Any) -> str:
    """Hash canonical JSON for prompt and run-configuration identity."""
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_expectation(expected: Any) -> None:
    """Reject malformed scorer operators before starting a model run."""
    if isinstance(expected, dict):
        operators = {key for key in expected if key.startswith("$")}
        if operators:
            if set(expected) == {"$contains"} and isinstance(expected["$contains"], str) and expected["$contains"]:
                return
            if expected == {"$language": "ko"}:
                return
            raise ValueError(f"invalid expected_json operator: {sorted(expected)}")
        for value in expected.values():
            validate_expectation(value)
    elif isinstance(expected, list):
        for value in expected:
            validate_expectation(value)


def load_cases(path: Path = DEFAULT_CASES) -> list[dict[str, Any]]:
    """Validate the compact, version-controlled synthetic scenario fixture."""
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a nonempty JSON array")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            raise ValueError("every case needs a string id")
        if case["id"] in seen:
            raise ValueError(f"duplicate case id: {case['id']}")
        seen.add(case["id"])
        if case.get("bucket") not in BUCKETS:
            raise ValueError(f"invalid bucket: {case['id']}")
        if not isinstance(case.get("workflow"), str) or not isinstance(case.get("system"), str):
            raise ValueError(f"missing workflow/system: {case['id']}")
        if not isinstance(case.get("max_tokens"), int) or not 1 <= case["max_tokens"] <= 2048:
            raise ValueError(f"invalid max_tokens: {case['id']}")
        if case.get("thinking") is not False:
            raise ValueError(f"thinking must be disabled: {case['id']}")
        turns = case.get("turns")
        if not isinstance(turns, list) or not turns:
            raise ValueError(f"missing turns: {case['id']}")
        for turn in turns:
            if not isinstance(turn, dict) or not isinstance(turn.get("user"), str):
                raise ValueError(f"invalid user turn: {case['id']}")
            if not isinstance(turn.get("expected_json"), dict) or not turn["expected_json"]:
                raise ValueError(f"missing expected_json: {case['id']}")
            validate_expectation(turn["expected_json"])
        if case["bucket"] == "short_task" and len(turns) != 1:
            raise ValueError(f"short task must have one turn: {case['id']}")
        if case["bucket"] == "multi_tool":
            tools = case.get("tools") or []
            script = case.get("tool_script") or []
            if len(turns) != 1 or len(tools) < 2 or len(script) < 2:
                raise ValueError(f"multi_tool needs one turn and >=2 synthetic tools: {case['id']}")
            names = [tool.get("function", {}).get("name") for tool in tools if isinstance(tool, dict)]
            if len(names) != len(tools) or len(set(names)) != len(names) or not all(isinstance(name, str) for name in names):
                raise ValueError(f"invalid tool declarations: {case['id']}")
            for step in script:
                if not isinstance(step, dict) or not all(key in step for key in ("name", "arguments", "result")):
                    raise ValueError(f"invalid tool script: {case['id']}")
                if step["name"] not in names or not isinstance(step["arguments"], dict):
                    raise ValueError(f"tool script names an undeclared tool: {case['id']}")
        elif case.get("tools") or case.get("tool_script"):
            raise ValueError(f"tools only belong in multi_tool: {case['id']}")
        if case["bucket"] == "long_horizon" and len(turns) < 4:
            raise ValueError(f"long_horizon needs at least four turns: {case['id']}")
        if case["bucket"] == "context_heavy":
            spec = case.get("context_spec")
            if len(turns) != 1 or not isinstance(spec, dict):
                raise ValueError(f"context_heavy needs one turn and context_spec: {case['id']}")
            if not isinstance(spec.get("target_tokens"), int) or not isinstance(spec.get("facts"), list):
                raise ValueError(f"invalid context_spec: {case['id']}")
            if len(spec["facts"]) < 2:
                raise ValueError(f"context_heavy needs distributed facts: {case['id']}")
            for fact in spec["facts"]:
                if not isinstance(fact, dict) or not all(key in fact for key in ("key", "value", "position")):
                    raise ValueError(f"invalid context fact: {case['id']}")
                if not 0 < fact["position"] < 1:
                    raise ValueError(f"invalid context fact position: {case['id']}")
            facts = {fact["key"]: fact["value"] for fact in spec["facts"]}
            if turns[0]["expected_json"] != facts:
                raise ValueError(f"context answer does not match its distributed facts: {case['id']}")
        elif case.get("context_spec"):
            raise ValueError(f"context_spec only belongs in context_heavy: {case['id']}")
    return cases


def context_notes(spec: dict[str, Any]) -> str:
    """Expand compact synthetic context with facts at reproducible positions."""
    target_chars = int(spec["target_tokens"] * CONTEXT_CHARS_PER_TARGET_TOKEN)
    filler_count = max(1, target_chars // len(FILLER))
    facts = sorted(spec["facts"], key=lambda fact: fact["position"])
    positions: dict[int, list[str]] = {}
    for fact in facts:
        index = min(filler_count - 1, max(0, round(fact["position"] * filler_count)))
        positions.setdefault(index, []).append(f"FACT {fact['key']} = {fact['value']}\n")
    distractors = spec.get("distractors") or []
    lines: list[str] = []
    for index in range(filler_count):
        lines.append(f"Record {index:05d}. {FILLER}")
        if distractors and index % 47 == 0:
            lines.append(f"Unverified note: {distractors[index % len(distractors)]}\n")
        lines.extend(positions.get(index, []))
    return "".join(lines)


def user_text(case: dict[str, Any], turn_index: int) -> str:
    """Materialize one user turn without storing large prompts in result files."""
    question = case["turns"][turn_index]["user"]
    if case["bucket"] == "context_heavy":
        return context_notes(case["context_spec"]) + "\nQuestion: " + question
    return question


def expected_subset(actual: Any, expected: Any) -> bool:
    """Check factual JSON fields, with explicit tolerance for expanded quotes."""
    if isinstance(expected, dict):
        if set(expected) == {"$contains"}:
            needle = expected["$contains"]
            if isinstance(actual, list):
                return any(expected_subset(item, expected) for item in actual)
            return isinstance(actual, str) and isinstance(needle, str) and needle.casefold() in actual.casefold()
        if set(expected) == {"$language"}:
            return expected["$language"] == "ko" and isinstance(actual, str) and bool(re.search(r"[가-힣]", actual))
        return isinstance(actual, dict) and all(
            key in actual and expected_subset(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            expected_subset(left, right) for left, right in zip(actual, expected)
        )
    if isinstance(expected, str):
        return isinstance(actual, str) and actual.strip() == expected.strip()
    if isinstance(expected, bool):
        return isinstance(actual, bool) and actual is expected
    if isinstance(expected, (int, float)):
        return isinstance(actual, (int, float)) and not isinstance(actual, bool) and actual == expected
    return actual == expected


def parse_json_answer(content: str) -> Any:
    """Accept a plain JSON object or one fenced JSON block, nothing else."""
    clean = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(\{.*\})\s*```", clean, re.DOTALL | re.IGNORECASE)
    if fenced:
        clean = fenced.group(1)
    return json.loads(clean)


def parse_stream(lines: Any, started: float) -> dict[str, Any]:
    """Collect streamed text, usage, finish reason, and first-token latency."""
    content: list[str] = []
    usage: dict[str, Any] = {}
    first_token: float | None = None
    finish_reason: str | None = None
    for raw in lines:
        line = raw.decode("utf-8").strip()
        if not line.startswith("data: "):
            continue
        item = line[6:]
        if item == "[DONE]":
            break
        chunk = json.loads(item)
        if chunk.get("usage"):
            usage = chunk["usage"]
        for choice in chunk.get("choices", []):
            delta = choice.get("delta") or {}
            piece = delta.get("content") or ""
            if piece and first_token is None:
                first_token = time.monotonic()
            content.append(piece)
            finish_reason = choice.get("finish_reason") or finish_reason
    return {
        "content": "".join(content),
        "tool_calls": [],
        "usage": usage,
        "finish_reason": finish_reason,
        "ttft_s": None if first_token is None else round(first_token - started, 3),
    }


def request_completion(
    messages: list[dict[str, Any]], case: dict[str, Any], model: str, base_url: str, timeout: int
) -> dict[str, Any]:
    """Call one OpenAI-compatible local request; never invoke a real tool."""
    has_tools = bool(case.get("tools"))
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "top_p": 1,
        "max_tokens": case["max_tokens"],
        "chat_template_kwargs": {"enable_thinking": False},
        "stream": not has_tools,
    }
    if has_tools:
        payload.update(tools=case["tools"], tool_choice="auto")
    else:
        payload["stream_options"] = {"include_usage": True}
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if payload["stream"]:
            result = parse_stream(response, started)
        else:
            body = json.load(response)
            choice = body["choices"][0]
            message = choice["message"]
            result = {
                "content": message.get("content") or "",
                "tool_calls": message.get("tool_calls") or [],
                "usage": body.get("usage") or {},
                "finish_reason": choice.get("finish_reason"),
                "ttft_s": None,
            }
    result["wall_s"] = round(time.monotonic() - started, 3)
    return result


def tool_reply(call: dict[str, Any], script: list[dict[str, Any]], index: int) -> tuple[dict[str, Any], bool]:
    """Return only a predefined synthetic fixture for the next expected call."""
    function = call.get("function") or {}
    try:
        arguments = json.loads(function.get("arguments") or "{}")
    except json.JSONDecodeError:
        arguments = None
    step = script[index] if index < len(script) else None
    correct = bool(step and function.get("name") == step["name"] and arguments == step["arguments"])
    if correct:
        return step["result"], True
    return {"error": "unexpected synthetic benchmark tool call"}, False


def run_case(case: dict[str, Any], model: str, base_url: str, timeout: int, run_id: str) -> dict[str, Any]:
    """Execute a case's turns and synthetic tool loop with a bounded trace."""
    started = time.monotonic()
    messages: list[dict[str, Any]] = [{"role": "system", "content": case["system"]}]
    trace: list[dict[str, Any]] = []
    tool_events: list[dict[str, Any]] = []
    turn_scores: list[bool] = []
    expected_script = case.get("tool_script") or []
    script_index = 0
    tool_sequence_ok = True
    error: str | None = None
    for turn_index, turn in enumerate(case["turns"]):
        messages.append({"role": "user", "content": user_text(case, turn_index)})
        final_text = ""
        final_finish: str | None = None
        for step_index in range(max(8, len(expected_script) + 3)):
            try:
                response = request_completion(messages, case, model, base_url, timeout)
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
                error = f"{type(exc).__name__}: {exc}"
                break
            trace.append({
                "turn": turn_index,
                "step": step_index,
                "wall_s": response["wall_s"],
                "ttft_s": response["ttft_s"],
                "usage": response["usage"],
                "finish_reason": response["finish_reason"],
                "content": response["content"],
                "tool_calls": response["tool_calls"],
            })
            calls = response["tool_calls"]
            if calls:
                # A dependent step cannot be chosen before the previous tool's
                # result has been observed in a separate model response.
                if len(calls) != 1:
                    tool_sequence_ok = False
                normal_calls: list[dict[str, Any]] = []
                for call in calls:
                    normal_calls.append({
                        "id": call.get("id") or f"synthetic_call_{len(trace)}_{len(normal_calls)}",
                        "type": "function",
                        "function": call.get("function") or {},
                    })
                messages.append({"role": "assistant", "content": response["content"], "tool_calls": normal_calls})
                for call in normal_calls:
                    result, correct = tool_reply(call, expected_script, script_index)
                    tool_events.append({
                        "name": call["function"].get("name"),
                        "arguments": call["function"].get("arguments"),
                        "result": result,
                        "correct": correct,
                    })
                    tool_sequence_ok = tool_sequence_ok and correct
                    if correct:
                        script_index += 1
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    })
                continue
            final_text = response["content"]
            final_finish = response["finish_reason"]
            messages.append({"role": "assistant", "content": final_text})
            break
        else:
            error = BOUNDED_TOOL_LOOP_ERROR
        if error:
            turn_scores.append(False)
            break
        try:
            parsed = parse_json_answer(final_text)
            turn_scores.append(final_finish != "length" and expected_subset(parsed, turn["expected_json"]))
        except (json.JSONDecodeError, TypeError):
            turn_scores.append(False)
    if expected_script and script_index != len(expected_script):
        tool_sequence_ok = False
    if not expected_script:
        tool_sequence_ok = True
    prompt_tokens = sum((item["usage"].get("prompt_tokens") or 0) for item in trace)
    completion_tokens = sum((item["usage"].get("completion_tokens") or 0) for item in trace)
    return {
        "id": case["id"],
        "bucket": case["bucket"],
        "workflow": case["workflow"],
        "model": model,
        "case_sha256": digest(case),
        "run_sha256": run_id,
        "turn_pass": turn_scores,
        "tool_sequence_pass": tool_sequence_ok,
        "case_pass": error is None and len(turn_scores) == len(case["turns"]) and all(turn_scores) and tool_sequence_ok,
        "error": error,
        "wall_s": round(time.monotonic() - started, 3),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "trace": trace,
        "tool_events": tool_events,
        "context_target_tokens": (case.get("context_spec") or {}).get("target_tokens"),
    }


def save_record(path: Path, record: dict[str, Any]) -> None:
    """Persist each complete JSONL row before the next GPU request."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        output.flush()
        os.fsync(output.fileno())
    directory = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def load_records(path: Path) -> list[dict[str, Any]]:
    """Reject corrupt or duplicate rows rather than silently losing results."""
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as source:
        for number, line in enumerate(source, 1):
            if not line.endswith("\n"):
                raise ValueError(f"incomplete JSONL row at {path}:{number}")
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL row at {path}:{number}") from exc
            if not isinstance(record, dict) or not isinstance(record.get("id"), str):
                raise ValueError(f"invalid record at {path}:{number}")
            if record["id"] in seen:
                raise ValueError(f"duplicate result id in {path}: {record['id']}")
            seen.add(record["id"])
            records.append(record)
    return records


def selected_cases(cases: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    """Apply reproducible bucket, ID, and smoke-test limits."""
    if args.bucket:
        cases = [case for case in cases if case["bucket"] == args.bucket]
    if args.ids:
        wanted = set(args.ids.split(","))
        cases = [case for case in cases if case["id"] in wanted]
        if len(cases) != len(wanted):
            raise ValueError("one or more requested case IDs are unknown or outside the selected bucket")
    if args.limit:
        cases = cases[: args.limit]
    return cases


def verify_model(base_url: str, model: str, timeout: int) -> None:
    """Fail closed if the local endpoint serves a different checkpoint."""
    with urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=timeout) as response:
        listed = json.load(response)
    if model not in [item.get("id") for item in listed.get("data", [])]:
        raise ValueError(f"endpoint {base_url} is not serving {model}")


def run(args: argparse.Namespace) -> None:
    """Run sequential cases with strict resume and an on-disk result per case."""
    all_cases = load_cases(args.cases)
    cases = selected_cases(all_cases, args)
    if not cases:
        raise ValueError("no selected cases")
    run_id = digest({
        "version": RUNNER_VERSION,
        "model": args.model,
        "base_url": args.base_url,
        "run_label": args.run_label,
        "temperature": 0,
        "top_p": 1,
        "thinking": False,
    })
    prior = {record["id"]: record for record in load_records(args.output)}
    by_id = {case["id"]: case for case in all_cases}
    for case_id, record in prior.items():
        if case_id not in by_id or record.get("case_sha256") != digest(by_id[case_id]):
            raise ValueError(f"fixture changed for existing result: {case_id}")
        if record.get("run_sha256") != run_id:
            raise ValueError(f"run configuration changed for existing result: {case_id}")
    verify_model(args.base_url, args.model, min(args.timeout, 10))
    for case in cases:
        previous = prior.get(case["id"])
        if previous:
            if previous.get("case_sha256") != digest(case):
                raise ValueError(f"fixture changed for existing result: {case['id']}")
            if previous.get("error") and previous["error"] != BOUNDED_TOOL_LOOP_ERROR:
                raise ValueError(f"existing failed result requires a separate retry output: {case['id']}")
            print(f"skip {case['id']}: already recorded", flush=True)
            continue
        print(f"start {case['id']} [{case['bucket']}]", flush=True)
        record = run_case(case, args.model, args.base_url, args.timeout, run_id)
        save_record(args.output, record)
        print(f"done {case['id']}: pass={record['case_pass']} wall={record['wall_s']:.2f}s", flush=True)
        if record["error"] and record["error"] != BOUNDED_TOOL_LOOP_ERROR:
            raise RuntimeError(f"stopped after recorded transport/runtime error on {case['id']}: {record['error']}")


def percentile(values: list[float], fraction: float) -> float | None:
    """Return an interpolated percentile for small per-bucket samples."""
    if not values:
        return None
    ordered = sorted(values)
    offset = (len(ordered) - 1) * fraction
    lower = int(offset)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (offset - lower), 2)


def summarize(args: argparse.Namespace) -> None:
    """Report paired case success and latency by bucket without hiding failures."""
    cases = {case["id"]: case for case in load_cases(args.cases)}
    left = {record["id"]: record for record in load_records(args.left)}
    right = {record["id"]: record for record in load_records(args.right)}
    for side in (left, right):
        for case_id, record in side.items():
            if case_id not in cases or record.get("case_sha256") != digest(cases[case_id]):
                raise ValueError(f"unknown or changed case result: {case_id}")
    for bucket in BUCKETS:
        ids = [case_id for case_id, case in cases.items() if case["bucket"] == bucket]
        paired = [case_id for case_id in ids if case_id in left and case_id in right]
        for name, side in (("left", left), ("right", right)):
            items = [side[case_id] for case_id in paired]
            other = right if name == "left" else left
            times = [item["wall_s"] for item in items if isinstance(item.get("wall_s"), (int, float))]
            print(json.dumps({
                "bucket": bucket,
                "side": name,
                "model": items[0]["model"] if items else None,
                "fixture_cases": len(ids),
                "completed": sum(case_id in side for case_id in ids),
                "paired": len(paired),
                "pass": sum(bool(item.get("case_pass")) for item in items),
                "paired_wins": sum(bool(side[case_id].get("case_pass")) and not bool(other[case_id].get("case_pass")) for case_id in paired),
                "paired_losses": sum(not bool(side[case_id].get("case_pass")) and bool(other[case_id].get("case_pass")) for case_id in paired),
                "errors": sum(bool(item.get("error")) for item in items),
                "p50_wall_s": percentile(times, 0.5),
                "p95_wall_s": percentile(times, 0.95),
                "total_prompt_tokens": sum(item.get("prompt_tokens") or 0 for item in items),
                "total_completion_tokens": sum(item.get("completion_tokens") or 0 for item in items),
            }, ensure_ascii=False))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Expose validation, sequential local runs, and paired summaries."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    runner = sub.add_parser("run")
    runner.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    runner.add_argument("--model", required=True)
    runner.add_argument("--base-url", required=True)
    runner.add_argument("--output", type=Path, required=True)
    runner.add_argument("--run-label", required=True, help="describes server engine and launch flags")
    runner.add_argument("--timeout", type=int, default=600)
    runner.add_argument("--bucket", choices=BUCKETS)
    runner.add_argument("--ids", help="comma-separated case IDs")
    runner.add_argument("--limit", type=int)
    summary = sub.add_parser("summarize")
    summary.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    summary.add_argument("--left", type=Path, required=True)
    summary.add_argument("--right", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch the requested benchmark action."""
    args = parse_args(argv)
    if args.command == "validate":
        cases = load_cases(args.cases)
        print(json.dumps({"cases": len(cases), "buckets": {key: sum(c["bucket"] == key for c in cases) for key in BUCKETS}}))
    elif args.command == "run":
        run(args)
    else:
        summarize(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
