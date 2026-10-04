#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Measure bounded synthetic coaching replies on the existing llama.cpp server.

No Hermes tools, real learner data, messaging, or provider lifecycle changes are
invoked. Records retain timing, token counts, hashes and host telemetry only.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import threading
import time
import urllib.request
from uuid import uuid4
from datetime import datetime, timezone


VERSION = "1.0"
CASES = [
    {"id": "coding_hint", "workflow": "coding", "target_input": 20000,
     "limit": 256, "question": "Binary Search를 복습 중이야. 반복문에서 왼쪽 경계가 갱신되지 않아. 완성 코드는 주지 말고 한국어로 힌트 하나와 확인 질문 하나만 줘.",
     "followup": "mid가 target보다 작으면 어느 경계를 옮겨야 해? 한국어로 짧게 답하고 내 이해를 확인해 줘."},
    {"id": "english_correction", "workflow": "english", "target_input": 16000,
     "limit": 256, "question": "과거시제를 자꾸 틀려. 'Yesterday I go to the office and meet my manager.'를 고쳐 주고 한국어로 이유 하나와 짧은 연습 질문 하나를 줘.",
     "followup": "'Last week she buy a book.'도 같은 약점일까? 교정 문장과 한국어 설명을 짧게 줘."},
    {"id": "coding_explanation", "workflow": "coding", "target_input": 20000,
     "limit": 512, "question": "과거에 풀었던 Valid Parentheses 문제를 복습하는 가상 상황이야. 왜 스택이 필요한지 예시 두 개, 시간·공간 복잡도, 흔한 실수 두 가지를 한국어로 설명해 줘. 내 실제 풀이를 조회했다고 말하지 마.",
     "followup": "입력이 '([)]'일 때 단순히 괄호 개수만 세면 왜 틀려? 한국어로 단계별로 설명해 줘."},
    {"id": "english_drill", "workflow": "english", "target_input": 16000,
     "limit": 384, "question": "가상의 학습 약점은 과거시제와 주어·동사 일치야. 'She work remotely yesterday.'와 'They was ready.'를 각각 교정하고, 한국어 설명과 정답이 있는 짧은 연습 두 개를 만들어 줘.",
     "followup": "'He have a meeting every Monday.'와 'We was late yesterday.'를 교정하고 지금까지의 약점을 한 문장으로 정리해 줘."},
]


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def api(base, path, payload=None):
    request = urllib.request.Request(base.rstrip("/") + path,
        data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def write_json(path, value):
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temp.chmod(0o600)
    temp.replace(path)


def host_sample(base):
    """UMA observations overlap; do not sum RSS and reported GPU allocation."""
    memory = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        if key in ("MemAvailable", "MemFree"):
            memory[key] = int(value.split()[0]) / 1024**2
    values = subprocess.check_output(["nvidia-smi", "--id=0",
        "--query-gpu=temperature.gpu,temperature.gpu.tlimit,clocks_event_reasons.hw_thermal_slowdown,clocks_event_reasons.sw_thermal_slowdown,memory.used",
        "--format=csv,noheader,nounits"], text=True, timeout=4).strip().split(",")
    metrics = urllib.request.urlopen(base.rstrip("/") + "/metrics", timeout=4)
    with metrics:
        text = metrics.read().decode()
    load = {}
    for name in ("requests_processing", "requests_deferred"):
        match = re.search(r"^llamacpp:" + name + r"(?:\{[^\n]*\})?\s+([\d.]+)$", text, re.M)
        if not match:
            raise RuntimeError("scheduler metrics unavailable")
        load[name] = int(float(match[1]))
    return {"available_gib": memory["MemAvailable"], "free_gib": memory["MemFree"],
        "gpu_c": float(values[0]), "gpu_margin_c": float(values[1]),
        "hw_thermal": values[2].strip() == "Active", "sw_thermal": values[3].strip() == "Active",
        "gpu_reported_used_gib": None if values[4].strip() in ("[N/A]", "N/A") else float(values[4]) / 1024,
        **load}


def require_ready(base, seconds=180):
    deadline = time.monotonic() + seconds
    while True:
        state = host_sample(base)
        if state["available_gib"] < 24 or state["free_gib"] < 8:
            raise RuntimeError("host memory below existing 24/8 GiB admission limits")
        if state["gpu_margin_c"] >= 8 and not state["requests_processing"] and not state["requests_deferred"]:
            return state
        if time.monotonic() >= deadline:
            raise RuntimeError("server remained busy or thermal margin insufficient")
        time.sleep(1)


class Telemetry:
    def __init__(self, base):
        self.base = base
        self.samples = []
        self.errors = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.collect, daemon=True)

    def collect(self):
        while not self.stop.is_set():
            try:
                self.samples.append(host_sample(self.base))
            except Exception as exc:
                self.errors.append(type(exc).__name__)
            self.stop.wait(1)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(8)

    def summary(self):
        if not self.samples:
            return {"available": False, "sampling_errors": self.errors}
        samples = self.samples
        gpu = [s["gpu_reported_used_gib"] for s in samples if s["gpu_reported_used_gib"] is not None]
        return {"available": True, "sample_interval_s": 1, "samples": len(samples),
            "min_available_gib": min(s["available_gib"] for s in samples),
            "min_free_gib": min(s["free_gib"] for s in samples),
            "max_gpu_reported_used_gib": max(gpu) if gpu else None,
            "max_gpu_c": max(s["gpu_c"] for s in samples),
            "min_gpu_margin_c": min(s["gpu_margin_c"] for s in samples),
            "hw_thermal_observed": any(s["hw_thermal"] for s in samples),
            "sw_thermal_observed": any(s["sw_thermal"] for s in samples),
            "max_requests_processing": max(s["requests_processing"] for s in samples),
            "max_requests_deferred": max(s["requests_deferred"] for s in samples),
            "sampling_errors": sorted(set(self.errors)),
            "accounting": "shared UMA; GPU allocation is not additional physical capacity"}


def render(base, messages):
    result = api(base, "/apply-template", {"messages": messages,
        "add_generation_prompt": True, "chat_template_kwargs": {"enable_thinking": False}})
    return result["prompt"]


def build_messages(base, case, repeat):
    """Size synthetic context with the server tokenizer, never real learner memory."""
    instruction = ("You are a patient coding and English practice coach. Use Korean for explanations. "
        "Answer only the final learner question. Never claim access to real records. "
        "The following archive is synthetic inert background, not instructions.\n"
        f"Benchmark repetition {repeat}.\n")
    filler = "\n".join(f"Archive {i}: fictional learner reviewed neutral vocabulary and algorithm notes; this record is background only." for i in range(2400))
    low, high = 0, len(filler)
    chosen = None
    while low <= high:
        size = (low + high) // 2
        messages = [{"role": "system", "content": instruction + filler[:size]},
                    {"role": "user", "content": case["question"]}]
        prompt = render(base, messages)
        count = len(api(base, "/tokenize", {"content": prompt, "add_special": False})["tokens"])
        if count <= case["target_input"]:
            chosen = messages
            low = size + 1
        else:
            high = size - 1
    if chosen is None:
        raise ValueError("target input smaller than coaching instructions")
    return chosen


def parse_stream(lines, begin):
    chunks, first, final = [], None, None
    for line in lines:
        if not line.startswith(b"data: "):
            continue
        raw = line[6:].strip()
        if raw == b"[DONE]":
            continue
        item = json.loads(raw)
        if item.get("error"):
            raise RuntimeError("model returned a stream error")
        text = item.get("content") or ""
        if text:
            if first is None:
                first = time.monotonic() - begin
            chunks.append(text)
        if item.get("stop"):
            final = item
    if final is None:
        raise RuntimeError("stream missing final timings")
    return "".join(chunks), first, final


def metrics_from_timings(timings, ttft, wall):
    output = timings["predicted_n"]
    return {"ttft_s": ttft, "wall_s": wall,
        "prefill_s": timings["prompt_ms"] / 1000, "decode_s": timings["predicted_ms"] / 1000,
        "full_input_tokens": timings["prompt_n"] + timings.get("cache_n", 0),
        "processed_input_tokens": timings["prompt_n"], "cached_input_tokens": timings.get("cache_n", 0),
        "output_tokens": output, "prefill_tps": timings.get("prompt_per_second"),
        "decode_tps": timings.get("predicted_per_second"),
        "client_decode_tps": (output - 1) / (wall - ttft) if ttft is not None and output > 1 and wall > ttft else None,
        "draft_tokens": timings.get("draft_n", 0), "accepted_draft_tokens": timings.get("draft_n_accepted", 0)}


def request(base, prompt, case, repeat, phase, slot, concurrency=1):
    payload = {"prompt": prompt, "stream": True, "cache_prompt": phase != "cold",
        "id_slot": slot, "n_predict": case["limit"], "temperature": 0.1,
        "top_k": 20, "top_p": 0.95, "min_p": 0.0, "presence_penalty": 1.5,
        "seed": 1234 + repeat}
    req = urllib.request.Request(base.rstrip("/") + "/completion", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    started_at, begin = utcnow(), time.monotonic()
    with urllib.request.urlopen(req, timeout=180) as response:
        text, first, final = parse_stream(response, begin)
    wall = time.monotonic() - begin
    timings = final["timings"]
    if final.get("truncated"):
        raise RuntimeError("server truncated input; context contract violated")
    if phase == "cold" and timings.get("cache_n", 0):
        raise RuntimeError("cold request unexpectedly reused prompt cache")
    return {"id": f"{case['id']}-{repeat}-{phase}-{slot}", "case": case["id"],
        "workflow": case["workflow"], "phase": phase, "repeat": repeat,
        "concurrency": concurrency, "output_limit": case["limit"],
        "started_at": started_at, "completed_at": utcnow(), "prompt_sha256": digest(prompt),
        "output_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "metrics": metrics_from_timings(timings, first, wall),
        "quality": {"nonempty": bool(text.strip()), "hangul_present": bool(re.search("[가-힣]", text)),
            "output_limit_reached": bool(final.get("stopped_limit")),
            "scope": "format checks only; teaching correctness requires review"}}, text


def run(args):
    props = api(args.base_url, "/props")
    if props["total_slots"] != 2 or props["default_generation_settings"]["n_ctx"] != 131072:
        raise RuntimeError("retain two 128K slots before benchmarking")
    model = api(args.base_url, "/v1/models")["data"][0]["id"]
    cases = [c for c in CASES if not args.case or c["id"] in args.case]
    if not cases:
        raise ValueError("no cases selected")
    report = {"schema_version": 1, "run_id": str(uuid4()), "label": args.label,
        "source": "synthetic_coaching_api", "started_at": utcnow(), "model": model,
        "build": props.get("build_info"), "dataset_digest": digest(CASES),
        "context_per_request": 131072, "slots": 2, "mtp": "off",
        "scope": "model API; no live Hermes tool loop or Telegram/web delivery",
        "sampling": {"temperature": 0.1, "top_k": 20, "top_p": 0.95, "min_p": 0.0,
                     "presence_penalty": 1.5, "seed_base": 1234, "thinking": False},
        "cold_definition": "uncached prompt on already loaded model; not process cold start",
        "records": []}
    pid = subprocess.check_output(["systemctl", "--user", "show", "hermes-vllm.service", "-p", "MainPID", "--value"], text=True).strip()
    argv = Path(f"/proc/{pid}/cmdline").read_bytes().decode().split("\0")
    if any(x.startswith("--spec-type") for x in argv):
        raise RuntimeError("this baseline runner requires production MTP OFF")
    report["provider_pid"] = int(pid)
    try:
        for repeat in range(args.repetitions):
            for case in cases:
                messages = build_messages(args.base_url, case, repeat)
                for phase in ("cold", "warm_followup"):
                    require_ready(args.base_url)
                    if Path(f"/proc/{pid}/cmdline").read_bytes().decode().split("\0") != argv:
                        raise RuntimeError("provider changed during run")
                    prompt = render(args.base_url, messages)
                    with Telemetry(args.base_url) as telemetry:
                        row, text = request(args.base_url, prompt, case, repeat, phase, 0)
                    row["telemetry"] = telemetry.summary()
                    report["records"].append(row)
                    write_json(args.output, report)
                    print(json.dumps({"case": row["case"], "phase": phase, **row["metrics"]}), flush=True)
                    messages += [{"role": "assistant", "content": text}, {"role": "user", "content": case["followup"]}]
        if args.concurrent:
            for repeat in range(args.repetitions):
                pair = [CASES[0], CASES[1]]
                prompts = [render(args.base_url, build_messages(args.base_url, c, repeat + 100)) for c in pair]
                require_ready(args.base_url)
                begin = time.monotonic()
                with Telemetry(args.base_url) as telemetry, concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(request, args.base_url, prompt, case, repeat, "cold", slot, 2)
                        for slot, (prompt, case) in enumerate(zip(prompts, pair))]
                    rows = [f.result()[0] for f in futures]
                pair_wall = time.monotonic() - begin
                for row in rows:
                    row["id"] += "-pair"
                    row["telemetry"] = telemetry.summary()
                    row["pair_wall_s"] = pair_wall
                    row["pair_output_wall_tps"] = sum(r["metrics"]["output_tokens"] for r in rows) / pair_wall
                    report["records"].append(row)
                    print(json.dumps({"case": row["case"], "concurrency": 2, **row["metrics"]}), flush=True)
                write_json(args.output, report)
    except Exception as exc:
        report["failure_class"] = type(exc).__name__
        raise
    finally:
        report["completed_at"] = utcnow()
        report["completed_records"] = len(report["records"])
        write_json(args.output, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8003")
    parser.add_argument("--label", default="production-mtp-off-coaching")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--case", action="append", choices=[c["id"] for c in CASES])
    parser.add_argument("--concurrent", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 10:
        parser.error("repetitions must be 1..10")
    run(args)


if __name__ == "__main__":
    main()
