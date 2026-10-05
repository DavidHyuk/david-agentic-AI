# Jun cache experiment interrupted by host power-off

This describes initial containment. Current20GiB cooperative protection and
reviewed recovery are in [the follow-up](jun-cache20-cooperative-2026-10-04.md).

Shared inference is held after the October 4 host interruption. The David-Agent
session stopped `hermes-cron-watchdog.timer/service` after reboot. Default and
English gateways are inactive; the independent ClawGram gateway was not
manually restarted. Model/photo incident holds remain intact. No request was
replayed and no new result was published to Langfuse in this experiment.

The private deployment receipt, installed override and model journal identify
the active baseline: **4GiB host prompt cache**, MTP ON with shared Q8_0 head /
draft maximum 2, provider 128K per request × 2, batch4096/ubatch1024, same
compatible runtime and repaired GGML as the earlier activation. Backend moved
to loopback8004 behind the streaming admission proxy at8003. Its experimental
emergency guard used available2GiB, free0.25GiB when available<4GiB. This policy
is not validated as safe. The 24GiB arm never started.

31 completed requests survive. The interrupted request was a Jun return with
19510 input tokens; three-request burst validation had not started. The run
has no completed-at marker and is marked `interrupted_host_poweroff` in its
deployment receipt. Do not present this as a completed cache comparison.

| Partial cache4 observation | Value |
|---|---:|
| Jun cold TTFT | 26.20s |
| Immediate cached Jun return TTFT | 0.14s |
| Jun return after 12 distinct contexts, no cached input | 26.74s |
| Minimum available / free in completed requests | 26.43 / 7.24GiB |
| Peak GPU temperature / minimum operating margin | 86°C / −4°C |
| Completed requests with hardware thermal slowdown | 5 |
| Last durable available / free | 27.27 / 8.08GiB |
| Last durable board / GPU temperature, GPU margin | 96.2 / 85°C, +2°C |

The baseline's churn uses frozen synthetic 7099-token prompts and bounded
structured outputs, not actual rooms. Jun uses the frozen earlier code-review
fixture. The saved records include TTFT, prefill/decode throughput, wall time,
cache-token counts, thermal and memory samples. Their differing prompt/output
lengths do not establish a TPS comparison between cache policies. Long-run
reliability, two filled 128K requests, broader correctness and the larger-cache
arms are untested.

Last completed request: October5 03:35:52 UTC; last model journal entry:
03:36:15 UTC; durable guard snapshot:03:36:18 UTC; new boot:03:51:16 UTC.
The precise shutdown instant is unknown. No new allocation error, Linux OOM,
Xid, thermal-critical or orderly shutdown entry was found near the interruption.
Older errors in the same boot do not establish this incident's cause.
Preserved evidence lives in private
`runtime/model-benchmarks/jun-memory-queue-20261004/incident-20261005`.
The new boot's model hold was created by a startup `nvidia-smi` timeout, not
an observation of the previous boot's power-off cause.

The candidate is now **16GiB host cache**, not a 16GiB minimum memory reserve.
It is prepared only: the installed override remains cache4 and no model is
running. If fully used, its cap could consume 12GiB more than cache4 and 8GiB
less than cache24. Cache capacity does not imply upfront allocation or prove
safe peak memory. It may prevent Jun prefix eviction across other workloads;
it does not accelerate the prefill of new uncached inputs. Review thermal and
power behavior before deployment or another GPU load experiment.

The shared admission implementation tracks available/free RAM, running backend
requests and empirical incremental demand, admits at most two concurrent
requests, prioritizes waiting interactive work and bounds queued body memory.
Scheduled requests can run alongside interactive work when the estimate fits.
Missing telemetry refuses submission. Forwarded requests are never retried
automatically. The incremental estimate is not a proven minimum allocation or
a certainty-of-overflow test; a queue cannot prevent driver/power faults or
manage clients that bypass its endpoint. ClawGram classifies photo requests
as background and delegates admission to this proxy when present. Completed
tests do not replace the unfinished production burst validation.

Langfuse retains the already verified earlier MTP results at
[the project dashboard](https://us.cloud.langfuse.com/project/cmuthqc2u09qiad0dy8x51ett).
This interrupted run is preserved locally and has **not** been uploaded; no
cache16/cache24 speedup or safety result is claimed.

Post-reboot checks passed: 682 David-Agent tests, ClawGram 320 passed /
2 skipped, installed systemd verification, no model/proxy PID, watchdog
inactive and model/photo holds present. These checks did not run GPU inference.
