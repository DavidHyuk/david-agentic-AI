# Local agent-task model benchmark

`agent_cases.json` is a small, synthetic, version-controlled comparison set for
the existing Papers Digest, interview, coding, English, podcast, tool-use, vision,
and long-context workflows. It contains no real tutor messages, Telegram chat
history, private paper database rows, or model-generated answers. It tests the
model-serving layer, **not** full Hermes helper execution or live source fetching.

Run each checkpoint on the same DGX Spark, one at a time. Both need a 64K
per-request context. The benchmark fixes temperature to zero, disables thinking
in both chat templates, leaves tool selection on `auto`, and caps output by case.
The Qwen3.6 FP8 service uses its existing vLLM parser; Qwen3.8 IQ4_XS uses
llama.cpp. Results therefore compare deployed checkpoint/runtime combinations,
not architecture alone. The runner sends only local API calls and does not
deliver Telegram messages or mutate Hermes state.

```bash
python3 local-model/eval/benchmark_agents.py run \
  --model Qwen3.8-Flash-Next-UD-IQ4_XS \
  --output runtime/model-benchmarks/qwen38.jsonl

# After temporarily stopping the production model, start Qwen3.6 on localhost:8004
# with its vLLM launch options and 65536 max model length.
python3 local-model/eval/benchmark_agents.py run \
  --model Qwen3.6-35B-A3B-FP8 --base-url http://127.0.0.1:8004/v1 \
  --output runtime/model-benchmarks/qwen36.jsonl

python3 local-model/eval/benchmark_agents.py blind \
  --left runtime/model-benchmarks/qwen38.jsonl \
  --right runtime/model-benchmarks/qwen36.jsonl \
  --salt 2026-09-29-agent-eval \
  --bundle runtime/model-benchmarks/blind.json \
  --mapping runtime/model-benchmarks/mapping.json
```

Read `blind.json` without opening `mapping.json`. For each non-tool case, give
every listed rubric clause a `1` only when the answer explicitly satisfies it
without a contradictory claim; otherwise give `0`. Judge A and B independently
against the supplied case facts, not by comparative fluency or length. Do not
reward unsupported detail; mark uncertain or truncated clauses `0`. Keep brief
criterion-level rationales for audit. Record `{case_id: {A: [...], B: [...]}}`
in a JSON file before unsealing the mapping. Tool-call accuracy is
automated from parsed function name and JSON arguments. Once grades are saved:

```bash
python3 local-model/eval/benchmark_agents.py summarize \
  --left runtime/model-benchmarks/qwen38.jsonl \
  --right runtime/model-benchmarks/qwen36.jsonl \
  --mapping runtime/model-benchmarks/mapping.json \
  --judgments runtime/model-benchmarks/judgments.json
```

The runner stores end-to-end wall time, first-token latency, output token count,
and approximate post-first-token decode throughput. For long-context speed,
compare the dedicated case separately. One run per case is a diagnostic sample,
not a statistically precise model ranking. `runtime/` is git-ignored; publish
only reviewed, non-sensitive aggregate results in project documentation.

The rubric follows [Inspect's reference-guided model grading](https://inspect.aisi.org.uk/model-graded.html)
and [OpenAI Docs evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices):
combine functional checks with grounded open-answer judgments, blind model
identity, and report position/verbosity and small-sample limitations. An
independent automated judge is preferable for repeated runs; without one,
Codex can grade the blinded bundle, but those scores require human spot checks.
