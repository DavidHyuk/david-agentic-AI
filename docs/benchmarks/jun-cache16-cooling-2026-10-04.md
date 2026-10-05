# Jun cache16 cooling deployment — 2026-10-04

**Historical report:** the policy below is superseded by
[cache20 cooperative protection](jun-cache20-cooperative-2026-10-04.md).
The later English retry reached92.0°C and caused a reviewed model stop; its
consumed retry is not replayed again. Original measurements remain intact.

The current provisional shared deployment uses cache16GiB, MTP ON, provider
128K per request×2, batch4096/ubatch1024, compatible runtime/repaired GGML.
All known agents/cron clients use the memory/slot/cooling proxy at8003;
backend8004 is internal. Current agent identities/context settings are retained.

Queue new requests at board90°C, recover after≤85°C for10s, and start background
photo/cron requests only at≤75°C. Cancel active hot requests by disconnecting
upstream; this backend cannot resume an interrupted answer. Never automatically
replay forwarded requests. Board≥92°C or GPU relative margin≤−4°C causes a
latched model stop. Existing sustained GPU and2/0.25GiB memory protection remain.
These are operator limits, not hardware guarantees; future memory demand is
empirical and cannot prove certain overflow. Bypassing clients/other GPU jobs
and driver/power faults remain outside the queue's authority.

The earlier physical host interruption occurred in the cache4 baseline, not
cache24. The interrupted31 completed rows are distinct from cache16 verification.
Historical OOM errors are retained separately from temperature evidence.

Five successful cache16 smoke checks used484-token inputs,10-token JSON outputs,
thinking off. Cold/warm TTFT0.839/0.097s and wall1.037/0.278s are short health
measurements, not Jun coding latency or matched cache4/cache16 speedups.
Three simultaneous requests finished1.918/1.855/2.895s; third admission wait1.854s.
Min available33.54GiB; peak board81.1°C/GPU72°C. A prior32-token smoke without
thinking-off produced no visible content; its failed receipt is retained locally.
Filled16GiB cache, large two-slot128K loads, long endurance and broad quality
are untested. A cache cap does not allocate that capacity upfront.

At October5 **04:25:14 UTC**, resumed photo work reached **92.2°C** after the
proxy signalled cancellation at91°C. The guard stopped only the model; the
host did not reboot. Available/free were31.79/24.97GiB. David/English stopped
through their model dependency. The75°C background entry rule was added after
this event, then exact incident/photo holds were reviewed and archived after
cooling. Model, all gateways and watchdog were restored. Two further background
requests completed without another thermal cancellation in the short observation.
The first cache16 health check must not be presented as proving photo endurance.

Startup GPU telemetry retries up to30s before first valid sample; memory/board
checks remain active. Preflight never succeeds without verified telemetry, and
genuine OOM/thermal holds remain latched across boot. `Linger=yes`, model and
all gateways are boot-enabled. Gateway preflight waits for expected model at8003.
Default/English schedules have8/5 registrations; default Observatory API responds.
The later thermal stop caused one English drill connection error. Its configured
one-time retry initially could not find `hermes` on the watchdog PATH; the owning
unit now explicitly includes the user CLI directory. Recovery queued that failed
execution once and persisted its retry key; successful jobs were not replayed.
Watchdog timer is enabled/active and its corrected check succeeded.
ClawGram uses family/Instagram/albums systemd timers; missing Hermes
cron/jobs.json there is normal. Successful inactive one-shot worker is normal.
No physical reboot or forced scheduled notification was performed for testing.

Three new separately labelled Langfuse experiments have37 traces/217 scores:
interrupted cache4 baseline, bounded cache16 health, and the protected photo
thermal-stop event. All IDs, score values, failure/cooling metadata were read
back. The thermal event has no invented request TTFT/TPS; it is a single stop
sample. Earlier uploads were not repeated, and these exports contain no raw
prompts, answers, images or logs. View them in
[the existing Langfuse project](https://us.cloud.langfuse.com/project/cmuthqc2u09qiad0dy8x51ett).

Private receipts are under `runtime/model-benchmarks/jun-memory-queue-20261004`.
Validation:683 David tests,331 ClawGram tests/2 skipped, installed systemd and
live flags/queue/service checks. A proposed return to24GiB would need measured
cache occupancy/peak budgeting, not the current unfilled-cache idle reading.
