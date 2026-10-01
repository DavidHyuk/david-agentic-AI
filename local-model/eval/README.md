# Local synthetic agent benchmark v2

`agent_suite_v2.py` deterministically builds `agent_cases_v2.json`, a
version-controlled suite of 120 synthetic cases: 30 each in `short_task`,
`multi_tool`, `long_horizon`, and `context_heavy`. The scenarios borrow themes
from papers, interview preparation, coding, English practice, and podcasts, but
contain no real tutor messages, Telegram history, private database rows, or
model-generated answers. Codex authored these synthetic cases and their expected
answers; they are not sampled Hermes traces or human-labeled ground truth.
Repeated templates, six scripted turns, generated filler, and required JSON
limit how well the suite represents real tasks. See the
[provenance and limits](../../docs/benchmarks/qwen36-vs-flashnext-v2-2026-09-30.md#dataset-provenance-and-representativeness).

This is a local API harness, **not** a live Hermes end-to-end benchmark. Tool
calls receive only scripted mock results; no helper, shell command, network
source, Telegram delivery, or Hermes state is invoked. Responses are parsed as
JSON (plain or one fenced JSON object) and scored against each case's expected
JSON subset. Object key order is ignored, expected list order is significant,
strings are compared after trimming outer whitespace, and extra response keys
are allowed. The explicit `{"$contains":"phrase"}` expectation instead checks
that a string contains the phrase case-insensitively; it is used where expanded
evidence quotes are valid. `{"$language":"ko"}` checks that a Korean summary
contains Hangul while companion factual fields are scored separately. This is
deterministic fixture scoring, not a general
semantic quality or safety judgment.

## Validate and run

Run validation before using the suite:

```bash
python3 local-model/eval/agent_suite_v2.py
python3 local-model/eval/benchmark_suite_v2.py validate
```

For manual runner commands, use the exact model ID advertised by each local
endpoint's `/models` route. Only the model for the current arm should be loaded and reachable.
Unload it before loading the next model on the same DGX Spark; sequential HTTP
requests alone do not prevent concurrent model memory allocation. Keep serving
configuration fixed during each run. These examples use the existing local
endpoints; adjust URLs and model IDs to match the services actually running:

```bash
python3 local-model/eval/benchmark_suite_v2.py run \
  --model Qwen3.8-Flash-Next-UD-IQ4_XS \
  --base-url http://127.0.0.1:8003/v1 \
  --run-label llama.cpp-64k \
  --output runtime/model-benchmarks/v2-qwen38.jsonl

# Unload Flash-Next, then load Qwen3.6 alone before running this command.
python3 local-model/eval/benchmark_suite_v2.py run \
  --model Qwen3.6-35B-A3B-FP8 \
  --base-url http://127.0.0.1:8004/v1 \
  --run-label vllm-64k \
  --output runtime/model-benchmarks/v2-qwen36.jsonl

python3 local-model/eval/benchmark_suite_v2.py summarize \
  --left runtime/model-benchmarks/v2-qwen38.jsonl \
  --right runtime/model-benchmarks/v2-qwen36.jsonl
```

Runner settings pin temperature to zero, `top_p` to one, and thinking off. The
run label records the engine and launch flags for the operator; the resume hash
also binds results to model ID, endpoint, runner version, and sampling settings.
The endpoint is checked against the requested model ID before inference. Ensure
each service context window can fit the largest requested context; target token
counts for generated context are estimates, not tokenizer measurements.

Each result row is flushed and fsynced before the next case. Re-running the same
command with the same output skips matching completed cases. The runner
rejects duplicate/corrupt rows and changed fixture or run identity. A failed
case remains in its result file; retry it into a new output file after resolving
the cause, rather than editing or deleting the recorded result. `--bucket`,
`--ids`, and `--limit` support focused runs; summaries compare only cases present
in both files and report completed and paired counts so partial runs are visible.

### One-command overnight run

After generating `agent_cases_v2.json` and confirming that the local production
Flash-Next endpoint is healthy, the orchestrator runs both benchmark arms and
restores the original service state on exit:

```bash
bash local-model/eval/run_overnight_v2.sh /home/david/workspace/David-Agent/runtime/model-benchmarks/2026-09-29-v2
```

Choose a unique final directory name for each run. The script requires an absolute path under the repository's
`runtime/model-benchmarks/` directory and takes a lock so the same run directory
cannot be used concurrently. It temporarily pauses the main and English
gateways and the cron watchdog, runs Flash-Next first, then stops it and runs
Qwen3.6 35B sequentially. An `EXIT` trap restores the Flash-Next production
service and restarts only gateways/watchdog that were active before the run.
The trap also runs after an error or interrupt; verify service status if the
host itself shuts down before the trap can complete.

The run directory is git-ignored and contains `orchestrator.log`, each model's
JSONL results, `summary.jsonl`, and a lock file. The benchmark is still a
nonproduction diagnostic: it temporarily interrupts gateway delivery and does
not exercise live Hermes workflows or real tools. Review service status and the
summary after the run; no performance result is implied by invoking the script.

## What the buckets measure

- `short_task`: one request and exact JSON subset checks for synthetic workflow
  facts.
- `multi_tool`: one task with at least two declared functions and an ordered,
  deterministic tool script. The harness checks tool names and parsed argument
  objects, requires dependent calls in separate model responses, returns only
  the next scripted result, then checks the final JSON.
- `long_horizon`: several user turns share the same conversation history, with
  state updates, interruption/retry checks, and a final state confirmation.
- `context_heavy`: a generated synthetic archive places multiple answer facts
  at specified positions among repeated filler and distractors. The target size
  is an estimate based on characters per token, not tokenizer-measured context.

The summary reports per-bucket case pass counts, paired wins/losses, errors,
p50/p95 client wall time, and prompt/completion token totals. Timing is paired by
case, but each case is run once per model; fixed order, runtime differences,
thermal state, and load can affect latency. Results compare served model/runtime
combinations, not model architecture in isolation, and are diagnostic rather
than statistically conclusive. This harness is for nonproduction evaluation:
it does not verify production behavior, run real tool implementations, or
justify switching a production model by itself. Runtime outputs belong under
git-ignored `runtime/`; label any interrupted run as partial and do not infer
results for missing cases.

## Separate blind semantic audit

After **both** 120-case result files are complete, create anonymous A/B material:

```bash
python3 local-model/eval/blind_judge_bundle_v2.py \
  --cases local-model/eval/agent_cases_v2.json \
  --left runtime/model-benchmarks/v2-qwen38.jsonl \
  --right runtime/model-benchmarks/v2-qwen36.jsonl \
  --salt 2026-09-30-agent-v2 \
  --bundle runtime/model-benchmarks/v2-blind.json \
  --mapping runtime/model-benchmarks/v2-sealed-mapping.json
```

The builder refuses incomplete or changed cases, balances A/B placement 60/60,
and removes model names, automatic scores, and timings from the bundle. Keep the
mapping sealed until judgments are saved. Apply [the frozen semantic rubric](judge_rubric_v2.md)
to each anonymous candidate independently, record uncertain cases, and repeat
boundary cases with reversed order. This audit is a separate, uncalibrated
LLM-as-judge estimate; it does not replace deterministic tool/field checks or
human calibration.

If a host shutdown leaves a run incomplete, use `--allow-partial` to build a
bundle from only case IDs present in **both** result files. The sealed mapping
then records every excluded ID and balances anonymous A/B placement over the
paired subset. Report the denominator by bucket and leave missing outcomes
unknown; a partial audit must not be presented as a 120-case comparison. The
default remains fail-closed on any missing result.

## Supervised retry after the September 30 host reset

Preserve the original 120 Flash-Next and 92 Qwen3.6 rows. Inspect previous/current
boot journals, host memory and pressure, swap, GPU processes/temperature, and
service state before a retry. The reset has no established cause; cgroup memory
caps and launch changes do not guarantee prevention. Do not use the full
120-case overnight orchestrator as the first retry after this incident.

Pause gateway traffic and the cron watchdog, prevent automatic model restarts,
and verify the production model is fully unloaded before loading Qwen3.6.
Start with a short request, then individual `context_00`, `context_01`,
`context_02`, and `context_03` cases (approximately 8K, 24K, 40K, 55K targets),
using `--ids` and a fresh output path. Inspect resources and server/kernel logs
between stages; stop on new GPU allocation/Xid errors, memory pressure, server
exit, timeout, or invalid smoke transport/response. A valid response that fails
the task rubric is an accuracy result: record it and continue when health and
resource checks permit. Restore Flash-Next, verify its `/models`
endpoint, and restore prior gateways/watchdog even on an aborted run.

The October 1 retry uses a separate run label and directory because eager
execution, concurrency, and prefill batch limits differ. Never append its rows
to the original `qwen36.jsonl`; report the retry independently, with any missing
cases and configuration changes visible. A completed retrieval retry does not
resolve the original missing pairs or establish production reliability.

The completed governed run used explicit 8 GiB BF16 KV, context 65,536, eager
execution, prefix caching off, one sequence, 512-token prefill batches,
language-only mode, a one-CPU quota, and thermal pause/resume controls. It
completed 120 cases with 72 passes and all 290 server phase records. Runtime
launch commands, telemetry and pause logs are retained separately; see the
[comparison report](../../docs/benchmarks/qwen36-vs-flashnext-v2-2026-09-30.md).
Thermal pauses are included in request timings. Production settings are restored
after testing; these diagnostic controls are not a general prevention claim.
The subsequent Flash audit removed pauses and cooldowns at user request, with
2-second health checks and 15-second kernel checks. It measured 15 cases /
50 requests, then stopped on observed thermal slowdown in the first context
request. Preserve that partial scope rather than combining it with governed
Flash timings or the original full Flash score.

## TTFT and phase throughput

Runner 2.3 retains client TTFT and records per-request performance in each
trace. For an isolated vLLM server, add its metrics endpoint:

```bash
python3 local-model/eval/benchmark_suite_v2.py run \
  --model Qwen3.6-35B-A3B-FP8 --base-url http://127.0.0.1:8004/v1 \
  --server-metrics-url http://127.0.0.1:8004/metrics \
  --run-label 'describe the fixed serving flags here' \
  --output runtime/model-benchmarks/new-metrics-run/qwen36.jsonl
```

Use a **fresh output**: runner-version and metrics-endpoint changes are part of
run identity. Original 2.2 results stay untouched and can still be summarized.
This flag only collects telemetry; it does not start, stop, or isolate services.

- Client TTFT is request start to the first nonempty streamed content. Tool
  requests currently use nonstreaming responses, so their client TTFT is absent;
  vLLM server TTFT is still measurable for these requests.
- vLLM server prefill time spans initial scheduling to the first output token;
  decode time spans the first to last output token. Prefill TPS uses newly
  computed KV tokens when that histogram is available, otherwise total input
  tokens (with the basis recorded), divided by server prefill seconds; decode TPS is `(generation_tokens - 1)`
  divided by server decode seconds. Server TTFT also includes server-side queue
  time. These phase times can include scheduling/preemption, not just GPU kernel
  time. The benchmark uses one request at a time and no other clients.
- Histogram differences are attributed only when every required count advances
  by exactly one. Missing, reset, or concurrent telemetry is marked unavailable;
  exporter errors do not turn a valid task into a failed inference. Metric
  collection time is recorded separately and excluded from case wall time.
- llama.cpp native `timings` are retained from streaming/nonstreaming responses,
  with its prompt/decode rates, cache count, and **actually processed** prompt
  tokens. Native prefill rates may use fewer tokens than total input when a
  prompt prefix is cached. Compare engines with those definitions visible.
- Client `prompt_tps_ttft_estimate` includes network, queuing, and tokenization;
  it is not pure prefill TPS. `decode_tps_estimate` uses client stream duration
  and is kept distinct from measured server phase throughput.

Summaries include per-bucket request counts, server-metric coverage, median
client/server TTFT, and median server prefill/decode TPS. Counts are requests,
not cases: a six-turn case and a tool chain contain multiple requests. Keep
accuracy, task latency, phase throughput, and stability separate, and report
cold/warm/cache/cooling conditions. See the
[vLLM cache configuration](https://docs.vllm.ai/en/v0.19.1/api/vllm/config/cache/)
for the explicit KV-byte budget; setting it overrides utilization-based KV
sizing and does not guarantee total host/GPU memory safety.
