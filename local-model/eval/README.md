# Local synthetic agent benchmark v2

## Interactive coaching latency and experiment tracking

See the [Langfuse first-use guide](../../docs/langfuse-quickstart.md) for Cloud signup,
private credentials, UI navigation and numeric score comparisons. Use
`--input-tokens 2048 --label coaching-compact-2k` to repeat the short coaching
cases with a smaller synthetic payload; this does not cap real agent history.


`interactive_latency.py` measures four synthetic coaching cases: a short coding
hint, English correction, coding explanation and English drill. It uses the
existing llama.cpp HTTP API, verifies **128K per request and two slots**, and
requires production MTP OFF. It never invokes Hermes tools, updates an agent,
restarts a provider or delivers Telegram messages.

```bash
python local-model/eval/interactive_latency.py --repetitions 3 --concurrent \
  --output runtime/model-benchmarks/interactive-coaching.json
python local-model/eval/experiment_tracker.py import-mtp \
  --source /home/david/.local/share/clawgram/diagnostics/mtp-comparison \
  --output runtime/model-benchmarks/mtp-matched.json
python local-model/eval/experiment_tracker.py audit-production \
  --since '2026-10-03 23:15:00 UTC' --until '2026-10-04 04:26:00 UTC' \
  --output runtime/model-benchmarks/production-latency.json
python local-model/eval/experiment_tracker.py report \
  --input runtime/model-benchmarks/interactive-coaching.json \
    runtime/model-benchmarks/mtp-matched.json runtime/model-benchmarks/production-latency.json \
  --output runtime/model-benchmarks/latency-dashboard.html
```

Choose a log interval ending before the synthetic experiment so production
statistics do not include benchmark calls. The journal importer only accepts
the current MTP-OFF provider PID and complete, untruncated timing records.
It reconstructs full context from slot release and separates cached tokens
from newly processed tokens. Server logs do not establish client TTFT,
delivery latency, request concurrency or which coach issued a call.

The coaching fixture sizes 20K coding and 16K English contexts with the actual
server tokenizer. These are test scenarios anchored by approximately 20K cron
usage and the earlier 16K benchmark, not measured interactive percentiles or
an assertion that English uses less context. Context is fictional archive filler, not private learner history
or real tools. Each case gets three independently seeded repeats, a prompt-cache
cold call and one followup reusing the preceding generated answer. Cold means
an uncached prompt on an already loaded model, not process startup. Cache reuse
is checked from server timing counters. The overlap test sends coding and
English requests into separate slots simultaneously. It does not measure two
warm conversations competing for cache or production queue percentiles.

Output limits are 256, 512 and 384 tokens. Inspect `output_limit_reached` before
calling a run a completed answer: capped explanations can be unfinished.
Quality checks establish nonempty text and Korean presence, not instructional
correctness. Only token counts, hashes, timing and aggregate host telemetry are
saved. No prompts, generated answers, photos or learner identifiers are exported.

Before each sample, the harness waits for idle scheduler metrics, at least 24GiB
MemAvailable, 8GiB MemFree and 8°C GPU thermal margin. The waits are excluded
from request latency. These entry checks cannot prevent later thermal
throttling or unrelated traffic. Memory, GPU temperature/margin, thermal flags
and scheduler state are sampled about once per second. GB10 uses unified
memory: reported GPU allocation overlaps physical host memory, so do not add
them. A single run with three repeats does not establish p95 or thermal
equivalence across configurations. Full 128K endurance is untested.

The [2026-10-03 report](../../docs/benchmarks/interactive-coaching-latency-2026-10-03.md)
contains the measured cold/warm and overlap results, MTP comparison, frontend
streaming audit, and tracker recommendation. This is an internal evaluation
helper with no new Observatory room, profile, schedule or messaging workflow.

### Optional tracker export

**Langfuse is recommended for these cross-framework model/agent experiments.**
Its [OpenTelemetry experiment ingestion](https://langfuse.com/integrations/native/opentelemetry/experiments)
accepts stable local dataset identifiers and per-item traces. This standard-library
exporter prepares direct OTLP/HTTP JSON without adding an SDK dependency:

```bash
python local-model/eval/experiment_tracker.py publish-langfuse \
  --input runtime/model-benchmarks/interactive-coaching.json \
    runtime/model-benchmarks/mtp-matched.json runtime/model-benchmarks/production-latency.json \
  --dry-run runtime/model-benchmarks/langfuse-otlp.json
```

To upload, configure `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY` and
`LANGFUSE_SECRET_KEY` privately, then omit `--dry-run`. The exporter targets
`/api/public/otel/v1/traces` with the v4 ingestion header and rejects reported
partial ingestion failures. Live ingestion is untested until a project is
configured. Local dry runs require no credentials and perform no network calls.
New measurements use actual request timestamps and first-token times.
Historical records without request starts become zero-duration import spans;
their measured timings remain metadata and numeric performance scores rather
than invented trace durations. Import timestamps use artifact recording times.
The exporter also writes `.scores.json` in dry-run mode and sends supported
score-create batches after OTLP ingestion. Missing client timings are omitted.
Use `--credentials ~/.config/david-agent/langfuse.env` to load a private settings
file without putting keys in shell commands.

[LangSmith](https://docs.langchain.com/langsmith/log-llm-trace) also supports
TTFT and token accounting and fits existing ClawGram LangGraph evaluations.
Its optional fallback exports tagged traces, not dataset-backed experiment runs:

```bash
python local-model/eval/experiment_tracker.py publish-langsmith \
  --input runtime/model-benchmarks/interactive-coaching.json --project coaching-latency
```

This needs the `langsmith` SDK and privately configured `LANGSMITH_API_KEY`.
Neither tracker is a prerequisite for the offline dashboard. The existing
ClawGram aggregate exporter and agent independence remain intact.

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

### Relaxed Flash follow-up and pause-excluded Qwen timing

The next Flash run uses all 120 cases with normal production flags. An in-flight
request is never paused or cancelled solely for temperature, margin, or thermal
throttling. At 88°C or above, wait before starting the next case until 84°C;
record this wait outside case timings. Keep GPU/kernel-error and severe memory
pressure checks. Preserve earlier output files and give this control policy a
new run label. Results and restoration are in the comparison report.

For the completed Qwen run, retain raw elapsed time and separately subtract
logged stage pauses for active case time. Phase-specific subtraction requires
absolute request/first-token/end times; the old logs do not have them. The
report therefore reconstructs context pause overlaps using UTC supervisor
samples, labels these values as estimates, and stores sensitivity intervals.
Do not treat a duration-minus-pause calculation as an unconstrained rerun or
subtract all pauses from prefill when a pause occurred during decode.

The completed relaxed Flash retry measured all 120 cases / 338 requests, with
110 deterministic passes (context 30/30), maximum sampled 87°C, and zero
process pauses or between-case cooldowns. See the report's opening tables for
both full runs, both-pass task latency, long-context phase throughput, raw
observations, and Qwen pause-excluded reconstruction limitations.

## Bounded CPU diagnostics after the October 3 reset

Use `guarded_diagnostic.py` for CPU-only metadata inspection. It creates a
separate systemd cgroup with a hard RAM limit, no swap, a runtime limit and
fsynced telemetry. It refuses launch below 12 GiB available-memory headroom.
The parent stops only its own diagnostic; it never signals the production model.
This is not containment for GPU/model workloads or protection from kernel and
firmware failures. Do not repeat unbounded GGUFReader inspection while serving.

`gguf_metadata.py` reads selected metadata and optional tensor descriptors with
standard-library streaming I/O. It skips tokenizer contents, never maps tensor
payloads, and rejects oversized/truncated headers. Run with a fresh output path:

```bash
python3 local-model/eval/guarded_diagnostic.py \
  --output-dir runtime/model-benchmarks/header-check-NEW \
  --memory-mib 128 --seconds 60 -- \
  /usr/bin/python3 local-model/eval/gguf_metadata.py \
  --tensor-summary /absolute/path/model.gguf
```

Multiple shard paths are accepted. The JSON includes selected PLE tensor shapes
and numeric GGML types, without reading their values. See the
[October 3 incident and diagnosis](../../docs/benchmarks/flash-prefill-diagnostic-incident-2026-10-03.md)
for the bounded reproduction, corrected distinction between speculative n-gram
and model-internal PLE hashing, and remaining performance-attribution limits.
