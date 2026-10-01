# Qwen3.6 35B vs Flash-Next: original 92 pairs and separate completed 120-case runs

Original run: 2026-09-30; separate diagnostic retries and relaxed Flash run: 2026-10-01.
One DGX Spark (GB10), kernel `6.14.0-1015-nvidia`.

## Completed October 1 comparison (separate full runs)

Both new arms completed all **120 cases**. Flash uses normal production serving
flags, no process pauses, no in-flight temperature abort, and a between-case
cooldown only if temperature is at least 88°C (resume new cases at 84°C).
Qwen uses the diagnostic configuration below; its active times subtract logged
thermal waits, and its phase-specific active values are reconstructed estimates.
Neither new arm is appended to the original September 30 files.

| Bucket | New Flash pass | New Qwen pass | Flash median case time | Qwen median case time minus logged stage pauses |
| --- | ---: | ---: | ---: | ---: |
| Short task | 30/30 | 25/30 | 1.91 s | 1.71 s |
| Multi-tool | 26/30 | 6/30 | 5.17 s | 2.21 s |
| Six-turn conversation | 24/30 | 12/30 | 11.36 s | 10.26 s |
| Context-heavy | 30/30 | 29/30 | 37.89 s | 10.62 s |
| Total | **110/120 (91.7%)** | **72/120 (60.0%)** | — | — |

These percentages are deterministic synthetic-fixture passes, not production
accuracy. All-case latency includes failed tasks, particularly Qwen tool
shortcuts. Successful-work latency uses only case IDs where both new arms pass:

| Bucket | Both-pass pairs | Flash median case time | Qwen median case time minus stage pauses |
| --- | ---: | ---: | ---: |
| Short task | 25 | 1.81 s | 1.70 s |
| Multi-tool | 5 | 5.56 s | 5.34 s |
| Six-turn conversation | 12 | 11.52 s | 10.62 s |
| Context-heavy | 29 | 38.00 s | 10.68 s |

### Long-context TTFT, prefill and decode without explicit pause waits

Medians over all cases at each target size (8/8/7/7 cases). Flash is measured;
Qwen values marked ≈ subtract reconstructed process-pause overlap. Exact
method and sensitivity limitations are below; these are not two unconstrained
runs with identical serving controls.

| Target | Qwen TTFT | Flash TTFT | Qwen prefill TPS | Flash prefill TPS | Qwen decode TPS | Flash decode TPS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 8,192 | ≈2.82 s | 11.67 s | ≈2827 | 708 | ≈26.4 | 26.6 |
| 24,576 | ≈8.47 s | 35.51 s | ≈2788 | 663 | ≈25.7 | 25.0 |
| 40,960 | ≈14.48 s | 63.39 s | ≈2704 | 618 | ≈26.5 | 22.9 |
| 55,296 | ≈19.67 s | 89.44 s | ≈2689 | 590 | ≈25.4 | 21.1 |

Flash native prefill TPS uses actually processed tokens. Median cached input
is 49 tokens in each long-context group, versus median total inputs around
7,900 / 23,456 / 38,974 / 52,564. The new Flash run retains a warm server and
its normal caches; it is not a cold-start experiment. Decode excludes the
first generated token. Tool requests remain nonstreaming, so client TTFT is
unavailable for those requests rather than invented.

### Stability and final restoration

Flash completed **338/338 requests with native phase timings**, no runtime
errors, no reset, **zero forced pauses**, and **zero between-case cooldowns**.
Maximum sampled GPU temperature was **87°C**, minimum reported margin **−6°C**,
and 572 samples indicated thermal slowdown. Those observations were recorded
without cancelling requests. Host available memory reached **6.48 GiB**, with
memory-full PSI `avg10` **0.00** and no new GPU allocation/Xid error.
Thermal throttling remains part of measured Flash performance; there is no
explicit cooling wait to subtract. Qwen's 637.59 seconds of process pauses are
separated in the active-time analysis, while CPU quota remains a confounder.

The result directory is
`runtime/model-benchmarks/2026-10-01-flash-88c-between-cases/`; it retains policy,
full launch/supervisor script, selection, original/final service states,
telemetry, raw results and `run-summary.json`. Full Flash result SHA-256:
`324124c1d56570d199aff7e6b1c0925ab558d5b25a529d198f0691a023f86c02`.
Production Flash, main/English gateways, and cron watchdog are restored and
active. ClawGram retains its pre-existing Qwen readiness mismatch and remains
`activating/start-pre`. Production launcher/profile settings were not changed.

The completed relaxed Flash run demonstrates that the earlier conservative
thermal stop was not necessary to finish this fixture. It does not identify
the earlier host reset's cause or guarantee future reliability. Fixture
correctness favors Flash, while Qwen's pause-excluded long-context estimates
show substantially shorter prefill/TTFT in these different served stacks.
This supports keeping Flash for the present tool/state workload, not a claim
of general model superiority or real Hermes production accuracy.

## Assessment of the original run

Three buckets finished with 30 paired cases each. Flash-Next had higher fixture
pass counts on this synthetic serving-layer suite; Qwen3.6 was about twice as
fast on the short and six-turn tasks. The original long-context comparison is **incomplete**: the
host stopped after only two of Qwen3.6's 30 context cases. These results do
not isolate model architecture from engine, quantization, or tool parser.
A subsequent **separate** Qwen3.6 configuration completed all 120 cases on
October 1; see the diagnostic results below. It does not fill the original
run's missing rows or inherit its blind semantic judgments.

| Bucket | Pairs | Deterministic pass: 3.6 / Flash | Blind semantic pass: 3.6 / Flash | Median client time: 3.6 / Flash |
| --- | ---: | ---: | ---: | ---: |
| Short task | 30/30 | 25 / 30 | 28 / 29 | 0.94 / 1.96 s |
| Multi-tool | 30/30 | 3 / 26 | 0 / 18 | 1.24 / 5.12 s* |
| Long-horizon | 30/30 | 10 / 24 | 15 / 24 | 5.55 / 11.83 s |
| Context-heavy | **2/30** | 2 / 2 paired | 2 / 2 paired | 3.83 / 26.41 s (2 pairs only) |

Across the three **complete** buckets, deterministic success was 38/90 for
Qwen3.6 and 80/90 for Flash-Next. The first blind semantic judge provisionally
passed 43/90 and 71/90. Excluding all 12 cases flagged uncertain by either
judge gives 36/78 and 61/78 respectively. These are case counts, not an
independent-sample accuracy estimate: scenario patterns repeat across cases.

\*The multi-tool median is not a like-for-like successful-work speed measure.
Qwen3.6 made **no tool call in 21/30** cases, while Flash-Next made at least one
in 30/30. Only three Qwen3.6 and 26 Flash-Next cases passed the deterministic
tool sequence; the three successful Qwen3.6 cases took 2.92–2.97 s. Faster
failed shortcuts must not be counted as a speed win. The semantic judge also
treated Markdown-fenced final JSON as a JSON-only format failure, whereas the
deterministic parser accepts a single JSON code fence; that policy difference
explains some disagreement in absolute scores, including the three Qwen3.6
tool-sequence successes. Both metrics and their definitions are retained.

## What was run

The version-controlled [fixture](../../local-model/eval/agent_cases_v2.json)
contains 120 synthetic cases authored by Codex (four buckets × 30), not sampled
from actual Hermes usage logs and not labeled with correct answers by humans.
It contains 30 cases each for short factual/planning tasks, dependent
mock-tool workflows, six-turn stateful conversations, and long-context fact
retrieval. It does not execute real Hermes tools, Telegram, or user data.
Flash-Next was served by llama.cpp with IQ4_XS weights and two 64K slots;
Qwen3.6 35B A3B used FP8 weights under vLLM at 64K maximum sequence length,
`gpu-memory-utilization=0.50`, and an 80 GiB service memory cap. Models were
run sequentially with the gateways paused. Requests used temperature 0,
`top_p=1`, thinking disabled, and `tool_choice=auto` when tools were available.
The Qwen3.6 server used its configured `qwen3_coder` tool parser; tool-calling
performance here is therefore a served-stack result, not proof of intrinsic
model capability. Each case was sampled once. Median time is client wall time
for **all** completed cases, including failures.

The deterministic score requires the reference JSON subset and exact scripted
tool branch, arguments, and dependency order. The separate
[frozen blind rubric](../../local-model/eval/judge_rubric_v2.md) scores meaning,
grounding, required actions, and format, independently for anonymous A and B.
The [bundle builder](../../local-model/eval/blind_judge_bundle_v2.py) stripped
model names, automatic scores, and timings and balanced A/B positions 46/46
over the 92 paired cases. A second blind reviewer judged 22 selected cases in
reverse candidate order: all first-review uncertain cases plus an unselected
random spot check. Across the 92 paired cases, **12/92 were flagged uncertain**
by either reviewer; all 12 fall in the three complete buckets. Seven case-level judgments
differed, all on cases marked uncertain. Six repeated interview cases ask for a
follow-up question but restrict JSON output to a follow-up count; other uncertain cases have similar
instruction/schema ambiguities. The primary table retains the first review;
the 78-case sensitivity count excludes uncertain cases instead of selecting
whichever judgment favors a model. This is **uncalibrated LLM-as-judge**, not
human-labeled ground truth. The blinding, fixed task rubric, and second review
follow [OpenAI's evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
and [agent trace-grading guidance](https://developers.openai.com/api/docs/guides/agent-evals).

## Dataset provenance and representativeness

Codex wrote the scenario generator, synthetic inputs, scripted tool outputs,
and expected JSON answers. Workflow names were inspired by this project's
papers, interview, coding, English, and podcast capabilities; they are thematic
proxies, not a sample of David's requests. The equal 30-case bucket allocation
was chosen for diagnostics and does not reflect production task frequencies.
The fixture's programmed answers and uncalibrated LLM judgments are not
human-verified ground truth.

| Suite construction | Difference from actual Hermes work |
| --- | --- |
| Mock tools with fixed branches, arguments, dependency order, and responses | No real filesystem, database, browser, network, Telegram side effects, permissions, latency, partial failures, or recovery. Alternative valid tool strategies can fail the scripted check. |
| Repeated scenario templates with substituted facts and branch variants | Cases are correlated and cover a narrow vocabulary and structure. 120 rows do not represent 120 independent real tasks or broad coverage. |
| Six scripted turns labeled `long_horizon` | Tests brief in-session state updates. Does not test days of interaction, persistent memory, compaction, asynchronous cron/user interruptions, or extended autonomous execution. |
| Generated long archives containing repeated filler, positioned `FACT` entries, and synthetic distractors | Primarily controlled fact retrieval, not heterogeneous papers, code, tutor messages, tool traces, source conflicts, or realistic multi-document reasoning. Target token counts are approximate. |
| Required final JSON and exact reference subset | Easier to score, but ordinary coaching, summaries, explanations, and Telegram conversations are usually prose. Counts format compliance alongside task correctness and omits human usefulness; fenced-JSON policies also differ between the deterministic and semantic judges. |

The 12/92 ambiguous judgments include instruction/schema conflicts; the
sensitivity analysis cannot make the remaining cases representative. The
original context-heavy comparison has only **2/30 completed pairs**, with
28 missing Qwen3.6 outcomes. Those missing outcomes cannot be assumed correct,
incorrect, or equivalent to the completed small-context cases.

Consequently, these scores are pass counts for this synthetic fixture and
served configuration. They are **not production accuracy**, a forecast of
David's task success rate, or evidence of universal model superiority. Engine,
quantization, tool parsing, evaluator design, and schema choices remain mixed
with model behavior.

## Interruption and missing data

The durable Qwen3.6 result file has 92/120 rows; its last completed case is
`context_01` (24K-token target). The next scheduled case targeted 40K tokens,
but there is no durable response for it. The previous boot journal stops
abruptly at 09:14:22 PDT and the next boot begins at 09:28:18; no orderly
shutdown was logged. At 09:13:42 the telemetry file showed about 51 GiB
`MemAvailable`, 15.3 GiB free swap, and memory-full PSI `avg10=0.00`.
No contemporaneous OOM, GPU Xid, kernel panic, memory-guard trip, pstore
record, or vmcore was found. There was an earlier NVIDIA allocation warning
during model loading, but not at the stop. The evidence does **not** establish
whether inference, driver, kernel, power, or another host issue caused the
reset; it does not support calling this a simple RAM exhaustion. The
orchestrator log has a torn/NUL tail, so the fsynced JSONL results, not its
last printed line, establish progress.

Flash-Next completed all 30 context cases deterministically, including 40K
and 55K target prompts. Qwen3.6 completed only the 8K and 24K cases, so no
long-context accuracy ranking is defensible. A further Qwen3.6 stress run
was **not** automatically restarted after the hard reset. Production
Flash-Next, both gateways, and the cron watchdog were restored and active.

## Reproducibility and limitations

- Fixture SHA-256: `73a31af88ca4a686463269502044a73acc6da7b76f9d315fb928f304a981c3d2`.
- Rubric SHA-256: `eb7005fc240b787d2fd00cd86ef857b96ff910158dbf237b8f8be44cbc9bf2fa`.
- Local ignored artifacts: `runtime/model-benchmarks/2026-09-30-v2-final/`
  (`flash-next.jsonl`, `qwen36.jsonl`, `blind-partial.json`, sealed mapping,
  judge files, telemetry, and orchestrator log). The Qwen3.6 output has 92
  rows; the Flash-Next output has 120.
- The suite is synthetic, once-per-case, fixed-order, and engine/quantization
  confounded. Context target sizes are approximate, not identical tokenizer
  lengths. The rubric was frozen before Qwen3.6 outputs were seen, but after
  a Flash-Next pilot, so evaluator-design bias cannot be excluded. No live
  Hermes end-to-end task or human calibration was performed.

## October 1 supervised retry: stopped before long-context inference

This is a **separate run**, not a continuation of the original 92 rows. On
October 1 at 04:28 PDT, Flash-Next and the main/English gateways were running;
the cron watchdog timer was active. Only about 6.9 GiB of host memory was
available with Flash-Next loaded. The GB10 reports no total/free GPU-memory
value through `nvidia-smi`; its process list showed only the production
`llama-server` as a compute process. Previous-boot logs and the final telemetry
were rechecked: no terminal OOM-kill, Xid, or panic was recorded. Earlier NVIDIA
allocation failures were present at loading times, including 09:00:50 before
the 09:14:22 stop. The current boot also had a loading-time allocation warning
at 09:29:45 on September 30. These do not establish the reset's cause.
The original pstore/dump finding above is from the previous investigation;
pstore could not be rechecked in this session because access was denied and
passwordless sudo was unavailable. No new reset-prevention guarantee is made.

Gateways and the watchdog were paused with temporary runtime start guards.
Flash-Next was stopped and its GPU process absence verified before Qwen3.6
loaded. Qwen3.6 used vLLM `0.19.0+cu130`, FP8 weights, 65,536 maximum sequence
length, `gpu-memory-utilization=0.50`, automatic KV dtype, prefix caching,
`qwen3_coder`, and thinking/MTP disabled. Compared with the original run,
`--enforce-eager`, `--max-num-seqs 1`, and `--max-num-batched-tokens 2048` were
added, with `MemoryMax=80G` and `MemorySwapMax=2G`. These are temporary
benchmark overrides; production configuration was not edited.

The plan gated a short request, then 8K/24K/40K/55K target contexts before the
remaining context cases. Resource checks ran approximately every 2–3 seconds,
with stops for available memory below 16 GiB, memory-full PSI `avg10` above
1.0, free swap below 14 GiB, GPU temperature at least 80°C, new kernel GPU
allocation/Xid/OOM/panic errors, server exit, request timeout, or a failed
smoke. Such checks and caps cannot prevent all driver/kernel/power failures.

At 04:36 PDT, the first `short_00` request returned valid JSON in **6.953 s**
with no transport/runtime error, but failed the deterministic subset check.
It translated the evidence into Korean, while `$contains` required the English
phrase `21% fewer KV bytes`; the original Qwen3.6 row failed the same check,
although the original blind semantic audit passed it. Selecting this known
format-sensitive item as a strict smoke gate was inappropriate. The response
is not evidence of memory failure or long-context failure. The gate nevertheless
stopped this run and restored production before any context request. Its lone
cold, deterministically failed request is not a speed comparison or an accuracy
estimate.

A replacement numeric/boolean smoke was prepared, but **not launched**:
restoring Flash-Next caused swap use to rise to about 9–10 GiB, transient memory
pressure, and a fresh NVIDIA `NV_ERR_NO_MEMORY` allocation warning at 04:38:13.
That warning occurred during Flash-Next restoration, not Qwen3.6 context
inference. Further model switching was stopped because these were resource
risk signals. The host did not reboot during this attempt, but this does not
establish stability at 40K/55K or explain the previous reset.

Flash-Next `/health` and `/v1/models` were verified after restoration; the
main/English gateways and watchdog timer are active, the benchmark server is
stopped, and temporary guards were removed. ClawGram was already stuck in
`activating/start-pre` before this work and remains there: its readiness check
expects Qwen3.6 on the Flash-Next endpoint. That pre-existing external-service
mismatch blocked the restoration script's sequential start client; the
watchdog was restored separately and the blocking client ended, without
changing ClawGram configuration. It is not reported as a healthy gateway.

Artifacts are git-ignored under
`runtime/model-benchmarks/2026-10-01-qwen36-eager-staged/`: fresh
`qwen36-eager.jsonl` (one short row, **zero context rows**), serving overrides,
supervisor/server logs, resource telemetry, boot/kernel evidence, original
service states, and restoration notes. The prepared
`2026-10-01-qwen36-eager-context/` directory is marked `NOT-RUN.txt` and contains
no inference results. Original result SHA-256 values were verified unchanged:

- Flash-Next 120 rows: `15d26d3a50541ae98384b717aeb7fc89f7bcd6c5c5d38d0114225dfce45d3bd7`.
- Qwen3.6 92 rows: `4f4ab4d39724665dfd8d2f051fe2ab225ed3b41aa126571c3ab73bb77a696705`.

## Subsequent October 1 KV and thermal diagnostics

The user requested further diagnosis and actual TTFT, prefill TPS, and decoding
TPS measurements. All subsequent directories are separate runs; none appends
to the original 92-row Qwen3.6 file or the earlier stopped smoke.

### What the evidence does and does not identify

The September 30 interrupted server logged **19.92 GiB** of available KV budget,
**260,832 cache tokens**, and **2.8% KV usage** in its final throughput log.
The earlier October 1 eager/prefix-on server had 20.44 GiB and 267,168 tokens.
Neither log suggests ordinary KV-pool saturation at that point. The original
reset remains unexplained: the final log precedes the unrecorded outcome of the
40K request, and cannot rule out a later transient allocation, kernel, driver,
power, or thermal failure.

Before switching again, `/proc/*/status` attributed 9,373,768 KiB of swapped
pages to the restored Flash-Next `llama-server`. Most swap was freed when that
process was stopped. This distinguished existing production-model swap from
new Qwen3.6 inference pressure. Unused pages of the unloaded model's weight
files were discarded with `posix_fadvise(DONTNEED)` before switching back;
no files or unrelated caches were deleted. GPU allocations are not fully
represented by the service's cgroup memory peak on this unified-memory host,
so host availability, swap changes, pressure, and GPU process state were also
monitored.

Three configurations progressively narrowed the problem:

| Separate directory under `runtime/model-benchmarks/` | Observation |
| --- | --- |
| `2026-10-01-qwen36-kv8-noprefix/` | Explicit 8 GiB BF16 KV pool, eager, prefix off, language only, one sequence, 1024-token prefill batches. Short smoke and 8K/24K/40K targets passed. A conservative 80°C guard stopped the 55K request without a durable response; no memory pressure, KV saturation, Xid, or host reset was observed. |
| `2026-10-01-qwen36-kv8-cooled-metrics/` | Added phase measurement and cooldown between cases. Short smoke and 8K/24K passed with server metrics; a temperature-limit margin guard stopped the 40K request. Memory availability remained about 65 GiB and memory-full PSI was zero. |
| `2026-10-01-qwen36-kv8-governed-metrics/` | Reduced prefill batch to 512, applied `CPUQuota=100%` (one aggregate CPU), cooled before cases, and paused/resumed the engine as temperature-limit margin decreased. First 8K/24K/40K/55K targets passed with complete server phase measurements. Full-run results are recorded separately below. |

The explicit 8 GiB pool advertised **104,544 cache tokens**, and 64K requests
fit at startup. `kv-cache-memory-bytes` overrides utilization-based KV sizing;
`gpu-memory-utilization=0.50` is not an additional total-memory cap in this
mode. This behavior was verified in installed vLLM code/startup logs and the
[vLLM cache documentation](https://docs.vllm.ai/en/v0.19.1/api/vllm/config/cache/).
Weights remain FP8 and KV remains automatic/BF16; KV quantization was not used.

The observed constraint in these retries was thermal margin under sustained
prefill, rather than exhausted memory. An initial fixed 80°C stop was overly
conservative without device-specific margin information. The subsequent
margin guard also ended a run even though thermal slowdown was not active.
GPU clock limiting was attempted but denied by driver permissions; no clocks
were changed. The final diagnostic therefore used smaller work batches and
adaptive pauses instead of raising a stop threshold and proceeding unchecked.
It pauses when margin is at most 15°C or GPU temperature reaches 74°C, resumes
at at most 65°C with at least 25°C margin, and aborts on margin at most 2°C,
thermal slowdown, GPU/kernel errors, material new swap growth, or host memory
pressure. The pauses and their durations are saved separately. This is an
operationally constrained configuration, not a claim that temperature caused
the old reboot, that another flag was responsible, or that reboot prevention
is guaranteed.

### Measurement definitions

Runner 2.3 preserves per-request client TTFT and separates server phase rates
from client estimates. vLLM metrics are differences of request histogram
sums/counts before/after one isolated request, with newly computed KV tokens
used when exported. Prefill time is initial scheduling to first output token;
decode time is first to last output token, with `(generation_tokens - 1)` in
the decode-rate numerator. These times include scheduling/preemption and
thermal pauses. They are not pure GPU kernel durations. Metric-exporter
failures are labeled unavailable and never counted as task failures; exporter
query time is excluded from case wall time.

llama.cpp native timings preserve processed prompt tokens, cached tokens,
prompt/decode seconds, and native rates. Its cached-prefix work must be visible
when comparing prefill TPS. Client TTFT spans request start to first streamed
content; current nonstreaming tool requests have no client TTFT, whereas vLLM
server TTFT is still available. The paired original results contain client
TTFT but no retained native phase timings, so pure server TPS cannot be
retroactively invented from their wall time. See
[measurement usage](../../local-model/eval/README.md#ttft-and-phase-throughput).

### Completed Qwen3.6 diagnostic: 120/120 cases, 290/290 measured requests

`2026-10-01-qwen36-kv8-governed-metrics/qwen36.jsonl` completed **120 cases**
with **72 deterministic passes** and **zero transport/runtime errors**. All
**290 individual API requests** have attributed vLLM phase metrics. The
following pairs the new Qwen3.6 configuration with the preserved September 30
Flash-Next arm on the same fixture; these are different served configurations
and dates, not a controlled single-flag ablation. No new blind semantic audit
or human judgment was performed, so the original semantic counts must not be
transferred to the new run.

| Bucket | New Qwen3.6 deterministic pass | Original Flash-Next deterministic pass | Median client case time: new Qwen / original Flash |
| --- | ---: | ---: | ---: |
| Short task | 25/30 | 30/30 | 1.71 / 1.96 s |
| Multi-tool | 6/30 | 26/30 | 2.21 / 5.12 s |
| Six-turn conversation | 12/30 | 24/30 | 10.26 / 11.83 s |
| Context-heavy | **29/30** | **30/30** | 27.84 / 38.81 s |
| Total | **72/120** | **110/120** | — |

The sole context failure, `context_24`, returned `assignment_status: "open"`
instead of the exact source value `"open; same weekly assignment"`. It was
recorded as an answer failure, with no server error, and the run continued.
The three noncontext buckets improved from 38/90 to 43/90 deterministic passes,
but multiple serving and resource settings changed; this does not establish
that prefix caching, KV size, or any other individual flag caused the change.
All-case multi-tool medians include skipped/failed tool workflows and remain
unsuitable for claiming a successful-work speed win.

### Qwen timing with explicit process-pause waits excluded

At user request, the main active-time table below subtracts logged thermal
process pauses rather than presenting those waits as inference throughput.
Original rows and the raw timing table below remain unchanged.
`pause-excluded-derived.json` stores per-case calculations, pause overlap,
phase estimates, and sensitivity intervals.

| Qwen target | Cases | Median case time minus stage pauses | Estimated TTFT minus pauses | Estimated prefill TPS minus pauses | Estimated decode TPS minus pauses |
| --- | ---: | ---: | ---: | ---: | ---: |
| 8,192 | 8 | 4.66 s | ≈2.82 s | ≈2827 | ≈26.4 |
| 24,576 | 8 | 10.43 s | ≈8.47 s | ≈2788 | ≈25.7 |
| 40,960 | 7 | 16.35 s | ≈14.48 s | ≈2704 | ≈26.5 |
| 55,296 | 7 | 21.61 s | ≈19.67 s | ≈2689 | ≈25.4 |

Case active time subtracts each stage's recorded `duration_s`. Phase values
are **reconstructed estimates**, not newly measured timestamps: the old runner
stored durations but no absolute request start/first-token/end times. Pause
intervals are recovered from UTC resume time minus duration; response end is
estimated between the final running supervisor sample (with an allowance for
sampling/exporter overhead) and the stage-complete sample. We overlap these
intervals with client TTFT and server prefill/decode durations. Endpoint
sensitivity windows are approximately 0.66 seconds; recorded ranges describe
this reconstruction assumption, not statistical confidence or rigorously
proven error bounds. A pause can overlap decode (`context_20` does), so we do
not subtract every pause from prefill or leave decode universally unchanged.
CPU quota, polling overhead and the temperature-dependent execution state
remain. Subtracting idle time cannot recover actual unconstrained throughput;
fresh phase-aligned measurements are needed for an exact comparison.

### Original observed Qwen timing, including process pauses

| Qwen target context | Cases / pass | Median actual input tokens | Median client TTFT | Median server prefill TPS | Median server decode TPS |
| --- | ---: | ---: | ---: | ---: | ---: |
| 8K | 8 / 7 | 7,900 | 2.82 s | 2,827 | 26.4 |
| 24K | 8 / 8 | 23,456 | 24.23 s | 971 | 25.7 |
| 40K | 7 / 7 | 38,974 | 49.12 s | 796 | 25.7 |
| 55K | 7 / 7 | 52,564 | 73.15 s | 720 | 25.3 |

These are **thermally governed, CPU-limited rates**, not unconstrained model
throughput. The first 55K target had TTFT 40.25 s; the seven-case median was
73.15 s as repeated load increased the required pauses. The governor paused
264 times for **637.59 s total**, within request/phase timing. Cooldown before
cases and a three-second stage gap are outside case wall time; exporter
collection time is also separately excluded. The first short request was cold
and retained as `short_01`, not removed from the score. The suite runs once per
case, in context-first staged order, with prefix caching disabled for Qwen3.6.

Across inference samples: minimum available host memory **64.69 GiB**,
memory-full PSI `avg10` maximum **0.00**, maximum GPU temperature **77°C**,
minimum temperature-limit margin **7°C**, and **zero thermal-slowdown samples**.
No new GPU allocation/Xid/kernel error or host reboot occurred during inference.
These observations validate this constrained run, not future reliability or
the cause of the previous host reset. Production restore transients are
logged separately and excluded from the inference resource summary.

The durable file SHA-256 is
`91b6cce4eebb1d594054d9e263b9f786acd46eb41b47f6eee3aece53b75a7b9e`.
The directory also contains the exact launch command, service states,
`thermal-pauses.jsonl`, host/GPU telemetry, `context-performance-summary.json`,
`run-summary.json`, paired summaries, and startup/server/kernel logs. The
production launcher/profile configuration was not changed.

## Separate Flash native performance audit (October 1)

`runtime/model-benchmarks/2026-10-01-flash-performance-audit/` uses the
production Flash launcher with isolated gateway traffic, native llama.cpp
response timings, and the same thermal pause thresholds. Its declared scope
is the first five cases in each noncontext bucket and the first four context
sizes (19 cases), rather than a new 120-case Flash accuracy run. It retains
normal two-slot prompt caching and has no one-CPU quota; Qwen's diagnostic
run uses one sequence, prefix-off, and a one-CPU quota. These are observations
of different served configurations, not a controlled model speed ranking.

The first audit attempt stopped at a 10 GiB available-memory threshold despite
zero memory-full PSI and no growing swap; normal resident Flash memory already
left roughly 7 GiB available. The resumed monitor used a 4 GiB floor plus PSI,
new swap growth, thermal margin/slowdown and GPU/kernel error checks. A user
interruption then stopped the supervisor at 16 durable cases. Owned runtime
guards were removed, the model resumed, and prior service starts restored
before resuming the same declared audit. Completed rows remain preserved.
The interrupted 24K request left cached work: its recorded retry processes
4,968 new tokens and reuses 18,481. Its low TTFT is therefore a cache-assisted
measurement and must not be treated as a cold full-prefill comparison.
Native prefill TPS uses processed tokens; client TTFT includes thermal pauses.
Neither arm provides unconstrained performance under these controls.

| Flash target context | Client TTFT | Native prefill TPS | Native decode TPS | Processed / cached input tokens |
| --- | ---: | ---: | ---: | ---: |
| 8,192 | 31.55 s | 255 | 26.4 | 7,899 / 0 |
| 24,576 | 10.08 s | 495 | 25.2 | 4,968 / 18,481 |
| 40,960 | 159.82 s | 244 | 22.9 | 38,920 / 49 |

The user requested less conservative Flash controls at 18 completed cases
(17 passes, 53 native request records). The in-flight 55K request was cancelled,
not assigned a result. The supervisor resumed the model and restored service
starts. This partial governed audit is preserved, with a separate production
performance run below; it is not pooled into either full original arm.


## Flash production settings without forced pauses (October 1)

At user request, a fresh run in
`runtime/model-benchmarks/2026-10-01-flash-production-metrics/` removed all
process pauses and forced cooldowns, retained production CPU/GPU/slot/cache
settings, checked health every two seconds, and checked kernel logs every
15 seconds. It completed **15 cases (14 passes), 50/50 native request timings**.
It then stopped during `context_00` at **85°C**, reported temperature-limit
margin **−1°C**, and an active thermal-slowdown flag. Memory-full PSI was zero,
available memory 7.94 GiB, and swap did not grow. The cancelled context request
has no score or phase result. No new GPU allocation/Xid error or host reset
was observed. This thermal observation does not identify the previous reset's
cause, establish that normal Flash use is unreliable, or invalidate its
original completed 120-case run. It limits this sustained-load speed audit.

| Served configuration | Bucket (same five case IDs) | Pass | Client TTFT median | Server prefill TPS median | Server decode TPS median |
| --- | --- | ---: | ---: | ---: | ---: |
| Flash production | short_task | 5/5 | 0.42 s | 227 | 28.9 |
| Flash production | multi_tool | 5/5 | unavailable (nonstream) | 156 | 28.4 |
| Flash production | long_horizon | 4/5 | 0.38 s | 158 | 28.5 |
| Qwen governed | short_task | 3/5 | 0.15 s | 819 | 26.5 |
| Qwen governed | multi_tool | 1/5 | unavailable (nonstream) | 2102 | 27.0 |
| Qwen governed | long_horizon | 1/5 | 0.20 s | 1857 | 26.4 |

These per-request medians use only the completed shared 15-case subset.
Flash reuses resident prompt caches, including earlier experiments; this is
not a cold-start benchmark. Qwen still uses CPU quota and thermal pauses and
can skip expected tools, so rates and request counts do not describe equivalent
successful work. The preserved original Flash 120 rows have no new native
phase measurements. This stopped run provides **no completed unpaused Flash long-context phase
comparison**. The later completed 88°C-policy run at the top of this report
provides that separate comparison; earlier governed measurements are not pooled.

The final production Flash endpoint, main/English gateways, and cron watchdog
are active again; the model has no remaining process stop or benchmark guard.
ClawGram retains its pre-existing Qwen readiness mismatch and remains in
`activating/start-pre`, rather than being reported as healthy.

## Is Flash-Next generally better for this agent?

| Dimension | Evidence and practical conclusion |
| --- | --- |
| Task correctness | On the original complete three-bucket fixture, Flash-Next passed 80/90 deterministic checks versus 38/90, and 71/90 provisional semantic checks versus 43/90; excluding the 12 uncertain cases gives 61/78 versus 36/78. The separate completed retry gives Flash 110/120 versus Qwen 72/120 deterministic passes, including context 30/30 versus 29/30; the retry has no new semantic/human review. This favors the current Flash-Next served stack on these particular synthetic tasks, especially scripted tools and six-turn state. It is not measured production accuracy. |
| Speed | Original Qwen3.6 median client time was about half Flash-Next's on short and six-turn tasks. Multi-tool failure shortcuts invalidate the all-case median as successful-work speed. The first October 1 eager smoke has only one cold failed short request. The subsequent governed run reports new phase metrics and slower decode than the original unconstrained Qwen run; its CPU quota, pauses, and cache policy must remain visible, and its rows cannot be pooled with the original run. The first unpaused audit stopped at 15 cases; the later relaxed full Flash run completed 120. Its measured phase values and Qwen pause-excluded estimates are compared at the top, with CPU/cache/control differences explicit. |
| Stability | Flash-Next completed 120 original cases; the Qwen3.6 arm ended at 92 during an unexplained host reset. The initial retry stopped after a short request; the subsequent governed Qwen configuration completed 120 cases, including all 30 contexts, without runtime errors or a reset. That establishes feasibility under its controls, not intrinsic model reliability or the cause of the old reset. |

Qwen pause-excluded derived context timing must be used when discussing
active computation; raw timings include deliberate waits. These reconstructions
retain the CPU quota and do not establish unconstrained performance.

The latest full Flash run independently reproduces 110/120 deterministic
passes and completes 30/30 contexts without explicit thermal waits. Compared
with Qwen 72/120, this strengthens the fixture-specific task-completion evidence.

Keeping Flash-Next as the operational default is a reasonable provisional
choice given its higher fixture task-completion counts and the unresolved
Qwen3.6 serving/host risk. **“Flash-Next is generally better for our real agent”
is not established.** Qwen3.6 has a measured speed advantage on some original
short tasks; realistic tool use, usefulness, durable state, and long-context
quality need the real-trace and human-reviewed evaluation below. The original
context-heavy comparison remains **2/30 original pairs**. The separately
configured retry provides **30/30 new completed contexts**, with 29 passes
versus 30 in the preserved Flash arm; it does not rewrite the interrupted run.

## Follow-up evaluation

Build a consented, privacy-redacted sample of actual Hermes tasks across the
existing workflows, retaining the relevant tool sequence, returned evidence,
interruptions, retries, and final user outcome. Remove personal identifiers,
credentials, private messages, and sensitive source content before evaluation.
Replay tools in an isolated environment with realistic failures and allow
multiple valid approaches; assess task completion and grounding separately
from formatting. Have people review both the task/reference quality and blind
model outputs, resolve the 12 ambiguous fixture cases, and calibrate any LLM
judge against that review. Report production-frequency weighting alongside
per-workflow results, repeated-run variation, successful-work latency, and
service stability independently. These steps are needed before a claim about
which model is generally better for this agent.
