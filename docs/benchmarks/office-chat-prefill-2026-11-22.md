# Observatory chat prefill on DGX Spark · 2026-11-22

The workbench now defaults to **빠른 답변**. The same local Flash-Next model
receives the character instructions, current question, supplied evidence and
up to three recent exchanges within a 6,000-character history budget. Choose
**전체 문맥 · 도구** to use older context, reasoning, tools or HQ project search.
Both modes use the same Hermes conversation history.

Two issues contributed to the delay. In the recent production logs, an
11,623-token prefill took 41.6 seconds. The idle host had 5.86 GiB available
against a 6.45 GiB admission budget, which included the 2 GiB reserve and the
observed 4.45 GiB request estimate. The shared service was running with a
20 GiB host prompt-cache cap and logging cache evictions. The cap is now
12 GiB. Immediately after loading the model, the admission proxy showed
35.7 GiB available. That reading includes the effect of clearing the old cache
and allocations at restart. Filled-cache endurance has not been measured.

| Single uncached comparison | Previous input | Fast input | Previous first visible token | Fast first visible token |
| --- | ---: | ---: | ---: | ---: |
| Jun · Binary Search boundary | 8,595 tokens | 1,502 tokens | 43.069 s | 2.955 s |
| Ellie · English grammar correction | 17,105 tokens | 337 tokens | 48.872 s | 1.486 s |

The two pairs replayed the same questions through the local 8003 admission proxy
with the same loaded llama.cpp model, decoding options and synthesized
conversation history. Prompts used the current Hermes system prompt and the
previous room tool catalog as the baseline. Native prefill fell from 43.032
to 2.714 seconds for Jun and from 48.655 to 1.093 seconds for Ellie. Both arms
answered the two checks correctly. A second fast Jun question reached its
first token in 2.827 seconds. Further long runs were stopped after the board
passed 88°C. These are directional single-request measurements with changing
thermal conditions. They do not establish a percentile, rich coaching quality
or the speed of tool-driven work. Raw local receipts live in
`runtime/model-benchmarks/office-chat-20261122/`.

An isolated Hermes turn used the staged plugin, the live proxy and a temporary
SQLite database. The repeated synthetic question reached its first visible
token in 0.207 s with a 295-token request and wrote both sides of the exchange
to the test database. This replay allowed cache reuse. Chromium also verified
the mode selector and request values against mocked SSE, and `pytest -q`
passed all 1,027 tests.

Other backends reviewed:

- Strata's GB10 port reports roughly 1,200–1,340 prefill tokens/s for 6K–75K
  inputs, with roughly 56–61 tokens/s in two short-input runs. It measured
  IQ3_XXS with one run per length. [Strata GB10 benchmark](https://github.com/shi3z/Strata-DGX-Spark/blob/main/bench/results/2026-10-05-dgx-spark-gb10/README.md)
- A pinned vLLM recipe for Flash-Next NVFP4 on one Spark reports 2.75 s TTFT at
  8K input and roughly 42.7 output tokens/s, with an alternate checkpoint and
  a bounded FP8 PLE/KV configuration. A separate SparkLab comparison reports
  4.53 s vLLM and 10.54 s SGLang at roughly 8K on its pinned configurations.
  [vLLM profile](https://github.com/shinrali/Qwen3.8-Flash-Next-NVIDIA-Hybrid-Single-Spark/blob/main/README.md)
  [SparkLab comparison](https://github.com/sixteen-miles-labs/sparklab/blob/main/benchmarks/frameworks/QWEN38_FLASH_NEXT_20260909.md)
- Infernix publishes 0.626 s TTFT at 2,048 tokens with its separate HC4-W4Dense
  checkpoint and GB10-specific configuration. Its tool evaluation and benchmark
  are useful for a future isolated long-context comparison.
  [Infernix GB10 results](https://github.com/eugene-kamenev/Infernix-dgx-spark-gb10#benchmarks-on-nvidia-dgx-spark-nvidia-gb10)

The deployed changes improve ordinary chat without loading a second checkpoint.
The other engines use different checkpoint formats or quantization and have
their own memory and long-context tradeoffs. The installed shared model unit
uses `--cache-ram 12288` (MiB). Its prior drop-in is saved owner-only at
`~/.hermes/backups/flash-next-cache20-20261122T221227Z.conf`. The shared
ClawGram installer still carries its historical 20 GiB template, so preserve
the installed limit if restaging that service. [llama.cpp server cache options](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
