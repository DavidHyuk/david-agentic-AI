# Jun cache20 and cooperative protection — 2026-10-04

Current provisional serving retains **20GiB host prompt-cache capacity, MTP ON,
provider128K per request×2**, batch4096/ubatch1024 and the compatible repaired
runtime. Existing agent64K settings and identities are unchanged.

At exposed board85°C the guard limits model CPU execution to200% of one core;
at90°C and above it uses1% and queues new work while preserving active answers.
There is no92°C board-temperature kill. Memory pressure, GPU critical relative
margin and invalid telemetry also queue and throttle instead of killing the
model. Resource recovery requires10s of valid acceptable samples. Hot/warm
board pacing releases after≤85°C/≤80°C respectively for10s. Background photo
and cron requests start only at≤75°C. These are operator choices, not hardware
trip limits; CPU pacing cannot stop GPU kernels already submitted or guarantee
thermal recovery, memory reclamation or immunity to actual OOM/client timeouts.

The installed guard is opt-in cooperative mode; legacy stop behavior is not
installed. Model dependency usesWants rather thanBindsTo the guard. The cron
watchdog checks the shared admission queue before gateway recovery/retries and
defers while active, queued, cooling, resource-paused or unverified. The same
model and all gateway PIDs survived the policy installation. No successful
scheduled job or external delivery was replayed. The earlier English drill
failure and consumed retry remain history; future regular schedules are retained.

Two20GiB health requests before the final cooperative change used484-token
input,10-token exact JSON output, thinking off and concurrency1. First-after-
restart/warm TTFT1.028/0.102s; full latency1.292/0.280s; native decode34.06/50.41
tokens/s. Available minimum34.84GiB; board/GPU maximum74.7/72°C. The first
request was cold only for prompt state, with OS/model-file state warm.

One warm check after the final policy change reused480/484 tokens on the same
model: TTFT0.111s, wall0.292s, native decode49.68 tokens/s, available minimum
34.58GiB, board/GPU maximum68.5/63°C. These are bounded transport checks,
not Jun/LeetCode TPS or a matched20/24 speed comparison. Cache20 occupancy,
long thermal endurance, two filled128K contexts and broad quality are untested.

Cache24 can retain more prompts after eviction. It does not directly improve
already cached requests, uncached prefill or decoding. Current20 remains David's
selected cap;24 has never run in this experiment. The initial physical shutdown
occurred during cache4; prior OOM evidence and high board readings do not prove
one cause. Historical cache16 cancellation subsequently reached92.2°C during
photo work and92.0°C during an English retry; both deliberate model stops
left the host up. Those stop policies are superseded.

Validation:691 David tests; ClawGram347 passed/2 skipped; mocked high board,
GPU/memory/sensor/quota faults and10s recovery, active-stream preservation,
watchdog recovery deferral, installed flags/dependencies and unchanged PIDs.
An earlier real kernel1% quota probe preserved the same request/answer;
no natural90°C stress was induced for this verification.

View separately labelled historical and current bounded runs in
[Langfuse](https://us.cloud.langfuse.com/project/cmuthqc2u09qiad0dy8x51ett).
Private receipts are in`runtime/model-benchmarks/jun-memory-queue-20261004`.
Exports exclude prompt/answer text, images, credentials and raw logs. Prior
uploads and their actual policies are retained rather than overwritten.
Five recovery experiments contain40 traces/235 scores; all IDs, numerical
values and policy metadata were read back. These comprise cache4 interruption,
cache16 health, its first photo stop, pre-cooperative cache20 readiness and the
final warm cooperative check. No prior successful upload was repeated.
See [historical cache16](jun-cache16-cooling-2026-10-04.md) and
[original interruption](jun-cache-poweroff-2026-10-04.md).
