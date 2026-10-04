#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Compare actual Hermes tool catalogs on frozen, private coaching request replays.

Only local inference is invoked; no tool execution, learner progress or messaging.
Exportable runs contain metrics/hashes, while replay outputs remain private.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

import interactive_latency as base

QUESTIONS = [
    {"id": "binary_hint", "question": "LeetCode Binary Search를 복습 중이야. mid의 값이 target보다 작을 때 left = mid로 하면 왜 무한 반복할 수 있어? 완성 코드는 주지 말고 한국어로 힌트 하나와 확인 질문 하나만 줘.", "limit": 384},
    {"id": "two_sum_review", "question": "다음은 가상 Two Sum 풀이야. [3, 3], target=6에서 왜 조회 후 삽입하는지, 같은 인덱스를 두 번 쓰지 않는 이유와 시간 복잡도를 한국어로 설명해줘. 개선 코드를 새로 쓰지 마.\nseen = {}\nfor i, n in enumerate(nums):\n    if target - n in seen:\n        return [seen[target - n], i]\n    seen[n] = i", "limit": 640},
]


def visible(text, thinking):
    if thinking:
        if "</think>" not in text:
            return ""
        text = text.split("</think>", 1)[1]
    return text.strip()


def parse(lines, begin, thinking):
    chunks, raw_first, visible_first, final = [], None, None, None
    for line in lines:
        line = line.decode().strip() if isinstance(line, bytes) else line.strip()
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        event = json.loads(line[6:])
        text = event.get("content", "")
        if text:
            chunks.append(text)
            stamp = time.monotonic() - begin
            if raw_first is None:
                raw_first = stamp
            if visible_first is None and visible("".join(chunks), thinking):
                visible_first = stamp
        if event.get("stop"):
            final = event
    if final is None or "timings" not in final:
        raise RuntimeError("missing authoritative native completion timings")
    text = "".join(chunks)
    return visible(text, thinking), raw_first, visible_first, final


def request(prompt, case, repeat, phase, slot, concurrency=1):
    import urllib.request
    payload = {"prompt": prompt, "stream": True, "cache_prompt": phase != "cold",
        "id_slot": slot, "n_predict": case["limit"], "temperature": 0.3,
        "top_k": 20, "top_p": 0.95, "min_p": 0.0, "presence_penalty": 1.5,
        "seed": 1234 + repeat}
    req = urllib.request.Request("http://127.0.0.1:8003/completion", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    started, begin = base.utcnow(), time.monotonic()
    with urllib.request.urlopen(req, timeout=180) as response:
        text, raw_first, first, final = parse(response, begin,
            thinking=prompt.rstrip().endswith("<think>"))
    wall = time.monotonic() - begin
    timings = final["timings"]
    if final.get("truncated") or (phase == "cold" and timings.get("cache_n", 0)):
        raise RuntimeError("context truncated or cold cache mislabeled")
    if phase != "cold" and not timings.get("cache_n", 0):
        raise RuntimeError("warm replay did not reuse cache")
    metrics = base.metrics_from_timings(timings, first, wall)
    # Visible delivery excludes hidden reasoning; do not estimate decode from it.
    metrics.pop("client_decode_tps", None)
    row = {"id": f"{case['id']}-{repeat}-{phase}-{slot}", "case": case["id"],
        "workflow": "coding", "phase": phase, "repeat": repeat, "concurrency": concurrency,
        "output_limit": case["limit"], "started_at": started, "completed_at": base.utcnow(),
        "prompt_sha256": base.digest(prompt), "output_sha256": base.digest(text),
        "metrics": metrics, "quality": {"nonempty": bool(text),
            "hangul_present": any('가' <= c <= '힣' for c in text),
            "output_limit_reached": bool(final.get("stopped_limit")),
            "scope": "synthetic coaching replay; manually review private outputs; no tool-loop quality claim"}}
    return row, {"id": row["id"], "output": text, "raw_ttft_s": raw_first,
        "finish_limit": final.get("stopped_limit"), "tool_call_present": "<tool_call>" in text}


def fixture():
    from dotenv import load_dotenv
    load_dotenv(str(Path.home() / ".hermes/.env"), override=False)
    os.environ["HERMES_HOME"] = str(Path.home() / ".hermes")
    sys.path.insert(0, "/home/david/.local/lib/python3.13/site-packages")
    from run_agent import AIAgent
    from gateway.run import _resolve_runtime_agent_kwargs, _resolve_gateway_model, _load_gateway_config, GatewayRunner
    from hermes_cli.tools_config import _get_platform_tools
    agent = AIAgent(model=_resolve_gateway_model(), **_resolve_runtime_agent_kwargs(),
        enabled_toolsets=sorted(_get_platform_tools(_load_gateway_config(), "api_server")),
        session_id="diagnostic_latency_fixture", platform="api_server", quiet_mode=True,
        verbose_logging=False, max_iterations=1, reasoning_config=GatewayRunner._load_reasoning_config())
    plugin_path = Path(__file__).resolve().parents[2] / "config/plugins/leetcode-latency/__init__.py"
    spec = importlib.util.spec_from_file_location("coaching_catalog", plugin_path)
    policy = importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)
    prompt = agent._build_system_prompt()
    tools = {"full": agent.tools, "focused": policy.focus_tools(agent, [])}
    if not tools["focused"]:
        raise RuntimeError("required coding tools unavailable")
    prompts = {}
    for variant, catalog in tools.items():
        prompts[variant] = {}
        for case in QUESTIONS:
            messages = [{"role": "system", "content": prompt + "\nYou are Jun, David's coding coach. Give concise Korean hints before solutions. These are synthetic practice questions; do not use tools or claim access to real records."},
                {"role": "user", "content": case["question"]}]
            rendered = base.api("http://127.0.0.1:8003", "/apply-template", {
                "messages": messages, "tools": catalog, "add_generation_prompt": True})["prompt"]
            prompts[variant][case["id"]] = rendered
    return prompts, {k: len(v) for k, v in tools.items()}, agent.model


def run(args):
    endpoint = "http://127.0.0.1:8003"
    props = base.api(endpoint, "/props")
    assert props["total_slots"] == 2 and props["default_generation_settings"]["n_ctx"] == 131072
    prompts, counts, model = fixture()
    out = args.output.expanduser().resolve();out.mkdir(parents=True, exist_ok=True)
    reports, outputs = {}, {}
    for variant in prompts:
        reports[variant] = {"schema_version": 1, "run_id": str(uuid4()),
            "label": f"Jun coding · {variant} tools · reasoning unchanged", "source": "hermes_tool_catalog_replay",
            "started_at": base.utcnow(), "model": model, "context_per_request": 131072, "slots": 2,
            "mtp": "off", "batch": 4096, "ubatch": 1024,
            "dataset_digest": base.digest(QUESTIONS), "sampling": {"temperature": 0.3, "seed_base": 1234,
                "top_k": 20, "top_p": 0.95, "min_p": 0.0, "presence_penalty": 1.5},
            "scope": f"Frozen Hermes request replay, {counts[variant]} original tool schemas; visible TTFT excludes hidden reasoning",
            "cold_definition": "cache_prompt=false; cold prompt, resident/warm engine",
            "limitations": ["No full agent/tool loop or browser delivery measurement", "Warm replay repeats the same request, not a conversation follow-up", "No p95 or filled 128K×2 endurance measurement", "Native decode TPS includes generated hidden reasoning", "Only the tool catalog differs; no model/build or reasoning setting change"],
            "records": []}
        outputs[variant] = []
    jobs = [(case, rep, 1) for case in QUESTIONS for rep in range(args.repetitions if case['id']=='binary_hint' else 1)]
    if args.concurrent:
        jobs.append((QUESTIONS[0], 0, 2))
    for case, repeat, concurrency in jobs:
        # Alternate the arm order to reduce time/temperature order bias.
        order = ["full", "focused"] if repeat % 2 == 0 else ["focused", "full"]
        for variant in order:
            prompt = prompts[variant][case["id"]]
            for phase in (["cold", "warm_replay"] if concurrency == 1 else ["cold"]):
                base.require_ready(endpoint, seconds=55)
                with base.Telemetry(endpoint) as telemetry:
                    if concurrency == 1:
                        pairs = [request(prompt, case, repeat, phase, 0)]
                    else:
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            pairs = list(pool.map(lambda slot: request(prompt, case, repeat, phase, slot, 2), [0, 1]))
                summary = telemetry.summary()
                for row, output in pairs:
                    row['telemetry'] = summary
                    reports[variant]['records'].append(row);outputs[variant].append(output)
                for arm in reports:
                    base.write_json(out / (arm + '.json'), reports[arm])
                    base.write_json(out / (arm + '-private-outputs.json'), outputs[arm])
                print(json.dumps({'arm':variant,'case':case['id'],'repeat':repeat,'phase':phase,'concurrency':concurrency,
                    'metrics':[r[0]['metrics'] for r in pairs],'telemetry':summary}), flush=True)
    for variant in reports:
        reports[variant]['completed_at'] = base.utcnow();base.write_json(out / (variant + '.json'), reports[variant])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repetitions', type=int, choices=range(1,4), default=3)
    parser.add_argument('--concurrent', action='store_true')
    run(parser.parse_args())


if __name__ == '__main__':
    main()
