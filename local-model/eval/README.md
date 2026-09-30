# Local synthetic agent benchmark v2

`agent_suite_v2.py` deterministically builds `agent_cases_v2.json`, a
version-controlled suite of 120 synthetic cases: 30 each in `short_task`,
`multi_tool`, `long_horizon`, and `context_heavy`. The scenarios borrow themes
from papers, interview preparation, coding, English practice, and podcasts, but
contain no real tutor messages, Telegram history, private database rows, or
model-generated answers.

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
endpoint's `/models` route. Both models must already be served and reachable.
Run them one at a time on the same DGX Spark, keeping their serving
configuration fixed during each run. These examples use the existing local
endpoints; adjust URLs and model IDs to match the services actually running:

```bash
python3 local-model/eval/benchmark_suite_v2.py run \
  --model Qwen3.8-Flash-Next-UD-IQ4_XS \
  --base-url http://127.0.0.1:8003/v1 \
  --run-label llama.cpp-64k \
  --output runtime/model-benchmarks/v2-qwen38.jsonl

# Run after the first command finishes; use the second already-served endpoint.
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
