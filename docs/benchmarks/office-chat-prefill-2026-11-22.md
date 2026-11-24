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

- The old Strata GB10 fork reported roughly 1,200–1,340 prefill tokens/s at
  6K–75K and 56–61 tokens/s at two shorter lengths using IQ3_XXS. The official
  ARM64 engine now publishes 1,296 / 1,680 / 1,735 tokens/s at 4K / 16K / 32K
  on IQ3_S and supports packing this host's existing UD-IQ4_XS weights.
  These rates come from different engine versions and quantizations.
  [Official GB10 measurements](https://github.com/Niko1221/Strata/blob/v0.2.20/docs/DGX_SPARK_LINUX.md)
  [UD-IQ4_XS support](https://github.com/Niko1221/Strata/blob/v0.2.20/docs/UNSLOTH_Q4.md#ud-iq4_xs)
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

## Follow-up with the official Strata build

The official ARM64 release v0.2.20 (engine 0.1.66) passed its signed-feed and
package SHA-256 checks. The packer read the three existing UD-IQ4_XS model shards,
matching the published byte sizes, and produced a 1.38 GiB compatibility arena.
It uses the original expert and PLE bytes. It rounds some small projections to
BF16 for compatibility, and this NVIDIA build reported using native Q8_0
hyper-connection projections. [Format details](https://github.com/Niko1221/Strata/blob/v0.2.20/docs/UNSLOTH_Q4.md#ud-iq4_xs)

Two fresh synthetic recall prompts kept the reference in the earlier user
message and placed the question after the retained history. The same prompt
token IDs were saved for both engines. The current llama.cpp proxy returned
the reference on both checks. Its first visible token arrived in 1.298 s at
376 tokens and 13.585 s at 11,416 tokens, with prefill at 321 and 846 tokens/s.
The long input consisted of repeated text and is separate from the realistic
Hermes prompt comparisons above.

The isolated Strata run identified SM121, read the original weights and PLE
table, and began filling its 24,576-slot, 55.43 GiB expert cache. It was
still filling at the trial's 90-second startup limit. The test therefore
produced no local Strata prefill result on November 22. The original model
and gateways were restarted. The private receipts and verified engine remain in
`runtime/model-benchmarks/strata-20261122/`.

On November 23 a longer trial filled all 24,576 slots in 99.1 s and processed
the 11,416-token input in about 11.8 s (965 prefill tokens/s). The first
decode window faulted with CUDA Invalid Address Space (kernel Xid 13/43)
and yielded no first visible token. The host stayed within the configured
memory and temperature bounds and the original service recovered. The
maintainer traced the equivalent failure to a Q8_0 hyper-connection kernel
bug in engine 0.1.66 and published two switches for the affected paths.
[Upstream CUDA regression](https://github.com/Niko1221/Strata/issues/6814)

A second November 23 trial set `STRATA_HC_Q8_TC=0` and
`STRATA_HC_Q8_BF16TC=0` and completed generation. The Strata prompt token IDs
matched the llama.cpp baseline exactly, and the answer correctly recalled
the reference from the earlier message. Strata measured 11.694 s native
prefill and 12.336 s to the first generated token, compared with llama.cpp's
13.496 s native prefill and 13.585 s to the first streamed token. The latter
includes localhost proxy and SSE overhead. The Strata run used a 16K context,
int8 KV and no MTP head, while llama.cpp used its production context, cache
configuration and MTP. Per-request results exclude model loading. Strata's
expert-cache fill took 117.3 s, and its full native process took 160.2 s.
This is one synthetic recall case with different runtime settings. Strata
was evaluated as an isolated experiment and the workspace runs llama.cpp.

### Why test the existing GGUF alongside NVFP4

The installed UD-IQ4_XS shards total 93.7 GB and already run with the shared
llama.cpp service. Keeping those shards for both arms isolates the engine
change as far as their different precision paths allow. The NVIDIA NVFP4
export uses native FP4 for routed experts, BF16 for other main layers, and
FP8 for the PLE embedding and MTP experts. Its safetensors total 132.7 GB,
including a 53.7 GB PLE/MTP shard. One Spark needs to leave room for KV cache
and runtime buffers, so published single-Spark recipes place PLE on SSD.
[NVIDIA checkpoint and precision details](https://huggingface.co/nvidia/Qwen3.8-Flash-Next-NVFP4)
[NVIDIA checkpoint sizes](https://huggingface.co/nvidia/Qwen3.8-Flash-Next-NVFP4/tree/main)

NVIDIA also ships a separate Qwen3.8-Flash-Next-FP4-Local checkpoint trained
for NVFP4. Its Flash-Next PLE is itself NVFP4 and is about 26.8 GiB, and the
checkpoint is about 96 GiB on disk. NVIDIA publishes a single-Spark vLLM
recipe with and without PLE offload. Strata calls its converted configuration
NVFP4-QAD. This is the more directly applicable local NVFP4 candidate.
[NVIDIA FP4-Local model and Spark recipe](https://huggingface.co/nvidia/Qwen3.8-Flash-Next-FP4-Local)
[Strata FP4-Local conversion](https://github.com/Niko1221/Strata/blob/v0.2.20/docs/NVFP4.md#nvidias-fp4-local-checkpoint)

Strata's published single-Spark NVFP4 GPTQ profile reads 4K prompts at 1,408
tokens/s versus 1,296 for its IQ3_S profile. At 16K they are 1,670 and 1,680,
respectively. These numbers do not include the local UD-IQ4_XS checkpoint.
A separate vLLM hybrid recipe reports 2.75 s TTFT for 8K input. Engine,
checkpoint, PLE residency and workload must be kept explicit when comparing
an NVFP4 rollout.
[Strata GB10 comparison](https://github.com/Niko1221/Strata/blob/v0.2.20/docs/DGX_SPARK_LINUX.md#speeds)
[Single-Spark vLLM measurement](https://github.com/shinrali/Qwen3.8-Flash-Next-NVIDIA-Hybrid-Single-Spark/blob/main/README.md)

## FP4-Local production deployment (2026-11-24)

The shared Spark now serves NVIDIA's FP4-Local checkpoint
(`b9ce18a6887e18c089fdea8509a33e63429a3300`) using the signed Strata v0.2.21
ARM64 CUDA 13 engine (0.1.67) and control package (0.1.68). A one-time conversion
of the 102.26 GB download produced a 99 GiB pack. The engine placed 24,576
routed experts on the GB10 and loaded the 26.8 GiB NVFP4 PLE table into
reclaimable host memory. The model uses INT8 KV and two MTP draft tokens per
slot. There are two 131,072-token slots, with 65,536 configured in Hermes.
[NVIDIA model](https://huggingface.co/nvidia/Qwen3.8-Flash-Next-FP4-Local)
[Strata release](https://github.com/Niko1221/Strata/releases/tag/v0.2.21)

Both model builds streamed the same messages through `:8003/v1/chat/completions`
with thinking disabled. The inputs contained a synthetic reference in an
earlier turn. Timing starts at request submission and stops at the first
visible text delta. The older 11.4K run reused 19 of 11,416 prompt tokens and
Strata reused none.

| Synthetic input | IQ4_XS and llama.cpp | FP4-Local and Strata | First-token reduction |
| --- | ---: | ---: | ---: |
| 376 prompt tokens | 1.32 s | 1.05 s | 20% |
| 11,416 prompt tokens | 15.00 s | 5.47 s | 64% |

The 11.4K prompt processing time fell from 14.52 s to 5.40 s. The first
FP4-Local attempt returned visible text in 6.06 s on the same prompt and was
rolled back when the run exceeded its 85°C experiment threshold. The second
attempt cooled the board below 72°C before heavy probes and used the shared
scheduler's existing 90°C pause threshold as its upper limit. It completed
with 28.4 GiB minimum available host memory and 87.3°C peak board temperature.
Each start logged a driver allocation refusal and subsequently reached
readiness. The kernel reported no GPU Xid or host OOM kill during these starts.

The accepted run recalled the earlier reference at 65,848 uncached prompt tokens
with first text at 31.30 s. It also completed two simultaneous 11K-token
requests, a streamed automatic tool call with its result carried into the next
answer, and image input with plain text and structured JSON output. A temporary
chat through the real Hermes gateway streamed its first text at 16.08 s, saved
the response and was removed after verification. The earlier standalone gateway
probe took 74.41 s during the model download. That test had different host load.

The API advertises `Qwen3.8-Flash-Next-FP4-Local` and the former model ID as a
compatibility alias. David and English gateways, admission and Observatory were
healthy after the switch. Raw logs are under
`runtime/model-benchmarks/nvfp4-20261124/`. The shared 128K limit was verified in
both slots' configuration. The longest completed check was 65,848 tokens in a
single request, and the concurrency check used roughly 11K tokens per slot.
