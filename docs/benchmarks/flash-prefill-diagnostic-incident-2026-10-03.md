# Flash prefill diagnosis and host-reset incident — 2026-10-03

## Incident and responsibility

The diagnostic session performed an unbounded Python `GGUFReader` inspection
while the production Flash model was resident. It did not launch an additional
model or intentionally send benchmark inference requests before the incident.
Treating a read-only model-file inspection as low-resource work was an unsafe
assumption. The diagnostic lacked a separate memory cgroup, runtime limit and
independent pressure monitor. Those omissions have now been addressed.

The previous boot journal ends abruptly at **01:20:06 PDT**; the new boot starts
at **01:34:34**. No terminal Linux shutdown, kernel panic or OOM-kill entry was
found in the readable journal. NVIDIA `NV_ERR_NO_MEMORY` allocation errors were
logged at **00:55:10**, before this diagnostic began. The last available sysstat
memory sample was 01:10, with about 9.56 GiB available; it does not describe the
final moment. Root-only pstore was not readable. These gaps prevent a definitive
mechanism attribution. They do not exonerate the unbounded diagnostic workload.

The partial metadata output files were zero length after reboot. Preserve them
as interrupted artifacts; do not interpret them as a completed inspection.
Production Flash, main/English/ClawGram gateways and the cron watchdog were
confirmed active after reboot. No production launcher was changed or manually
restarted during recovery and bounded reproduction.

## Containment implemented and checked

`local-model/eval/guarded_diagnostic.py` launches CPU-only diagnostics in a
separate transient systemd service. Defaults are 1 GiB `MemoryMax`, 768 MiB
`MemoryHigh`, no swap, one aggregate CPU, low I/O weight, 90-second
`RuntimeMaxSec`, `OOMPolicy=stop`, and `KillMode=control-group`. It masks CUDA
devices by environment and is intended for CPU-only inspection, not GPU/model
launches. The kernel memory/runtime limits remain when the supervising agent
disconnects. CUDA masking is not a security boundary, and cgroup memory limits
do not guarantee containment of GPU-driver allocations or firmware failures.

The separate supervisor records fsynced host/unit telemetry every second and
checks new kernel/GPU errors every five seconds. It refuses launch or stops only
its own diagnostic unit when available memory falls below a 12 GiB reserve,
memory-full PSI avg10 exceeds 1, or new swap use exceeds 256 MiB. It preserves
results in fresh directories and writes manifests with fsync and atomic rename.
No gateway, production-model or host shutdown command is part of this helper.
Fast completed jobs retain accounting until the supervisor records the result.

| Bounded experiment | Outcome |
| --- | --- |
| Allocate 256 MiB inside a 64 MiB unit | Applied limits confirmed; supervisor stopped the child after reclaim pressure exceeded its PSI threshold. This validates pressure-triggered stopping, not an observed hard OOM kill. |
| Sleep 30 seconds with a two-second runtime limit | systemd returned `Result=timeout`, terminating the diagnostic child only. |
| Original GGUFReader on the first shard, 1 GiB maximum / 768 MiB high limit | Unit reached about 768 MiB; reclaim-related pressure triggered a stop. No completed metadata result, host reset or new GPU error. This is not the unbounded process's measured peak. |
| New streaming reader across all three shards, 128 MiB maximum | Completed successfully; retained cgroup `MemoryPeak=4,763,648` bytes (4.54 MiB). No tensor payload was read or mapped. |
| Synthetic PLE predecessor/hash arithmetic, 256 MiB maximum | Completed five 52,564-token trials: 8.56–8.67 ms, median about 8.58 ms. No model weights, embedding gathers, GPU transfer or model kernels were included. |

The kernel accounting includes charged memory, rather than serving as a measure
of all host memory attributable to the job. All experiments ran on the same new
boot without another reset; host pressure recovered to zero. Their evidence is
stored under `runtime/model-benchmarks/2026-10-03-flash-prefill-diagnosis/`.

## Corrected n-gram diagnosis

The live `/slots` response reported `speculative=false` and
`speculative.types=none`. **This excludes n-gram speculative decoding only.**
The earlier explanation incorrectly extended this finding to all n-gram work.

Streaming inspection establishes that this checkpoint's architecture is
`qwen4exp`. It has **PLE n-gram embeddings**: n-gram size 3, eight heads per
n-gram length, 16 heads total. Its `per_layer_token_embd.weight` tensor has shape
`[160, 320001536]`, 51,200,245,760 elements, and GGML type 20 (`IQ4_NL`). The
three shards total 176,943,899,520 tensor elements. These are local checkpoint
facts, not inferred from the public model name.

The active server build and clean local llama.cpp checkout both identify commit
`526c43b8f`. In that implementation:

- `src/models/qwen4exp.cpp`, `llm_graph_input_ple::set_input`, calculates PLE
  predecessor lookups and n-gram hashes on the host, then transfers row indices.
- `build_inp_ple` separately gathers embedding rows with `ggml_get_rows`.
- `src/llama-arch.cpp` classifies `PER_LAYER_TOKEN_EMBD` as an input tensor;
  `src/llama-model.cpp` places the input buffer list on the CPU. Actual gather
  scheduling and transfer time still require runtime profiling.
- The production launcher uses `--lazy-mode off`; the checkpoint's large
  embedding table cannot be assumed to have negligible host-memory cost.

The synthetic CPU probe mirrors the predecessor-tree lookup and hash arithmetic
shape with fake tokens. Its roughly 8.6 ms result makes **hash arithmetic alone**
an implausible explanation for about 89 seconds of long-context prefill. It is
not an actual model trace and does not bound table gather, dequantization,
page faults, CPU/GPU copies or GPU kernels.

## Remaining attribution limits

| Candidate | Verified evidence | What is not established |
| --- | --- | --- |
| CPU n-gram | PLE host hashing exists; speculative decoding is disabled. Synthetic hash/predecessor work is milliseconds. | Actual PLE gather and transfer share of TTFT. |
| Model structure | Flash has 48 layers, hidden size 2560, 512 experts, 10 selected; Qwen config has 40, 2048, 256, 8. | A causal time percentage from parameter counts; the architectures differ further. |
| Quantization/backend kernels | Flash serves mixed GGUF types under llama.cpp; Qwen served FP8 under vLLM. | IQ4 versus FP8 contribution independent of model, batch and layout. |
| CPU/GPU placement | PLE input-tensor buffer policy is CPU-side; host/GPU memory accounting differs substantially. | Every live layer's placement or a blanket claim that the repeating model layers run on CPU. |
| Thermal throttling | The earlier full Flash run completed 120 cases and logged slowdown samples, maximum 87°C. | A percentage of delay caused by throttling; no paired controlled thermal experiment. |

No additional GPU load, profiler/model reload or heavy inference experiment was
performed after this reset. CPU-only containment and metadata inspection are
verified. GPU performance attribution remains incomplete and must use a separate
staged experiment with saved placement/kernel traces and restore handling; none
of these findings establishes the reset's final mechanism or future immunity.

## Verification

Final `pytest -q`: **459 passed**, including 18 focused diagnostic/header tests.
`git diff --check` passed. Original benchmark rows remain unchanged. The
post-experiment boot ID matches the post-reset boot, no diagnostic unit remains
running, and Flash/main/English/ClawGram/watchdog are active.
