# Qwen3.6 35B vs Flash-Next: 120-case agent suite, interrupted at 92 pairs

2026-09-30, one DGX Spark (GB10), kernel `6.14.0-1015-nvidia`.

## Assessment of the original run

Three buckets finished with 30 paired cases each. Flash-Next had higher fixture
pass counts on this synthetic serving-layer suite; Qwen3.6 was about twice as
fast on the short and six-turn tasks. The long-context comparison is **incomplete**: the
host stopped after only two of Qwen3.6's 30 context cases. These results do
not isolate model architecture from engine, quantization, or tool parser.

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
