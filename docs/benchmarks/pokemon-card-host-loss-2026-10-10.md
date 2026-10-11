# Pokemon-card benchmark host loss — 2026-10-10

The direct Vision benchmark reused the existing localhost:8004 llama.cpp
Flash-Next IQ4_XS server and mmproj-F16 projector. No Hermes, llama-server,
system service, network, Tailscale or kernel configuration was changed.
Four 3000×4000 smartphone photos created 28 planned sequential requests.
No successful complete run is claimed.

## Local observations

- Previous boot's journal ends at **21:52:32 PDT**, immediately after the
  server launches task 2108601. The new boot begins at **21:54:18 PDT**.
- No Linux OOM kill, NVIDIA Xid, NV_ERR_NO_MEMORY or kernel-panic match is
  present in the accessible incident-window kernel journal. This does not
  exclude an unflushed kernel/driver error, memory pressure, power or firmware
  failure. The failure's timing during evaluation is not causal proof.
- The JSONL contains **12 valid completed rows** and a final **1,148-byte NUL
  record**. Preserve the original bytes and exclude the corrupt final record
  from scoring. Mark the run `interrupted_host_reboot`. Recover CSV/JSON,
  Markdown and PNG/SVG reports without another inference request.
- Human ground truth is absent, so all field accuracies remain N/A.
- Actual running stack: Ubuntu 24.04.4; dgx-release **7.5.0**; kernel
  **6.14.0-1015-nvidia**; NVIDIA module **580.95.05**. The installed
  **6.17.0-1029-nvidia** kernel has no NVIDIA module found by `modinfo -k`.
  Merely selecting it at boot would not establish a working GPU stack.
- After recovery, a read-only `/health` query returns `ok`. Vision inference
  has not been revalidated. No model/service restart was initiated here.

Runtime artifacts are outside Git:
`~/pokemon-card-benchmark/runs/20261011T044736.727475Z-baseline/`.
Source hashes must continue to match `metadata.json` for every original photo.

## Official update evidence, checked 2026-10-10

The [Founders Edition release notes](https://docs.nvidia.com/dgx/dgx-spark/release-notes.html)
(updated September 10) list DGX OS 7.5.0, kernel 6.17 and driver 580.159.03.
The July update explicitly improves GB10 unified-memory OOM handling. It does
not promise immunity from all allocation failures or full-host resets.

The newer [DGX OS 7.6.0 release notes](https://docs.nvidia.com/dgx/dgx-os-7-user-guide/release_notes.html)
(September 14 release) list Spark-specific kernel **7.0.0-1018-nvidia** and
Canonical-signed driver **580.173.02**. These are different documentation
snapshots; version numbers alone do not demonstrate stability on this workload.

The [Founders Edition update guide](https://docs.nvidia.com/dgx/dgx-spark/os-and-component-update.html)
recommends **DGX Dashboard** for the tested OS/driver/firmware update path.
The [DGX OS release guidance](https://docs.nvidia.com/dgx/dgx-os-7-user-guide/release_guidance.html)
advises against individual package updates. No updates were installed here.
Local APT cache candidates were only inspected; indexes were not refreshed.

A firsthand [NVIDIA playbooks issue #97](https://github.com/NVIDIA/dgx-spark-playbooks/issues/97)
reports GB10 host loss on 6.17.0-1029/580.173.02 during vLLM workloads.
It is a user report on an NVIDIA repository, not a vendor-confirmed diagnosis
or a reproduction of this llama.cpp/card workload. That combination cannot be
described as proven crash-free based on the published release alone.

## Benchmark changes and remaining limits

Add conservative read-only request admission: MemAvailable ≥ 40 GiB,
MemFree ≥ 24 GiB and memory full PSI avg10 < 0.1. Check before preparation
and immediately before every inference. Keep idle-slot checks and sequential
execution. Persist each completed JSONL row with flush/fsync and recover a torn
final row while preserving the original evidence.

These checks neither guarantee GPU allocator headroom nor cancel an already
submitted GPU kernel. A client `try/except` cannot convert a kernel/firmware
reset into a live-server HTTP error. Keeping the host and llama-server alive
under exhaustion requires supported driver/firmware behavior, a validated
memory budget and serving-engine allocation error handling. Cgroup OOM limits
can kill a service; they do not ensure this service survives.

Do not resume live evaluation until the operator has resolved the stack/budget
question. Preparation, label editing and reports remain available without Vision
inference. No server-level containment or kernel fix is claimed.
