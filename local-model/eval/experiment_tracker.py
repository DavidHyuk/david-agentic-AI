#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Import latency experiments, render an offline dashboard, and export metrics.

Post-run Langfuse OTLP and LangSmith publishing are optional. No prompts,
completions, learner identifiers, photos, credentials, or raw logs are exported.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import urllib.request
from uuid import uuid5, NAMESPACE_URL
from urllib.parse import urlsplit


METRIC_KEYS = {"ttft_s", "wall_s", "server_total_s", "prefill_s", "decode_s",
    "full_input_tokens", "processed_input_tokens", "cached_input_tokens", "output_tokens",
    "prefill_tps", "decode_tps", "client_decode_tps", "draft_tokens", "accepted_draft_tokens"}
ROW_KEYS = {"id", "case", "workflow", "phase", "repeat", "concurrency", "output_limit",
    "started_at", "completed_at", "prompt_sha256", "output_sha256", "pair_wall_s", "pair_output_wall_tps"}
TELEMETRY_KEYS = {"available", "sample_interval_s", "samples", "min_available_gib", "min_free_gib",
    "max_gpu_reported_used_gib", "max_gpu_c", "min_gpu_margin_c", "hw_thermal_observed", "sw_thermal_observed",
    "max_requests_processing", "max_requests_deferred", "sampling_errors", "accounting"}
RUN_KEYS = {"schema_version", "run_id", "label", "source", "started_at", "completed_at", "model", "build",
    "dataset_digest", "context_per_request", "slots", "mtp", "scope", "sampling", "cold_definition",
    "failure_class", "completed_records", "limitations", "session_usage", "kernel_audit", "batch", "ubatch", "input_budget_tokens", "recorded_at"}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def stable_id(value):
    return str(uuid5(NAMESPACE_URL, value))


def save(path, value):
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    tmp.chmod(0o600)
    tmp.replace(path)


def sanitize(run):
    clean = {k: v for k, v in run.items() if k in RUN_KEYS}
    clean["records"] = []
    for row in run.get("records", []):
        item = {k: v for k, v in row.items() if k in ROW_KEYS}
        item["metrics"] = {k: v for k, v in row.get("metrics", {}).items() if k in METRIC_KEYS and (v is None or isinstance(v, (int, float)))}
        item["telemetry"] = {k: v for k, v in row.get("telemetry", {}).items() if k in TELEMETRY_KEYS}
        item["quality"] = {k: v for k, v in row.get("quality", {}).items()
            if k in ("nonempty", "hangul_present", "output_limit_reached", "scope")}
        clean["records"].append(item)
    return clean


def import_mtp(directory):
    runs = []
    for filename, label, enabled in (
        ("current-fixed-no-mtp.json", "Matched MTP OFF · repaired feature build", False),
        ("current-fixed-mtp2.json", "Matched MTP ON · draft 2", True),
        ("production-fixed-no-mtp.json", "Production build · MMQ repaired · MTP OFF", False)):
        path = directory / filename
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        host = data.get("host", {})
        telemetry = {
            "min_available_gib": host.get("minimum_available_gib"),
            "min_free_gib": host.get("minimum_free_gib"),
            "max_gpu_c": host.get("maximum_gpu_c"),
            "min_gpu_margin_c": host.get("minimum_gpu_margin_c"),
            "hw_thermal_observed": host.get("hw_thermal_observed"),
            "sw_thermal_observed": host.get("sw_thermal_observed"),
            "accounting": "run-wide extrema, not per-request samples; unified memory"}
        run = {"schema_version": 1, "run_id": stable_id(filename + data.get("prompt_digest", "")),
            "recorded_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            "label": label, "source": "mtp_matched_historical", "model": "Qwen3.8-Flash-Next-UD-IQ4_XS",
            "build": data.get("model_build"), "dataset_digest": data.get("prompt_digest"),
            "context_per_request": data["context_per_slot"], "slots": data["slots"], "mtp": "on" if enabled else "off",
            "batch": data.get("batch"), "ubatch": data.get("ubatch"),
            "cold_definition": "matched result samples only; separate first-request startup sample excluded",
            "scope": "historical synthetic text benchmark, not conversational agent replay",
            "limitations": ["both feature arms thermally throttled", "absolute request timestamps unavailable",
                "128K filled-context endurance and broad semantic quality untested"], "records": []}
        for result in data["results"]:
            for index, response in enumerate(result["requests"]):
                t = response["timings"]
                run["records"].append({"id": f"{result['case']}-{result['repeat']}-{index}",
                    "case": result["case"], "workflow": "synthetic", "phase": "uncached", "repeat": result["repeat"],
                    "concurrency": result["concurrency"], "output_limit": result["output_tokens_per_request"],
                    "metrics": {"ttft_s": response["ttft_s"], "wall_s": response["wall_s"],
                        "prefill_s": t["prompt_ms"] / 1000, "decode_s": t["predicted_ms"] / 1000,
                        "full_input_tokens": result["input_tokens"], "processed_input_tokens": t["prompt_n"],
                        "cached_input_tokens": t.get("cache_n", 0), "output_tokens": response["generated_tokens"],
                        "prefill_tps": t.get("prompt_per_second"), "decode_tps": t.get("predicted_per_second"),
                        "draft_tokens": t.get("draft_n", 0), "accepted_draft_tokens": t.get("draft_n_accepted", 0)},
                    "pair_wall_s": result["wall_s"] if result["concurrency"] == 2 else None,
                    "output_sha256": response.get("output_sha256"), "telemetry": telemetry})
        runs.append(sanitize(run))
    return runs


def session_usage(home, since):
    summary = {}
    for name in ("default", "english"):
        path = (home if name == "default" else home / "profiles" / name) / "state.db"
        if not path.exists():
            continue
        conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        try:
            rows = conn.execute("""SELECT source,input_tokens,cache_read_tokens,cache_write_tokens,
                output_tokens,api_call_count FROM sessions WHERE started_at>=? AND
                model='Qwen3.8-Flash-Next-UD-IQ4_XS' AND api_call_count>0""", (since,)).fetchall()
        finally:
            conn.close()
        group = [r for r in rows if r[0] == "cron"]
        calls = sum(r[5] for r in group)
        if calls:
            summary[name] = {"source": "cron", "sessions": len(group), "calls": calls,
                "mean_full_input_tokens": sum(sum(x or 0 for x in r[1:4]) for r in group) / calls,
                "mean_processed_input_tokens": sum(r[1] or 0 for r in group) / calls,
                "mean_output_tokens": sum(r[4] or 0 for r in group) / calls,
                "scope": "cumulative session counters; no per-call percentiles or interactive latency"}
    return summary


def parse_journal(lines, pid=None):
    """Keep scalar timing lines only; reconstruct context from OFF slot release."""
    rows = {}
    for raw in lines:
        event = json.loads(raw)
        if pid is not None and str(event.get("_PID")) != str(pid):
            continue
        line = event.get("MESSAGE", "")
        match = re.search(r"id\s+(\d+)\s*\| task\s+(\d+)\s*\| (.*)", line)
        if not match:
            continue
        key = (str(event.get("_PID")), match[1], match[2])
        row = rows.setdefault(key, {"metrics": {}})
        tail = match[3]
        stamp = datetime.fromtimestamp(int(event["__REALTIME_TIMESTAMP"]) / 1e6, timezone.utc).isoformat()
        prompt = re.search(r"prompt eval time =\s*([\d.]+) ms /\s*(\d+) tokens.*?([\d.]+) tokens per second", tail)
        decode = re.search(r"^\s*eval time =\s*([\d.]+) ms /\s*(\d+) tokens.*?([\d.]+) tokens per second", tail)
        total = re.search(r"total time =\s*([\d.]+) ms", tail)
        release = re.search(r"stop processing: n_tokens =\s*(\d+), truncated = (\d+)", tail)
        if prompt:
            row["completed_at"] = stamp
            row["metrics"].update(prefill_s=float(prompt[1]) / 1000,
                processed_input_tokens=int(prompt[2]), prefill_tps=float(prompt[3]))
        if decode:
            row["metrics"].update(decode_s=float(decode[1]) / 1000,
                output_tokens=int(decode[2]), decode_tps=float(decode[3]))
        if total:
            row["metrics"]["server_total_s"] = float(total[1]) / 1000
        if release:
            row["slot_tokens"] = int(release[1])
            row["truncated"] = bool(int(release[2]))
    result = []
    for key, row in rows.items():
        m = row["metrics"]
        if not all(k in m for k in ("processed_input_tokens", "output_tokens", "server_total_s")) or "slot_tokens" not in row or row.get("truncated"):
            continue
        full = row["slot_tokens"] + 1 - m["output_tokens"]
        if full < m["processed_input_tokens"]:
            continue
        m.update(full_input_tokens=full, cached_input_tokens=full - m["processed_input_tokens"], ttft_s=None, wall_s=None)
        result.append({"id": hashlib.sha256(":".join(key).encode()).hexdigest()[:16],
            "case": "production_model_call", "workflow": "unattributed", "phase": "cached" if m["cached_input_tokens"] else "uncached",
            "concurrency": None, "completed_at": row["completed_at"], "metrics": m})
    return result


def audit(args):
    pid = subprocess.check_output(["systemctl", "--user", "show", "hermes-vllm.service", "-p", "MainPID", "--value"], text=True).strip()
    argv = Path(f"/proc/{pid}/cmdline").read_bytes().decode().split("\0")
    if any(x.startswith("--spec-type") for x in argv):
        raise RuntimeError("slot-context reconstruction requires MTP OFF")
    command = ["journalctl", "--user", "-u", "hermes-vllm.service", "--since", args.since,
        "--until", args.until, "--no-pager", "-o", "json"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)
    records = parse_journal(process.stdout, pid)
    if process.wait():
        raise RuntimeError("journal read failed")
    run = {"schema_version": 1, "run_id": stable_id("production:" + args.since + args.until + pid),
        "recorded_at": datetime.fromtimestamp(args.output.stat().st_mtime, timezone.utc).isoformat() if args.output.exists() else utcnow(),
        "label": "Production server logs · MTP OFF", "source": "production_server_log",
        "model": "Qwen3.8-Flash-Next-UD-IQ4_XS", "mtp": "off", "context_per_request": 131072, "slots": 2,
        "scope": "server-only telemetry; no measured client TTFT, tool duration or delivery latency",
        "limitations": ["requests cannot be attributed to a specific coach from scalar logs",
            "full input reconstructed from OFF slot release; cached and processed tokens separated"],
        "session_usage": session_usage(args.hermes_home, datetime(2026, 9, 27, tzinfo=timezone.utc).timestamp()),
        "records": records}
    save(args.output, sanitize(run))
    print(json.dumps({"production_calls": len(records), "output": str(args.output)}))


def load_runs(paths):
    result = []
    for path in paths:
        data = json.loads(path.read_text())
        for run in (data if isinstance(data, list) else [data]):
            # Artifact recording time anchors import spans; never invent request starts.
            run.setdefault("recorded_at", datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat())
            result.append(sanitize(run))
    ids = [r["run_id"] for r in result]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate experiments; do not double-count imported measurements")
    for run in result:
        item_ids = [row['id'] for row in run['records']]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("duplicate experiment items; give concurrency variants distinct IDs")
    return result


def report(args):
    runs = load_runs(args.input)
    # Escape script delimiters even when a label contains HTML; render textContent.
    data = json.dumps(runs, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028")
    template = Path(__file__).with_name("latency_dashboard.html").read_text()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(template.replace("__EXPERIMENT_DATA__", data))
    args.output.chmod(0o600)
    print(json.dumps({"experiments": len(runs), "records": sum(len(r["records"]) for r in runs), "dashboard": str(args.output)}))


def otlp_attributes(values):
    def encode(value):
        if isinstance(value, bool):
            return {"boolValue": value}
        if isinstance(value, int):
            return {"intValue": str(value)}
        if isinstance(value, float):
            return {"doubleValue": value}
        return {"stringValue": value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)}
    return [{"key": key, "value": encode(value)} for key, value in values.items() if value is not None]


def langfuse_payload(runs):
    spans = []
    for run in runs:
        for row in run["records"]:
            identity = run["run_id"] + ":" + row["id"]
            trace_id = hashlib.sha256(identity.encode()).hexdigest()[:32]
            span_id = hashlib.sha256((identity + ":span").encode()).hexdigest()[:16]
            historical = not (row.get("started_at") and row.get("completed_at"))
            start = datetime.fromisoformat(row["started_at"]) if not historical else datetime.fromisoformat(run.get("recorded_at") or utcnow())
            end = datetime.fromisoformat(row["completed_at"]) if not historical else start
            m = row["metrics"]
            attrs = {"langfuse.observation.type": "span" if historical else "generation",
                "langfuse.experiment.id": run["run_id"], "langfuse.experiment.name": run["label"],
                "langfuse.experiment.dataset.id": run.get("dataset_digest") or "local:production-metrics",
                "langfuse.experiment.item.id": row["id"], "langfuse.experiment.item.root_observation_id": span_id,
                "langfuse.environment": "experiment", "langfuse.trace.name": row["case"],
                "langfuse.trace.public": False,
                "langfuse.observation.metadata.historical_import": historical,
                "langfuse.observation.metadata.source": run["source"],
                "langfuse.observation.metadata.mtp": run.get("mtp"),
                "langfuse.observation.metadata.workflow": row.get("workflow"),
                "langfuse.observation.metadata.phase": row.get("phase"),
                "langfuse.observation.metadata.concurrency": row.get("concurrency"),
                "langfuse.observation.metadata.context_per_request": run.get("context_per_request"),
                "langfuse.observation.metadata.slots": run.get("slots"),
                "langfuse.observation.metadata.build": run.get("build"),
                "langfuse.observation.metadata.batch": run.get("batch"),
                "langfuse.observation.metadata.ubatch": run.get("ubatch"),
                "langfuse.observation.metadata.sampling": run.get("sampling"),
                "langfuse.observation.metadata.output_limit": row.get("output_limit"),
                "langfuse.observation.metadata.input_budget_tokens": run.get("input_budget_tokens"),
                "langfuse.observation.metadata.kernel_audit": run.get("kernel_audit"),
                "langfuse.observation.input": json.dumps({"case": row["case"], "prompt_sha256": row.get("prompt_sha256")}),
                "langfuse.observation.output": json.dumps({"metrics": m, "quality": row.get("quality", {})}),
                "langfuse.observation.metadata.telemetry": row.get("telemetry", {})}
            attrs.update({"langfuse.observation.metadata." + key: value for key, value in m.items()})
            if not historical:
                attrs["langfuse.observation.model.name"] = run["model"]
                attrs["langfuse.observation.usage_details"] = json.dumps({
                    "input": m.get("full_input_tokens"), "output": m.get("output_tokens")})
                if m.get("ttft_s") is not None:
                    attrs["langfuse.observation.completion_start_time"] = (start + timedelta(seconds=m["ttft_s"])).isoformat()
            spans.append({"traceId": trace_id, "spanId": span_id, "name": row["case"], "kind": 1,
                "startTimeUnixNano": str(round(start.timestamp() * 1e9)),
                "endTimeUnixNano": str(round(end.timestamp() * 1e9)),
                "attributes": otlp_attributes(attrs), "status": {"code": 1}})
    return {"resourceSpans": [{"resource": {"attributes": otlp_attributes({"service.name": "david-agent-latency-experiments"})},
        "scopeSpans": [{"scope": {"name": "david-agent.experiments", "version": "1.0"}, "spans": spans}]}]}


def langfuse_credentials(path=None):
    """Load three private settings without executing a shell or printing keys."""
    names = ("LANGFUSE_BASE_URL", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
    values = {name: os.environ.get(name, "") for name in names}
    if path is not None:
        path = Path(path).expanduser()
        if path.stat().st_mode & 0o077:
            raise ValueError("Langfuse credentials file must be private: chmod 600")
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            if not sep or key.strip() not in names:
                raise ValueError("invalid Langfuse credentials setting")
            value = value.strip()
            if len(value) >= 2 and value[0] in ("'", '"') and value[-1] == value[0]:
                value = value[1:-1]
            values[key.strip()] = value
    if values["LANGFUSE_BASE_URL"]:
        parsed = urlsplit(values["LANGFUSE_BASE_URL"])
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("invalid Langfuse base URL")
    return values


def status_langfuse(args):
    values = langfuse_credentials(args.credentials)
    print(json.dumps({"configured": all(values.values()), "base_url": values["LANGFUSE_BASE_URL"] or None,
        "public_key_present": bool(values["LANGFUSE_PUBLIC_KEY"]),
        "secret_key_present": bool(values["LANGFUSE_SECRET_KEY"]), "connection_tested": False}))


def langfuse_scores(runs, payload):
    """Attach numeric performance measurements to each experiment-item root."""
    spans = payload["resourceSpans"][0]["scopeSpans"][0]["spans"]
    rows = [row for run in runs for row in run["records"]]
    events = []
    for row, span in zip(rows, spans):
        values = {k: row["metrics"].get(k) for k in ("ttft_s", "wall_s", "prefill_s", "decode_tps")}
        values.update({k: row.get("telemetry", {}).get(k) for k in ("min_available_gib", "min_gpu_margin_c")})
        timestamp = datetime.fromtimestamp(int(span["endTimeUnixNano"]) / 1e9, timezone.utc).isoformat()
        for name, value in values.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                continue
            identity = span["traceId"] + ":" + name
            events.append({"id": stable_id(identity + ":event"), "timestamp": timestamp,
                "type": "score-create", "body": {"id": stable_id(identity), "traceId": span["traceId"],
                    "observationId": span["spanId"], "name": name, "value": float(value),
                    "dataType": "NUMERIC", "environment": "experiment",
                    "comment": "Measured performance; not a semantic correctness score."}})
    return {"batch": events}


def publish_langfuse(args):
    runs = load_runs(args.input)
    payload = langfuse_payload(runs)
    scores = langfuse_scores(runs, payload)
    if args.dry_run:
        save(args.dry_run, payload)
        score_path = args.dry_run.with_suffix(".scores.json")
        save(score_path, scores)
        print(json.dumps({"prepared": str(args.dry_run), "scores_prepared": str(score_path), "uploaded": False}))
        return
    settings = langfuse_credentials(getattr(args, "credentials", None))
    public, secret, base = (settings[key] for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL"))
    if not all((public, secret, base)):
        raise RuntimeError("configure LANGFUSE_BASE_URL, LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY")
    auth = base64.b64encode((public + ":" + secret).encode()).decode()
    req = urllib.request.Request(base.rstrip("/") + "/api/public/otel/v1/traces", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Basic " + auth,
                 "x-langfuse-ingestion-version": "4"})
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.loads(response.read() or b"{}")
    if result.get("partialSuccess", {}).get("rejectedSpans", "0") not in (0, "0", None):
        raise RuntimeError("Langfuse partially rejected experiment spans")
    for offset in range(0, len(scores["batch"]), 100):
        batch = scores["batch"][offset:offset + 100]
        req = urllib.request.Request(base.rstrip("/") + "/api/public/ingestion",
            data=json.dumps({"batch": batch}).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Basic " + auth})
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.load(response)
        if result.get("errors") or len(result.get("successes", [])) != len(batch):
            raise RuntimeError("experiment traces accepted, but Langfuse rejected performance scores")
    print(json.dumps({"uploaded": True, "backend": "langfuse", "scores": len(scores["batch"])}))


def publish_langsmith(args):
    if not os.environ.get("LANGSMITH_API_KEY"):
        raise RuntimeError("configure LANGSMITH_API_KEY")
    from langsmith import Client
    client = Client()
    count = 0
    for run in load_runs(args.input):
        for row in run["records"]:
            historical = not row.get("started_at")
            start = datetime.fromisoformat(row["started_at"]) if not historical else datetime.now(timezone.utc)
            end = datetime.fromisoformat(row["completed_at"]) if not historical else start
            m = row["metrics"]
            extra = {"metadata": {"experiment": run["label"], "source": run["source"], "historical_import": historical,
                "phase": row.get("phase"), "mtp": run.get("mtp"), "telemetry": row.get("telemetry", {})}}
            if not historical:
                extra["metadata"].update(ls_provider="llama.cpp", ls_model_name=run["model"])
            events = []
            if not historical and m.get("ttft_s") is not None:
                events.append({"name": "new_token", "time": (start + timedelta(seconds=m["ttft_s"])).isoformat()})
            outputs = {"metrics": m, "quality": row.get("quality", {})}
            if not historical:
                outputs["usage_metadata"] = {"input_tokens": m.get("full_input_tokens"),
                    "output_tokens": m.get("output_tokens"),
                    "input_token_details": {"cache_read": m.get("cached_input_tokens", 0)}}
            client.create_run(id=uuid5(NAMESPACE_URL, run["run_id"] + row["id"]),
                name=row["case"], run_type="chain" if historical else "llm", project_name=args.project,
                start_time=start, end_time=end, events=events, extra=extra,
                inputs={"case": row["case"], "prompt_sha256": row.get("prompt_sha256")},
                outputs=outputs, tags=["latency-experiment", run["label"]])
            count += 1
    if hasattr(client, "flush"):
        client.flush()
    print(json.dumps({"uploaded": True, "backend": "langsmith", "records": count}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import-mtp")
    imp.add_argument("--source", type=Path, required=True)
    imp.add_argument("--output", type=Path, required=True)
    aud = sub.add_parser("audit-production")
    aud.add_argument("--since", required=True)
    aud.add_argument("--until", required=True)
    aud.add_argument("--hermes-home", type=lambda p: Path(p).expanduser().resolve(), default=Path.home() / ".hermes")
    aud.add_argument("--output", type=Path, required=True)
    status = sub.add_parser("status-langfuse")
    status.add_argument("--credentials", type=Path)
    for name in ("report", "publish-langfuse", "publish-langsmith"):
        command = sub.add_parser(name)
        command.add_argument("--input", type=Path, nargs="+", required=True)
        if name == "report":
            command.add_argument("--output", type=Path, required=True)
        elif name == "publish-langfuse":
            command.add_argument("--dry-run", type=Path)
            command.add_argument("--credentials", type=Path, help="private .env file with three Langfuse settings")
        else:
            command.add_argument("--project", required=True)
    args = parser.parse_args()
    if args.command == "import-mtp":
        runs = import_mtp(args.source)
        if not runs:
            parser.error("no completed matched MTP artifacts found")
        save(args.output, runs)
        print(json.dumps({"imported_experiments": len(runs), "output": str(args.output)}))
    elif args.command == "audit-production":
        audit(args)
    elif args.command == "report":
        report(args)
    elif args.command == "publish-langfuse":
        publish_langfuse(args)
    elif args.command == "status-langfuse":
        status_langfuse(args)
    else:
        publish_langsmith(args)


if __name__ == "__main__":
    main()
