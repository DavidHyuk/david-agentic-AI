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

## After the operator's update and reboot

The operator installs the exact prepared Ubuntu kernel/driver bundle and runs
the privileged verification command on 2026-10-10. Subsequent read-only checks
confirm kernel **6.17.0-1021-nvidia**, running driver **580.159.03**, all 20 target
package versions, 20 package holds, the saved GRUB target and the unchanged
Flash-Next alias on localhost:8004. The previous 6.14 kernel also has a matching
580.159.03 signed GPU module for boot fallback. Firmware and GPU clock settings
were not updated by this procedure.

MemAvailable is approximately **35.7 GiB** and MemFree **31.3 GiB**, with memory
full PSI avg10 zero. A one-photo/0.3MP admission check refuses before any Vision
request because the existing 40 GiB available-memory floor is unmet. Do not
equate boot/model-API verification with Vision or sustained-load stability.
Four original photo hashes still match the interrupted run. Runtime evidence:
`~/pokemon-card-benchmark/validation/post-upgrade-2026-10-10.json`.

Review the memory budget before further inference. The benchmark remains
incomplete, accuracies remain unlabeled, and the user's request to publish the
completed results to Langfuse remains pending in the workspace. The completed
stack update does not establish the earlier reboot's cause.

## Repeated host loss on the updated stack

The operator explicitly permits exploratory evaluation despite possible another
shutdown. Override the two unvalidated client memory floors to zero for these
executions only, retaining sequential requests, idle-slot checks and the PSI
guard. The 40/24 GiB defaults were selected by the agent; they are not NVIDIA
recommendations or measured request-allocation budgets.

- One 0.3MP request completes in 4.504 seconds on the updated stack.
- The full run completes first-photo 2MP (5.470 s) and 5MP (21.915 s), then
  loses the host during the next 8MP request. Only **2/28** records are complete.
- Previous boot ID `2b1f4679-eabe-4cea-a069-03fac220f95b` changes to
  `25db06fc-9c64-4328-abdc-8d3ee726ba9d`. The user reports a hard shutdown.
  Accessible prior-boot logs end mid-request without orderly shutdown,
  OOM/Xid/panic markers. `/sys/fs/pstore` is permission-restricted; do not
  describe it as inspected or empty. `/var/lib/systemd/pstore` is empty.
- **75 saved samples** from 06:00:50 to 06:02:06 UTC show minimum available
  memory **33.177 GiB**, minimum free memory **27.894 GiB**, maximum GPU
  temperature **81 C**, GPU-only power **90.53 W**, and thermal-zone maximum
  **93.8 C**. All sampled memory PSI avg10 values are zero. The seven zones
  expose only `acpitz`, so CPU/SoC mapping is not established. Sampling cannot
  rule out unobserved allocation/power spikes or establish root cause.
- All four source hashes match. Preserve JSONL and mark metadata
  `interrupted_host_reboot`; regenerate partial reports without inference.
  Human labels remain absent. Further inference and completed-result Langfuse
  publication are deferred; no clock or firmware changes are applied.

Runtime evidence: `~/pokemon-card-benchmark/validation/host-loss-20261011T0602Z/`
and `validation/monitored-20261011T060050.070827Z-full/`. Partial report:
`runs/20261011T060050.158682Z-post-upgrade-baseline/report.md`.

## Community experience and NVIDIA guidance checked after this failure

The [same-stack NVIDIA_DGX_Spark report](https://forums.developer.nvidia.com/t/hard-power-off-under-sustained-gpu-load-at-90w-persists-after-full-platform-firmware-update/378315)
uses exactly 6.17.0-1021 and 580.159.03. A user reports hard power-off near
90 W GPU draw despite updated platform firmware, with successful larger
workloads after `sudo nvidia-smi -lgc 300,2200`. NVIDIA's July 27 reply calls
the symptoms a known issue, recommends lowering the GPU clock maximum as
the current workaround and links Spark Fieldiag. This is a relevant temporary
diagnostic mitigation, not proof that this host has the same cause or that
2200 MHz will always prevent shutdown. Other [firsthand users](https://forums.developer.nvidia.com/t/dgxspark-temperature-too-high-automatic-shutdown/363370?page=2)
report improved uptime with clock limits, failures even at 2300 MHz and device
variation on the same software. A diagnostic PASS does not reproduce every
workload failure.

In a separate [OOM/hang thread](https://forums.developer.nvidia.com/t/device-hangs-under-load/375016),
NVIDIA identifies recorded NV_ERR_NO_MEMORY and recommends at least 580.159.03
and a workload memory budget, expecting exhaustion to kill the process instead
of hanging the host. The user says that driver is already installed; further
diagnostic collection is requested. This does not promise a surviving
llama-server or a clean HTTP allocation-error response.

Read-only fwupd evidence identifies installed **EC 0x02004b03 (2.75.3)**,
**SoC 0x02009009 (2.144.9)** and **USB-PD 0x00000500 (0.5.0)**. The cached
release names map the two generic UEFI firmware devices to SoC and USB-PD.
These precede the Founders Edition release-note values EC 3.5.8, SoC 2.155.11,
USB-PD 0.5.22. The kernel/driver operation deliberately left firmware unchanged.
NVIDIA recommends the [DGX Dashboard update path](https://docs.nvidia.com/dgx/dgx-spark/os-and-component-update.html)
for compatible OS, driver and firmware updates. Firmware freshness is another
unresolved variable, not an established cause or guaranteed remedy.

For a reversible operator-run clock test, use `sudo nvidia-smi -lgc 300,2200`;
restore defaults with `sudo nvidia-smi -rgc`. The [nvidia-smi reference](https://docs.nvidia.com/deploy/nvidia-smi/index.html)
documents both commands. Keep clock state recorded alongside subsequent
benchmarks because latency changes and this setting affects all GPU clients.
For persistent faults, collect support evidence and use the [official Field
Diagnostic/RMA route](https://docs.nvidia.com/dgx/dgx-spark/support.html).
Field diagnostics require disruptive setup, including temporarily disabling
Secure Boot and switching console mode; they are not run as part of this
read-only investigation. No new kernel version is proposed as a proven fix.
