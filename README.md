# david-agentic-ai

A personalized, always-on AI partner for **David Choi**, built on the
[**Hermes Agent**](https://github.com/NousResearch/hermes-agent) framework
(Nous Research). It learns David's life and goals over time and proactively helps
with research and interview preparation delivered to the David **Telegram**
bot, plus English feedback delivered to a dedicated English **Telegram** bot:

1. **LLM/LVM research** — daily arXiv + Hugging Face ingestion and a personalized twice-weekly digest.
2. **Staff/Senior MLE interview prep** — MLE drills, beginner coding, and a weekly adaptive system-design interview on a noon schedule.
3. **English practice** — turns tutor recordings + corrections into spaced-repetition drills.
4. **Daily podcast English** — sends the latest watched podcast
   link plus long-sentence and weak-pattern practice at 18:00 Monday–Friday,
   with weekday-material review on weekends, through
   the existing English Telegram bot.

Google Calendar support is retained for a later phase, but its skill, MCP
connection, and scheduled brief are currently disabled.

This repository is the **single source of truth** for the David and English
agent configurations. David-agent assets are synced into `~/.hermes` by
`bootstrap/stage.py`; both tutor and podcast English skills are synced into the
existing English profile by `bootstrap/stage_english_profile.py`.

## Why a config repo instead of ad-hoc setup?
Hermes stores skills, memory, personality, scripts, and cron jobs under `~/.hermes`.
Keeping them version-controlled here makes the setup **reproducible, testable, and
maintainable**: edit in the repo, re-run `stage.py`, done. The runtime stays a
disposable cache.

## Automatic Codex usage-limit recovery

Install the standalone host helper (separate from Hermes staging):

```bash
bash bootstrap/install_codex_auto_resume.sh
codex-auto-resume status
journalctl --user -u codex-auto-resume.service -f
```

The enabled user service polls the local Codex thread index/rollouts every ten
seconds. A root session ending with `usage_limit_exceeded` gets one persistent
retry **90 seconds after the server's reset time**, using structured quota windows
or the usage error's local `try again at …` clock. Only when no reset time is
available does it wait **five hours after the failure, plus 90 seconds**.
The clock is resolved against the failure's date, including midnight rollover;
parser upgrades correct existing pending reservations without duplicating jobs.
Existing unresolved failures from the last 24
hours are recovered on installation. Later failures also survive watcher downtime.
A new manually submitted turn supersedes its pending retry. Context-window,
network and ordinary tool errors do not trigger quota recovery.
Every submission rechecks that the original quota failure is still current;
completed, manually stopped and already resumed sessions are skipped. Manual
time reservations also require a currently unresolved usage-limit stop.

Retries use `codex exec resume --json`, preserving the original session ID,
working directory, model, reasoning effort and last actual turn's sandbox access.
When an open TUI owns the idle session's writer, the helper submits `turn/start`
through that same local Codex daemon and observes its durable outcome. An active
turn is skipped. It does not fork another session or merely queue a message.
An existing TUI connected to that same daemon receives live progress, tool output
and the final reply without reconnecting. A separate app or `--no-daemon` writer
outside that daemon must release its lock before recovery can proceed.
Approval requests are disabled for unattended execution. Up to three independent
systemd workers run concurrently; SSH/tmux disconnects and watcher restarts do
not stop them. Persistent private state and JSONL worker output live in
`~/.local/state/codex-auto-resume/`. A turn is marked complete only after verified
`turn.started` / `turn.completed` events and a successful exit. Another quota
failure schedules another retry using its reset time; ambiguous worker crashes are recorded
as `needs_review` rather than blindly replaying external actions.

The former command remains available and now saves a persistent schedule:

```bash
codex-auto-resume <SESSION_ID> 03:10
codex-auto-resume <SESSION_ID> now
codex-auto-resume cancel <SESSION_ID>    # cancel this pending retry
codex-auto-resume exclude <SESSION_ID>   # cancel and exclude future detection
```

The old script is backed up during installation. Local-time `HH:MM` reservations
include the same 90-second grace; `now` runs at the next poll. `status` shows the
worker unit and private output path. Reconnect to the resumed work with
`codex resume <SESSION_ID>`; the TUI's previous limit error is historical, not a
new request. The host's enabled user linger keeps the service running after logout
and at boot. Tests use isolated `--codex-home` / `--state-dir` directories and
shortened watcher delays; production uses server reset times or the five-hour fallback.
Live validation used a synthetic quota failure in an isolated rollout, a two-second
delay and real authenticated Codex turns that wrote verified files. Both normal
execution and the shared-daemon writer-conflict path kept one original session.
An additional live TUI test kept the terminal attached and captured progress,
tool output and the final reply delivered through the same `turn/start` path.

This is an internal Codex lifecycle helper for existing tasks, not a new Hermes
agent, scheduled content workflow, profile, Telegram bot or Observatory room.

## Architecture

```
Local DGX Spark (llama.cpp @ :8003, Qwen3.8 Flash-Next IQ4_XS, 2 × 64K slots)
        │  OpenAI-compatible API
        ▼
   David Hermes profile ───────────────────────────────────────► David Telegram bot
        │ skills (procedural)   │ cron (schedule)   │ memory (who David is)
        ├─ Built-in Browser ── agent-browser ── local Chromium CDP (:19222)
        ├─ papers-digest  ── reads ~/.hermes/data/papers/papers.db
        ├─ interview-prep ── MLE drills + curated coaches + adaptive coach_state.json
        └─ calendar-assistant ─ disabled; source retained for later

   English Hermes profile ─────────────────────────────────────► English Telegram bot
        │ isolated SOUL / memory / sessions / Telegram token
        ├─ english-practice ─ Kakao webhook → intake + SRS review/drill
        └─ english-podcast-coach ─ YouTube app watch history → 18:00 links + long-sentence practice

 arXiv + Hugging Face ── papers_ingest.py ── SQLite paper catalog
                              ▲
                    systemd timer (08:00 daily)
```

## Repository layout
| Path | Purpose |
|---|---|
| `config/soul/SOUL.md` | Agent personality (→ `~/.hermes/SOUL.md`) |
| `config/memory/{USER,MEMORY}.md` | Seed memory (→ `~/.hermes/memories/`) |
| `config/config.fragment.yaml` | Non-secret settings merged into `config.yaml` |
| `config/env.example` | Template for `~/.hermes/.env` secrets |
| `skills/<category>/<name>/SKILL.md` | Three David-agent skills (two active, Calendar disabled) |
| `profiles/english/` | Isolated English SOUL, memory, config, tutor skill, and podcast skill |
| `scripts/*.py` | Standalone, unit-tested helpers (→ `~/.hermes/scripts/`) |
| `cron/jobs.yaml` | Declarative Telegram notification schedule |
| `docs/kakao-channel-setup.md` | Kakao Channel chatbot and webhook setup |
| `bootstrap/install.sh` | One-shot installer + orchestrator |
| `bootstrap/stage.py` | Idempotently stage repo → `~/.hermes` |
| `bootstrap/register_cron.py` | Register `jobs.yaml` with `hermes cron` |
| `bootstrap/install_papers_service.sh` | Install daily paper ingestion service/timer |
| `bootstrap/install_cron_watchdog.sh` | Install automatic cron-stall detection and gateway recovery |
| `bootstrap/stage_english_profile.py` | Stage only the isolated English-coaching Hermes profile |
| `bootstrap/install_english_bot.sh` | Create/stage the English profile, install its gateway, and sync cron jobs |
| `scripts/english_podcast.py` | Channel transcripts and selected-video long-sentence practice |
| `scripts/youtube_history.py` | Import cookies over SSH and send the latest watched podcast link headlessly |
| `scripts/youtube_browser_login.py` | Open temporary DGX Chromium over an SSH tunnel for direct YouTube login |
| `scripts/export_youtube_cookies.py` | Export YouTube-only cookies on the MacBook for server connection |
| `scripts/papers_ingest.py` | Fetch and merge arXiv/Hugging Face paper metadata |
| `scripts/papers_digest.py` | Read-only recommended/recent/trending paper digest |
| `scripts/interview_progress.py` | Concrete study messages, feedback, hints, adaptive reviews, weekly metrics |
| `scripts/reward_system.py` | Evidence-backed Career Cash, streaks, weekly missions, and virtual offer unlocks |
| `scripts/leetcode_sync.py` | Owner-only LeetCode session link and read-only solved-history snapshot |
| `scripts/chatgpt_project_sync.sh` | Daily selected-project browser observation and atomic local RAG refresh |
| `skills/career/interview-prep/references/coach_catalog.json` | Curated coding curriculum plus General/ML/Agent design interviews |
| `skills/career/interview-prep/references/system-design-interviewer.md` | Stateful interview flow, commands, rubric, and solution gate |
| `skills/career/interview-prep/references/company-coding-strategy.md` | Company-aware LeetCode/practical-coding preparation strategy |
| `browser/setup_browser.sh` | Pin agent-browser + install the local Chromium CDP service |
| `browser/browser_smoke.py` | Verify browser navigation, click, DOM read, and snapshot |
| `mcp/setup_google_calendar.py` | Securely configure Google's official Calendar MCP |
| `mcp/calendar_smoke.py` | Verify MCP discovery and a read-only Hermes calendar call |
| `docs/next-steps.md` | Agreed paper/job questions and Kakao English E2E checklist |
| `local-model/run_flash_next.sh` | Launch Qwen3.8 Flash-Next UD-IQ4_XS on llama.cpp |
| `local-model/setup_vllm.sh` | Create an isolated CUDA-compatible vLLM runtime for legacy models |
| `local-model/run_model.sh` | Launch Qwen3.6 FP8, Qwen3.8 27B FP8, or another vLLM alternative |
| `local-model/restart_service.sh` | Restart a legacy vLLM service and optionally wait for API readiness |
| `local-model/model_preflight.py` | Validate checkpoint quantization and context |
| `local-model/eval/` | Reproducible local agent-task model benchmark and synthetic cases |
| `/home/david/workspace/models/download_model.py` | Download and manage Hugging Face checkpoints outside this config repo |
| `config/config.fragment.minimax.yaml` | Hermes provider config for MiniMax |
| `tests/` | Pytest suite |

## Quick start

```bash
# 0. Install Python tooling deps
python3 -m pip install -r requirements.txt

# 1. Run the bootstrap (installs Hermes if missing, stages config, sets model)
bash bootstrap/install.sh

# 2. Download the 4-bit GGUF into the models workspace and build llama.cpp with CUDA
hf download unsloth/Qwen3.8-Flash-Next-GGUF \
  --include 'UD-IQ4_XS/*' --include 'mmproj-F16.gguf' \
  --local-dir /home/david/workspace/models/unsloth/Qwen3.8-Flash-Next-GGUF
git clone https://github.com/ggml-org/llama.cpp /home/david/workspace/llama.cpp
git -C /home/david/workspace/llama.cpp switch --detach 526c43b8f
cmake -S /home/david/workspace/llama.cpp -B /home/david/workspace/llama.cpp/build-qwen38 \
  -DGGML_CUDA=ON -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc
cmake --build /home/david/workspace/llama.cpp/build-qwen38 -j 8 --target llama-server
bash local-model/run_flash_next.sh

# In another shell, verify model discovery and OpenAI tool calling
python3 local-model/smoke_test.py

# Verify Hermes's built-in browser runtime
bash browser/setup_browser.sh --check
python3 browser/browser_smoke.py

# Optional but recommended: keep the model endpoint running across logouts/reboots
bash local-model/install_service.sh

# 3. Verify a plain chat
hermes -z "Which model are you, and what do you know about me?"
```

Then complete the **interactive, one-time** steps `install.sh` prints:
- `bash bootstrap/install_papers_service.sh` → migrate legacy papers and enable
  daily metadata ingestion.
- `hermes gateway setup` → connect **Telegram**, then `hermes gateway install`.
- Create the dedicated English bot with BotFather, then configure its isolated
  profile and gateway:

  ```bash
  bash bootstrap/install_english_bot.sh
  hermes -p english gateway setup
  # Choose Telegram, enter the new bot token, and message the bot once to pair it.
  bash bootstrap/install_english_bot.sh
  ```

  The English token is stored only in `~/.hermes/profiles/english/.env`. The same
  installer disables the old morning transcript timer and registers the 18:00
  watch-history digest in this existing bot; no second token is needed.
- `bash bootstrap/install_cron_watchdog.sh` → recover automatically from a
  permanently stuck cron worker.
- Create Telegram groups for papers, MLE interviews, system design, and LeetCode
  practice; add the David bot and set their IDs in `~/.hermes/.env` (details
  below).
- `python3 bootstrap/register_cron.py` → schedule the Telegram briefs.
- Follow [Kakao Channel setup](docs/kakao-channel-setup.md) to receive tutor feedback
  through the Channel chatbot, then turn it into Telegram drills.

### Always-on model service

`local-model/install_service.sh` installs and enables the user-level
`hermes-vllm.service`. It also installs a gateway systemd drop-in that requires
the model service and runs `wait_for_vllm.py` before Hermes starts. This prevents
fresh cron jobs from racing the several-minute model load after a reboot.
The service name is retained for compatibility; it now runs the Qwen3.8
Flash-Next 4-bit GGUF through llama.cpp. Manage it with:

```bash
# Start, stop, and inspect the service
systemctl --user start hermes-vllm.service
systemctl --user stop hermes-vllm.service
systemctl --user status hermes-vllm.service

# Follow startup and runtime logs (initial model loading takes a few minutes)
journalctl --user -u hermes-vllm.service -f
```

To restart and wait for the correct model to appear:

```bash
systemctl --user restart hermes-vllm.service
python3 scripts/wait_for_vllm.py --url http://127.0.0.1:8003/v1/models \
  --expected-model Qwen3.8-Flash-Next-UD-IQ4_XS --timeout 900
```

`run_flash_next.sh` uses two 64K request slots and lets llama.cpp fit layers to the
DGX Spark's available unified memory. Its server binds only `127.0.0.1:8003`.
An existing swap file can absorb ordinary host memory pressure, but model and
CUDA allocations must still fit in available unified memory. The legacy
`restart_service.sh` GPU reservation setting applies only when the service is
restored to the vLLM launcher.
The Flash-Next launcher now refuses to start without a working NVIDIA GPU;
an `active` CPU-only fallback is not a healthy agent endpoint. The user service
does not repeatedly restart on this missing-GPU exit; restore driver access
before starting the model and gateways again.

For a temporary local test of the separately downloaded official Qwen3.8 27B
FP8 checkpoint, stop the shared model and both gateways first, then run:

```bash
HERMES_VLLM_HOST=127.0.0.1 HERMES_VLLM_PORT=8004 \
  bash local-model/run_model.sh qwen38-27b
```

This uses a 64K context and does not change Hermes's default model. A
2026-09-29 run passed tool and vision smoke checks but was interrupted by a
host-level outage before the full benchmark finished; do not treat it as a
validated production replacement. On this Spark, restore the NVIDIA driver
and verify `nvidia-smi` before launching either GPU backend.

### Bounded local-model inspection

After the October 3 host reset, CPU-only model inspection uses a separate
systemd memory/runtime boundary and pressure monitor. The streaming GGUF helper
reads headers and tensor descriptors without mapping weights or retaining the
vocabulary. See [usage](local-model/eval/README.md#bounded-cpu-diagnostics-after-the-october-3-reset)
and the [incident report](docs/benchmarks/flash-prefill-diagnostic-incident-2026-10-03.md).
These limits do not guarantee protection against GPU-driver or host failures.

### Agent-task model benchmark

The [interactive coaching latency notebook](local-model/eval/README.md#interactive-coaching-latency-and-experiment-tracking)
measures short coding/English replies, longer explanations, cached followups,
and two overlapping requests on the existing two-slot 128K provider. It imports
the earlier matched MTP results, builds an offline comparison dashboard, and
prepares metrics-only Langfuse exports (or optional LangSmith traces). It is an
internal evaluation helper with no new room, schedule, gateway or messaging.
Use `--input-tokens 2048` to compare a smaller synthetic payload while preserving
the two 128K slots. Web character conversations now display streamed assistant
text through the existing authenticated Hermes session API; complete history
remains owned by Hermes. See the [Langfuse first-use guide](docs/langfuse-quickstart.md)
for Cloud signup, private credentials, experiment comparisons and exports.

David/English Hermes conversations also use an optional observer plugin to
record agent, LLM and tool spans in Langfuse with background export. It captures
bounded question/answer text, usage, latency and observed visible-stream TTFT;
system prompts, tool bodies and images are omitted. See the
[agent visualization and tracing guide](docs/agent-observability.md) for
Graph/Sessions navigation, isolated ClawGram Studio state inspection, and
`bootstrap/stage_conversation_tracing.py` installation/disable commands.

Jun's **코딩** web conversation defaults to **빠른 답변** and offers **깊이 생각**
for normal reasoning/full tools. Fast mode disables hidden thinking, narrows
tool schemas, and references oversized past `session_search` results through
private immutable originals in `~/.hermes/data/jun-context/`. Jun can read those
originals when needed. Durable history and code are preserved. Changing learning
facts and retrieved code follow the stable system prefix for cached followups.
Other rooms and Telegram conversations retain their existing request policy.

Install the optional policy from this repository, then restart the idle owning
gateway; use normal Observatory staging for the corresponding web controls:

```bash
/home/david/miniconda3/bin/python3 bootstrap/stage_leetcode_latency.py --hermes-home ~/.hermes
systemctl --user restart hermes-gateway.service
```

The helper backs up config/plugin and preserves tracing. To disable, set
`leetcode_latency.enabled: false` in `~/.hermes/config.yaml` and restart that
gateway when idle. Restore the helper's private backup for rollback. Keep
`data/jun-context` while archived references are in use. The provider retains
two 128K slots and the agent's separate 64K setting. See the
[Jun measurements and limits](docs/benchmarks/jun-latency-2026-10-04.md).

**Current provisional deployment (2026-10-04):**20GiB host-cache cap, MTP ON,
128K per request×2 and shared memory/cooling queue at8003. At85°C limit model
CPU execution to200% of one core; at90°C and above use1% and queue new requests
while preserving active answers. There is no92°C board-triggered kill.
Memory/GPU protection also queues and paces instead of killing the model.
Recovery uses10s hysteresis; background work starts only at≤75°C. Watchdog
recovery defers while inference is active, queued or protected. Real OOM,
hardware faults and client timeouts can still interrupt answers. Filled20GiB
cache and sustained cooling remain untested;24GiB has never run. See
[current policy and bounded evidence](docs/benchmarks/jun-cache20-cooperative-2026-10-04.md).

Earlier on 2026-10-04 the shared provider enabled MTP with the compatible feature
runtime, shared Q8_0 head and two draft tokens. It retains 128K per request
and two slots. That verified activation capped host prompt cache at 4GiB and
stopped below 20GiB available
or below 32GiB available with less than 4GiB free. ClawGram photo admission
remains 24/8GiB. Matched completed hint decoding improves 26.60→32.75 TPS;
the long Jun code review improves 25.21→29.49 TPS. Cold TTFT increases slightly.
This is a decode improvement, with long-input prefill still limiting response
time. Find the three new `Jun MTP activation` experiments in Langfuse
(20 traces / 120 performance scores); the
[activation report](docs/benchmarks/jun-mtp-2026-10-04.md) records output-length,
concurrency, memory, thermal and quality limits. Experiment metadata includes
the cache and memory guard budgets. Provider changes do not change agent
profile ownership or add a new Observatory room.

The version-controlled [120-case synthetic benchmark](local-model/eval/README.md)
uses four balanced buckets: short tasks, scripted multi-tool calls, multi-turn
long-horizon state, and context-heavy retrieval. Validate the fixture, then run
each local model sequentially into separate JSONL files, unloading one before
loading the other on the Spark, and summarize paired cases by bucket. The optional overnight orchestrator
temporarily pauses the main/English gateways and cron watchdog, runs Flash-Next
then Qwen3.6 35B, and restores the original service state through an EXIT trap;
see [benchmark instructions](local-model/eval/README.md). Scoring checks an
exact JSON subset with explicit case-insensitive `$contains` and Korean-language
`$language` checks where appropriate; tool results come only from predefined
mock scripts.
This measures local API behavior, not live Hermes end-to-end execution, real
tools, or source fetching.
Complete paired runs, or explicitly labeled paired subsets after an outage,
can additionally be anonymized for a separate
[blind semantic audit](local-model/eval/README.md) using a frozen rubric; keep
those judgments distinct from the deterministic score.
The runner also records client TTFT and decoding estimates, llama.cpp native
phase timings, and optional vLLM prefill/decode TPS plus server TTFT via
`--server-metrics-url`. It keeps exporter overhead and missing measurements
visible; see [performance measurement instructions](local-model/eval/README.md#ttft-and-phase-throughput).
Use fresh output files when the runner or serving configuration changes.
It is an internal, nonproduction evaluation helper and does not add a Hermes
agent, cron job, bot, or Observatory room. The
[2026-09-30 partial comparison](docs/benchmarks/qwen36-vs-flashnext-v2-2026-09-30.md)
records the original three complete buckets and 2/30 context pairs separately
from the supervised October 1 retry, which completed all 120 Qwen cases
(72 deterministic passes, including 29/30 contexts), with 290 requests measured.
The preserved original Flash arm passed 110/120. The final relaxed Flash retry
also completed 120 cases with 110 passes and 338/338 native phase measurements,
no process pauses, and no between-case cooling waits. At 88°C or above it would
wait only before starting the next case; maximum observed temperature was 87°C.
The report includes Qwen timing estimates with logged pause waits excluded.
An earlier separate Flash audit without
forced pauses measured 50 requests across 15 cases before stopping on observed
thermal slowdown; it provides no completed unpaused long-context comparison.
Codex authored the 120 cases and expected
answers; they are not sampled Hermes usage or human-labeled ground truth.
Repeated templates, mock tools, six-turn conversations, generated long archives,
and JSON requirements limit representativeness; 12/92 original paired judgments
were uncertain. Compare fixture pass counts, successful-work speed, and service
stability separately. These scores do not establish production accuracy or
universal model superiority. After the unexplained reset, use
[supervised retry guidance](local-model/eval/README.md#supervised-retry-after-the-september-30-host-reset)
and fresh outputs for changed serving settings; memory caps cannot guarantee
that a host reset will not recur.

## Automatic verified commit and push

Codex owns `.codex/hooks/auto_git_commit.py`; Cursor delegates to that same
implementation through `.cursor/hooks.json`. On a trusted Stop event it stages
only allowlisted project files, excludes secrets/runtime data/binary assets,
requires `pytest -q` to pass, creates a Conventional Commit, and pushes the
current upstream branch. A push failure is retried at the next Stop event even
if there are no new changes.

After changing `.codex/hooks.json` or the hook implementation, open Codex
`/hooks` and review/trust the command. Diagnostics are written to stderr and
stored in `.git/codex-auto-commit.log`; hook stdout stays empty to satisfy the
Codex `Stop` protocol. To run the same flow manually:

```bash
python3 .codex/hooks/auto_git_commit.py </dev/null
```

See [AGENTS.md](AGENTS.md) for the commit and safety rules.

## 논문 수집과 digest 사용법

논문 수집은 Hermes 대화 세션과 분리된 `hermes-papers-ingest.timer`가 매일
08:00에 실행합니다. 수집 대상은 arXiv의 `cs.AI`, `cs.CL`, `cs.LG`,
`cs.CV`와 Hugging Face Daily Papers입니다. 이 단계에서는 PDF를 내려받거나
LLM 분석을 실행하지 않습니다.

처음 한 번 설치합니다.

```bash
bash bootstrap/install_papers_service.sh
```

설치 시 기존
`/home/david/workspace/Subscribe-Papers/data/papers.db`의 45편을 새 카탈로그로
한 번 이관한 뒤 실제 수집을 실행합니다. 원본 DB와 PDF는 수정하거나 삭제하지
않습니다.

상태와 최근 로그를 확인합니다.

```bash
python3 ~/.hermes/scripts/papers_ingest.py --status
systemctl --user status hermes-papers-ingest.timer
journalctl --user -u hermes-papers-ingest.service -n 50 --no-pager
```

필요하면 수동으로 다시 수집할 수 있습니다.

```bash
systemctl --user start hermes-papers-ingest.service

# 특정 소스만 직접 실행
python3 ~/.hermes/scripts/papers_ingest.py --source arxiv
python3 ~/.hermes/scripts/papers_ingest.py --source huggingface
```

Hermes가 사용할 후보를 직접 확인합니다.

```bash
python3 ~/.hermes/scripts/papers_digest.py \
  --mode recommended --days 4 --limit 5

python3 ~/.hermes/scripts/papers_digest.py \
  --mode recent --days 2 --limit 10 \
  --keywords LLM VLM multimodal agent "browser agent" MCP GRPO
```

Hermes의 Python helper는 항상 `python3`로 실행합니다. 런타임에는 `python`
alias가 없으며, SOUL과 각 skill도 `python`을 탐색하거나 재시도하지 않도록
명시합니다.

매일 전달되는 논문 digest는 각 항목마다 Telegram에서 바로 열 수 있는
canonical `https://...` 링크를 별도의 `Link:` 줄로 포함합니다.

SQLite는 원본 메타데이터와 ingestion 이력의 기준 저장소입니다. Qdrant는
PDF 본문 질의·논문 간 비교가 필요해지는 다음 단계까지 사용하지 않습니다.

## Google Calendar MCP — 추후 활성화

> 현재 상태: `calendar-assistant`는 `config/config.fragment.yaml`에서
> 비활성화되어 있고 `morning-brief`도 cron에서 제거되었습니다. 지금은 아래
> OAuth 작업을 진행할 필요가 없습니다. 이 절은 추후 재개용으로 보존합니다.

Hermes는 Google 공식 Calendar MCP 서버를 사용합니다. 기본 설정은 읽기
전용이며 `list_calendars`, `list_events`, `get_event`만 허용합니다. 일정
생성·수정·삭제 권한은 포함하지 않습니다.

### 1. Google Cloud 설정

Hermes가 사용할 Google Cloud 프로젝트에서 다음 작업을 한 번 수행합니다.

1. **Google Calendar API** (`calendar-json.googleapis.com`)를 활성화합니다.
2. **Google Calendar MCP API** (`calendarmcp.googleapis.com`)를 활성화합니다.
3. Google Auth Platform의 OAuth 동의 화면을 설정합니다.
4. External 테스트 앱이면 David의 Google 계정을 Test users에 추가합니다.
5. 다음 세 가지 읽기 전용 scope를 추가합니다.

   ```text
   https://www.googleapis.com/auth/calendar.calendarlist.readonly
   https://www.googleapis.com/auth/calendar.events.freebusy
   https://www.googleapis.com/auth/calendar.events.readonly
   ```

`gcloud`가 설정돼 있다면 API는 다음 명령으로 활성화할 수 있습니다.

```bash
gcloud services enable \
  calendar-json.googleapis.com \
  calendarmcp.googleapis.com \
  --project=YOUR_PROJECT_ID
```

### 2. Web OAuth client 생성

Google Auth Platform에서 애플리케이션 유형이 **Web application**인 OAuth
client를 생성합니다. Authorized redirect URI에는 아래 값을 정확히
등록합니다.

```text
http://127.0.0.1:8765/callback
```

다운로드한 JSON은 저장소 밖의 비공개 경로에 보관합니다.

```bash
mkdir -p ~/.config/google
chmod 700 ~/.config/google
install -m 600 ~/Downloads/YOUR_DOWNLOADED_CLIENT.json \
  ~/.config/google/hermes-calendar-client.json
```

### 3. Hermes 설정 및 OAuth 승인

GUI 브라우저를 열 수 있는 터미널에서 실행합니다.

```bash
python3 mcp/setup_google_calendar.py \
  --credentials ~/.config/google/hermes-calendar-client.json
```

Google 동의 화면에서 위 세 가지 읽기 전용 권한을 승인합니다. 설정기는
MCP 정보를 `~/.hermes/config.yaml`에 반영하고 파일 권한을 `0600`으로
제한합니다. OAuth token은 `~/.hermes/mcp-tokens/`에 저장됩니다.

### 4. 상태 및 E2E 확인

설정 상태는 언제든 변경 없이 확인할 수 있습니다.

```bash
python3 mcp/setup_google_calendar.py --check
```

실제 MCP 연결, 도구 검색, Qwen3.6의 `list_calendars` 호출까지 검증합니다.
테스트는 캘린더 이름이나 ID를 출력하지 않습니다.

```bash
python3 mcp/calendar_smoke.py
```

마지막 줄에 `HERMES_CALENDAR_OK`가 나오면 정상입니다. 자세한 Cloud Console
화면과 보안·해제 절차는
[Google Calendar MCP 상세 가이드](docs/google-calendar-mcp.md)를 참고합니다.

## 카카오톡 채널 활성화

이 연동은 기존 개인 카카오톡 대화방을 읽지 않습니다. 영어 선생님이
**카카오톡 채널 챗봇**으로 보낸 메시지만 수집해 로컬 LLM 분석과 Telegram
복습에 사용합니다.

### 1. 로컬 수집 서버 활성화

프로젝트 루트에서 다음 설치 스크립트를 한 번 실행합니다.

```bash
bash bootstrap/install_kakao_services.sh
```

이 명령은 다음 작업을 자동으로 수행합니다.

- Kakao/English 스크립트와 스킬을 `~/.hermes`에 배치
- `~/.hermes/.env`에 비밀 `KAKAO_WEBHOOK_PATH` 생성
- 현재 CPU에 맞는 `cloudflared` 설치
- `kakao-webhook.service` 등록 및 시작; 임시 주소 모드는 `kakao-tunnel.service`도 시작
- 터널 재시작·DGX 재부팅 시 현재 연결을 검증하고 비밀 URL 파일을 자동 갱신

임시 주소 모드의 서비스 상태는 다음과 같이 확인합니다. 두 줄 모두 `active`여야 합니다.
단, 이 상태만으로 카카오에 등록한 URL의 유효성을 확인할 수는 없습니다.

```bash
systemctl --user is-active kakao-webhook.service kakao-tunnel.service
```

### 2. Open Builder 스킬 URL 입력

현재 머신에서는 전체 스킬 URL이 다음 파일에 저장됩니다.

```bash
cat ~/.hermes/data/english/kakao-skill-url.txt
```

출력된 한 줄 전체를 Open Builder의 `스킬 → English Feedback Intake → URL`
필드에 붙여넣고 저장합니다. 이 URL에는 비밀 경로가 포함되므로 Git,
스크린샷, 메신저에 공유하지 않습니다.

URL 파일이 없거나 Quick Tunnel을 다시 시작했다면 현재 HTTPS origin을
직접 조합하지 말고 설치 스크립트를 다시 실행해 URL 파일을 갱신합니다.

```bash
bash bootstrap/install_kakao_services.sh
```

### 3. 폴백 블록과 채널 연결

Open Builder에서 다음 순서로 설정합니다.

1. `시나리오 → 기본 시나리오 → 폴백 블록`을 엽니다.
2. 상단 `스킬 검색/선택`에서 `English Feedback Intake`를 선택합니다.
3. 스킬 버전을 선택합니다. 별도 파라미터는 추가하지 않습니다.
4. `봇 응답`의 `+`를 누르고 **`스킬데이터로 사용`**을 선택합니다.
   기존 `제가 할 수 있는 일이 아니에요` 텍스트를 단순히 수정하는 것이
   아닙니다. 이 문구는 폴백 블록의 유일한 응답인 동안 비워 둘 수
   있으므로, 스킬데이터 응답을 먼저 추가한 다음 기존 텍스트형 응답을
   제거합니다.
5. 저장한 뒤 테스트 봇에서 아래 샘플을 전송합니다.

   ```text
   You said: I am agree.
   Better: I agree.
   ```

6. `피드백을 저장했어요. 다음 영어 복습 알림에 반영할게요.`라고 응답하면
   스킬과 응답 형식 연결이 정상입니다. 봇테스트의 발신자 ID는 실제
   카카오톡 앱의 ID와 다르므로 여기서는 응답 형식만 확인합니다.
7. 왼쪽 상단의 `연결된 채널 없음`에서 만든 카카오톡 채널을 선택한 뒤
   챗봇을 배포합니다.
8. `설정 → 카카오톡 채널 연결`에서 운영 채널이 `David English Feed`,
   봇 상태가 `실행`인지 확인합니다.
9. 카카오톡 채널 관리자센터의 `1:1 채팅 → 채팅 설정`에서 상담원용
   1:1 채팅을 끕니다. 이 수집 채널은 상담원 연결을 사용하지 않습니다.
   `비즈니스 도구`의 채팅방 리스트 메뉴나 커스텀 메뉴가 켜져 있다면
   함께 끕니다.
10. `프로필 → 채널홈 설정`에서 **채팅 카드**를 추가/활성화하고 그 안에
    **챗봇 채팅**이 노출되는지 확인한 뒤 저장합니다. 카카오톡의 기존
    1:1 상담방은 챗봇 방으로 자동 전환되지 않습니다. 기존 방 우측 상단
    홈 아이콘을 눌러 채널 홈으로 이동하고 **챗봇 채팅**을 선택해 새로
    진입합니다.
11. 실제 앱에서 짧은 메시지를 보내고 `이 채널은 등록된 영어 선생님
    피드백만 받을 수 있어요`가 나오면, 방금 발신자를 원본 ID 출력 없이
    allowlist에 추가하고 webhook을 재시작합니다.

   ```bash
   python3 ~/.hermes/scripts/kakao_webhook.py \
     --approve-latest-sender \
     --env-file ~/.hermes/.env
   systemctl --user restart kakao-webhook.service
   ```

   승인 전에 보낸 메시지는 저장되지 않으므로 같은 메시지를 다시 보내
   `피드백을 저장했어요...` 응답을 확인합니다. 실제 선생님 계정도 처음
   한 번은 이 절차로 별도 승인해야 합니다.
12. 같은 날 두 번째 문장을 보내도 새 파일만 정확히 한 번 감지되는지
   `python3 ~/.hermes/scripts/english_intake.py`로 확인합니다.

실제 채팅에서 `위 운영시간 내에 채팅이 가능합니다` 또는 `지금은 ...
채팅 가능한 시간이 아닙니다`가 보이면 webhook 장애가 아니라 상담원용
1:1 채팅으로 진입한 것입니다. 1:1 채팅을 끈 뒤 `관리자가 채팅을 OFF한
상태입니다`가 나오는 것도 같은 기존 상담방입니다. 두 경우 모두 메시지는
영어 수집 서버로 전달되지 않으므로, 채널 홈의 **챗봇 채팅**에서 원문을
다시 보내야 합니다.

수집된 원문은 `~/english-lessons/YYYY-MM-DD/` 아래에 저장됩니다. 월–토
20:05 `english-intake`가 새 피드백을 분석합니다. 새 피드백이 없는 날에는
누적 SRS 카드에서 취약 패턴을 골라 짧은 코칭을 보냅니다. 일요일 20:15
`english-weekly-review`는 그 주의 전체 피드백과 누적 취약 카드를 전용
English bot으로 복습합니다. 21:10 `english-drill`은
당일 복습 문제를 전송합니다. Ellie 작업실의 **오늘의 영어 복습**은 부연설명을
한국어로 먼저 보여주고 기존 영어 설명을 **영어 참고**로 함께 보관합니다.
새 카드는 `english_srs.py add --wrong "..." --correct "..." --note "한국어 설명"`
으로 추가하며, 참고할 영어 설명은 `--note-en "English explanation"`으로 저장합니다.
정답 문장·카드 ID·복습 단계와 일정은 설명 언어와 별도로 유지됩니다.

개인화 코칭과 주간 복습에 사용되는 근거를 직접 확인할 수 있습니다.

```bash
python3 ~/.hermes/scripts/english_srs.py weaknesses --limit 5
python3 ~/.hermes/scripts/english_intake.py --week
```

Cloudflare Quick Tunnel 주소는 DGX 재부팅이나 터널 재시작 때 바뀔 수 있습니다.
로컬 URL 파일은 자동 갱신하지만 카카오 관리자센터의 URL은 자동 변경되지 않습니다.
현재 DGX는 고정 Tailscale Funnel의 HTTPS 포트 10000으로 전환했고, 외부 ingress의
실제 수신을 검증한 뒤 기존 임시 터널을 비활성화했습니다. 이 주소는 일반 재부팅 후에도
유지됩니다. Ellie의 **스킬 URL 복사**로 카카오 관리자센터에 한 번 저장·배포하세요.
지속 운영에는 [고정 주소 설정 가이드](docs/kakao-channel-setup.md#stable-public-address)의
Tailscale Funnel 또는 named Cloudflare Tunnel을 사용하세요. 이미 연결된 고정
HTTPS 주소는 다음처럼 검증·등록할 수 있습니다.

```bash
bash bootstrap/install_kakao_services.sh --public-origin https://your-fixed-hostname
```

고정 주소의 실제 수신을 확인한 후 임시 터널을 비활성화하고, 이후 설치·비밀 경로
회전도 같은 주소를 사용합니다. 카카오에는 갱신된 전체 스킬 URL을 한 번 저장·배포해야
하며, 그 뒤 일반 재부팅에는 URL 교체가 필요 없습니다.
Tailscale 주소는 내부 MagicDNS 접속과 구별해서 공개 DNS·외부 ingress·TLS까지
검증합니다. Funnel 최초 활성화 후 공개 DNS 반영에는 최대 10분이 걸릴 수 있습니다.

비밀 URL이 로그나 화면에 노출됐다면 즉시 회전하고 새 URL을 Open Builder에
다시 입력합니다.

```bash
bash bootstrap/install_kakao_services.sh --rotate-path
cat ~/.hermes/data/english/kakao-skill-url.txt
```

## Scheduled Telegram notifications (`cron/jobs.yaml`)

David's scheduled notifications use focused Telegram groups. The combined
Sunday review stays in the existing private chat:

| Destination | Suggested name | Jobs |
|---|---|---|
| Research | **Frontier Radar** | `papers-digest` |
| MLE interviews | **Interview Lab** | `interview-prep` |
| System design | **System Design Studio** | `system-design-coach` |
| Coding | **LeetCode Gym** | `coding-coach` |
| Podcast English | **🎧 Morning Echo** | `english-podcast-daily` |
| Main private chat | **Hermes HQ** | `weekly-review` |

Configure each topic group once:

1. Create the group, add `@David_agentic_ai_bot`, and send
   `/start@David_agentic_ai_bot` so Hermes observes it.
2. Find the group's negative numeric ID. `hermes send --list` shows established
   destinations; a newly observed `/start` can instead appear only in the
   gateway log:

   ```bash
   hermes send --list telegram
   tail -200 ~/.hermes/logs/gateway.log | rg 'telegram:group'
   ```

3. Add the IDs to the local secret environment file (never to this repository):

   ```dotenv
   # ~/.hermes/.env
   PAPERS_TELEGRAM_CHAT_ID=-1001234567890
   INTERVIEW_TELEGRAM_CHAT_ID=-1001234567891
   LEETCODE_TELEGRAM_CHAT_ID=-1001234567892
   SYSTEM_DESIGN_TELEGRAM_CHAT_ID=-1001234567893
   ENGLISH_PODCAST_TELEGRAM_CHAT_ID=-1001234567894
   ```

4. Verify each delivery, then register the declared jobs:

   ```bash
   hermes send --to telegram:-1001234567890 "[Hermes E2E] paper room test"
   hermes send --to telegram:-1001234567891 "[Hermes E2E] interview room test"
   hermes send --to telegram:-1001234567892 "[Hermes E2E] LeetCode room test"
   hermes send --to telegram:-1001234567893 "[Hermes E2E] system-design room test"
   hermes -p english send --to telegram:-1001234567894 "[Hermes E2E] Morning Echo test"
   python3 bootstrap/register_cron.py --dry-run
   python3 bootstrap/register_cron.py
   ```

The registrar refuses to create a topic-routed job without its numeric group ID,
so it cannot silently fall back to the private chat. The Sunday `weekly-review`
remains in the private chat because it combines paper highlights with interview,
coding, and system-design progress.

| Job | When (local) | What |
|---|---|---|
| `papers-digest` | 08:50 Tue/Fri | Dedicated paper group: three hottest LLM/LVM papers after 08:00 ingestion |
| `chatgpt-project-sync` | Daily 03:17 LA | Local script only: refresh Silicon Valley Career 2027 observations and RAG; no notification |
| `interview-prep` | 12:05 Mon/Wed/Fri | Interview group: one focused Staff/Senior MLE drill |
| `coding-coach` | 12:10 Tue/Thu/Sat | LeetCode group: 35-minute beginner problem with canonical links |
| `system-design-coach` | 12:15 Sunday | System-design group: one adaptive 45-minute interview |
| `english-podcast-daily` | 18:00 Mon–Fri | `🎧 Morning Echo` group on the existing English bot: latest watched podcast link + transcript-backed long-sentence practice |
| `english-podcast-weekend-review` | 18:00 Sat/Sun | Same podcast group: review this week’s weekday sources, no new video |
| `english-intake` | 20:05 Mon–Sat | Dedicated English bot: feedback analysis or weakness coaching |
| `english-drill` | 21:10 daily | Dedicated English bot: tonight's spaced-repetition drill |
| `english-weekly-review` | 20:15 Sunday | Dedicated English bot: tutor feedback + weak SRS cumulative review |
| `career-rewards-daily` | 21:25 daily | Main David bot: newly earned Career Cash and weekly progress |
| `weekly-review` | 18:05 Sunday | Main David bot: papers + MLE coverage + coding/design progress and next focus |

### Interview study coach

The existing `interview-prep` skill owns all interview coaching. The catalog at
[`coach_catalog.json`](skills/career/interview-prep/references/coach_catalog.json)
contains problem IDs, names, patterns, difficulty, and concrete study goals. It uses the
[NeetCode roadmap](https://neetcode.io/roadmap) and
[NeetCode 150](https://neetcode.io/practice/practice/neetcode150) as the backbone,
LeetCode for coding practice, plus a curated General/ML/LLM-Agent interview bank.
Daily pushes are
rendered locally from curated content; no scraping, login cookies, or live
lookups are required. Web lookup is only for maintaining links.

For company-specific questions, the coach reads
[`company-coding-strategy.md`](skills/career/interview-prep/references/company-coding-strategy.md).
It distinguishes official OpenAI/Anthropic guidance from anecdotal candidate
reports and treats company-family differences as planning heuristics. David's
current phase keeps three weekly LeetCode sessions; after roughly 8-12 weeks and
an evidence-based readiness check, the intended next phase replaces one of those
slots with a 60-minute Practical Coding exercise covering incremental features,
state, concurrency, retries, debugging, and tests. That future scheduled track is
not active until its catalog, progress tracking, and cron job are implemented.

Coding follows eight six-problem blocks: **HashMap (including the Two Sum
foundation) → Two Pointers → Sliding Window → Stack → Binary Search → Tree /
BFS / DFS → Heap → Graph**. At three sessions per week, each block normally lasts
two weeks. Every push shows progress such as `HashMap · 5/6`. The default path
stays in that block; you can explicitly skip a problem or choose another topic.

In **Jun → LeetCode Gym**, **잠시 스킵 · 다음 문제** records the current unfinished
problem and opens the next available one, continuing to the next topic when
needed. **스킵 기록 → 다시 풀기** reopens the original assignment with its hints
and solution exposure intact. Skips never count as completion or mastery; the
history remains after eventual completion and records repeat skips.
**주제별 문제 목록** shows all eight topics, problem names, difficulty and status.
Choose **이 주제 시작하기 / 이어가기** to switch, and **이전 주제 …로 돌아가기**
or another topic's button to resume saved work. Topic switches pause the old
assignment and its browser timer. Scheduled coaching respects the selected
problem/topic across dates. Completed problems still use **복습하기**.

The same state is available through the standalone CLI (get the current ID first):

```bash
python3 ~/.hermes/scripts/interview_progress.py coding-navigation
python3 ~/.hermes/scripts/interview_progress.py coding-skip \
  --assignment coding:2026-10-09 --expected-assignment coding:2026-10-09
python3 ~/.hermes/scripts/interview_progress.py coding-topic \
  --topic 'Two Pointers' --expected-assignment coding:2026-10-09:2
python3 ~/.hermes/scripts/interview_progress.py coding-resume \
  --assignment coding:2026-10-09 --expected-assignment coding:2026-10-09:3
```

`--expected-assignment ''` represents no current assignment. A stale tab/action
is rejected before changing progress. All navigation uses the existing coding
room, David profile/bot and `data/interview/coach_state.json`.

Start as a coding beginner. Each coding push includes a goal, both problem links,
a 35-minute budget, and “try 20 minutes without AI first.” Ask for a hint when
stuck: Hermes gives observation → algorithm/data structure → pseudocode, one
request at a time. A full solution requires another explicit request after
hint 3. The helper retains hint levels across fresh cron sessions.

Reply with your actual results. Coding tracks minutes, independent yes/no,
highest hint 0–3, solution viewed yes/no, confidence 1–5, and a lesson/mistake.
System design stores the original answer, interviewer follow-ups, all ten core
rubric scores, track-specific ML or Agent scores, strengths, weaknesses, mistakes,
and review topics. Missing feedback keeps the current interview pending. A
curriculum update preserves an obsolete open assignment as `superseded` history
rather than falsely completing it, while removing it from the active workbench.
The active block's unfinished problem is resumed across later cron dates instead
of creating duplicate assignments.

Solution viewed or confidence ≤2 schedules a review in 2 days; hint 2/3 or
confidence 3 in 7 days; independent work with confidence ≥4 in 21 days. Other
assisted attempts use 7 days. Scheduled Jun and **작업 이어가기 · 새 문제** always
keep the active uncompleted, unskipped new problem in the selected topic. Jun may suggest a due weak
review without assigning it; use **복습하기** to request a prior problem. A review
due date means eligibility when that explicit review path is used.

The design coach gives exactly one new 45-minute problem per ISO week and resumes
it until feedback is saved. Selection targets General 40%, ML 25%, and Agent 35%,
then favors different scenarios covering recurring weaknesses. It starts at
Standard senior level; two recent overall scores of at least 4.0 advance it, while
a score below 2.75 lowers it. `/review` is a separate 10-minute active-recall drill
and never counts as another weekly problem. Reference designs stay locked until
the original design and at least one follow-up have been evaluated.

Sunday's existing 18:05 review includes completed coding sessions, new/review
counts, weak patterns, average session minutes (including unsuccessful attempts),
hint usage, solutions viewed, design topics and weakest dimension, and next
week's focus, alongside papers and MLE coverage. Reports cover local Monday
through the requested date; unknown scores remain unknown.

### Career Cash rewards

Verified study activity earns motivational **Career Cash**: coding `$30`, system
design `$45`, an English SRS day `$10`, and a completed paper `$20`. Completing
any one is the daily mission; completing two different categories on the same day
adds a `$15` combo. The weekly mission is 3 coding sessions, 1 design session,
3 English practice days, and 1 read paper, with a `$150` clear bonus. Assignments,
agent messages, and reminders do not count until David records the actual result.

The office shows the wallet, streak, weekly checklist, next unlock progress, coin
animation, and a celebration from the relevant character followed by Hermes. Click
the Career Cash HUD to open a remaining-cash guide: it shows the current amount to
the next card, each verified earning activity and amount, weekly progress, bonuses,
and a direct link to the relevant workbench.
At cumulative `$250/$500/$1000/$2000`, fictional recruiter/offer cards unlock.
They are game achievements—not cash, hiring contact, or real offers. HQ owns this
cross-room workflow, so the existing David profile, private Telegram chat, and
Hermes HQ room are reused. The 21:25 digest stays silent without new rewards.

```bash
python3 ~/.hermes/scripts/reward_system.py status
python3 ~/.hermes/scripts/reward_system.py notify
```

Stage and register using the existing bootstrap:

```bash
python3 bootstrap/stage.py
python3 bootstrap/register_cron.py --dry-run
python3 bootstrap/register_cron.py
```

`stage.py` already copies the helper and the skill's catalog. It preserves runtime
progress in `~/.hermes/data/interview/coach_state.json`; `HERMES_HOME` also works.
The older MLE `progress.md` and `trends.json` remain separate. Cron uses the host's
local timezone, which should be America/Los_Angeles. The full registration command
syncs all declared jobs, including existing English jobs; for an interview-only
update, use the existing registrar with just these three jobs:

```bash
python3 - <<'PYCOACH'
from bootstrap.register_cron import DEFAULT_JOBS, load_jobs, register
names = {"coding-coach", "system-design-coach", "weekly-review"}
register([job for job in load_jobs(DEFAULT_JOBS) if job["name"] in names])
PYCOACH
```

Inspect a lesson and its assignment ID locally (these commands print text/JSON;
Telegram delivery belongs to cron):

```bash
python3 ~/.hermes/scripts/interview_progress.py plan coding
python3 ~/.hermes/scripts/interview_progress.py plan coding --format json
python3 ~/.hermes/scripts/interview_progress.py plan system_design
python3 ~/.hermes/scripts/interview_progress.py weekly
```

The Telegram and Design Studio chat support `/next`, `/answer`, `/followup`,
`/feedback`, `/solution`, `/history`, `/weakness`, `/progress`, and `/review`.
The same complete General-track session can be exercised from the CLI:

```bash
python3 ~/.hermes/scripts/interview_progress.py plan system_design --format json
python3 ~/.hermes/scripts/interview_progress.py design-answer \
  --assignment system_design:2026-09-20 \
  --answer "I would separate ingestion, preference filtering, queues, and channel workers."
python3 ~/.hermes/scripts/interview_progress.py design-followup \
  --assignment system_design:2026-09-20 \
  --question "What happens after an ambiguous provider timeout?" \
  --answer "Retry with a stable idempotency key and reconcile provider status."
python3 ~/.hermes/scripts/interview_progress.py design-feedback \
  --assignment system_design:2026-09-20 --duration 45 \
  --evaluation-json '{"scores":{"requirement_clarification":4,"high_level_architecture":4,"data_model":3,"api_design":3,"scalability":4,"reliability":4,"failure_handling":3,"trade_off_reasoning":4,"observability":3,"communication":4},"strongest_area":"high_level_architecture","weakest_area":"failure_handling","strengths":["Clear async boundaries"],"weaknesses":["Ambiguous delivery outcomes"],"mistakes":["Did not quantify retry load"],"top_3_improvements":["Quantify peak load","Trace timeout recovery","Define SLO alerts"],"recommended_review_topics":["idempotency"]}'
python3 ~/.hermes/scripts/interview_progress.py design-solution \
  --assignment system_design:2026-09-20
python3 ~/.hermes/scripts/interview_progress.py design-progress
```

The helper deliberately contains no model client. Hermes is the common provider
interface for both the local OpenAI-compatible vLLM endpoint and API models; the
skill owns interviewer prompts, while the helper owns deterministic selection,
validation, phase gates, and persistence. Invalid evaluation JSON is rejected,
and the skill repairs and retries it once.

Log the real assignment ID returned by `plan`, for example:

```bash
python3 ~/.hermes/scripts/interview_progress.py log-coding \
  --assignment coding:2026-09-08 --duration 35 --independent no \
  --hint-level 2 --solution-viewed no --confidence 3 \
  --lesson "Forgot to consider repeated values"
```

Global `--state PATH`, `--catalog PATH`, and `--date YYYY-MM-DD` options go before
the subcommand. Use a temporary state for previews/simulations. Logs must be
chronological. Identical completion retries are ignored; conflicting feedback
for the same assignment fails explicitly. Locked atomic writes preserve concurrent
updates, and corrupt state is retained for recovery instead of silently reset.

To import actual hints and learning from a cached ChatGPT project conversation,
prepare a **private** JSON file with `chat_id` and an `entries` array. Each entry
contains `slug`, the exact `accepted_at` from your saved LeetCode snapshot,
zero-based `message_indices`, and source-grounded `lesson` / `hint_notes`:

```bash
python3 ~/.hermes/scripts/interview_progress.py import-coding-history --file /private/path/learning.json
python3 ~/.hermes/scripts/interview_progress.py plan coding --next
```

The importer verifies project membership, cached messages and actual Accepted
evidence before writing `external_coding` in the locked coach state. Identical
retries do nothing; conflicting imports fail without partial changes. Known
curriculum problems advance and close outstanding new assignments, while
explicit reviews remain open. Extra practice stays visible without adding slots.
Missing time, confidence, numeric hint level or independence remain unknown and
do not affect graded review statistics. The existing LeetCode workbench shows
the next assignment first, imported hints/lessons with source messages and links,
and days since the last verified completion below Jun's greeting. This practice
gap uses Los Angeles dates and is not a scheduled deadline. The redundant
“대화 이어가기” companion button is removed; the existing conversation remains.
Jun's greeting also shows total LeetCode solves and the Easy / Medium / Hard
breakdown from the linked account snapshot, alongside the practice gap. These
counts move out of the lower account card and update whenever the workbench
refreshes; source-sync status and recent accepted problems remain below.
All workbenches use one compact heading such as **Jun과 함께하는 LeetCode Gym**,
with history/refresh controls and existing learning metrics in the same frame.
Below it, a wider conversation column uses the former introduction space and
fills the available height, with independent history scrolling and a persistent
composer. Current work remains alongside it; smaller screens stack conversation
and work vertically. Escape keeps workbench conversations open.
Graded attempts and imported ChatGPT learning appear in one chronological
**학습 완료 기록** list, with available metrics, actual hints/lessons and original
conversation links. Same-problem/same-date evidence merges into one entry.
Jun receives the current shared completion inventory on each reply, including
externally verified completions and pattern-specific learning. Missing submitted
source is not evidence that a problem was never solved.

Each workbench has **계정·연결 설정**. In Jun it sits at the bottom, below
solution reviews and learning history; the other rooms show it above their
main cards:

| Workbench | Connection action |
| --- | --- |
| Jun | **LeetCode 다시 연결** and **ChatGPT 다시 연결** |
| Rina | **Google · YouTube 다시 연결** for the existing watched-history account |
| Ellie | **챗봇 관리자센터 열기**, channel management, and **스킬 URL 복사** |
| Hermes HQ | The same ChatGPT reconnect button and saved profile used by Jun |

Click reconnect, then **로그인 창 열기** when ready. Log in directly through
the dashboard's existing private address without SSH forwarding or a monitor.
ChatGPT reconnection closes its window after confirmed login while preserving
the existing browser profile; it does not request an export. YouTube verifies
that the saved session can collect history again. Repeated clicks reuse an active
window. Only bounded transient units are started; bots, profiles and schedules
stay with their existing owners. Login windows use separate displays and ports.
The connection cards show last-known verification, not a guarantee of permanent
access. A source refresh error is distinguished from an authentication error.

For Ellie, the Kakao manager opens on your own PC browser. Copy the private skill
URL with **스킬 URL 복사**, paste it into **English Feedback Intake → URL** in
Open Builder, select that skill on the fallback block, choose **스킬데이터로
사용**, connect the operating channel, and deploy. The card reports local
collector/tunnel readiness; confirm channel deployment in Kakao's manager.
The secret URL is fetched only by the explicit copy action and never appears in
normal connection status, browser storage or the workspace archive.

Jun's workbench keeps its web conversation and **학습 완료 기록**, while removing
the additional Dashboard ↔ Telegram composer, workbench notes and recent-session
cards. **풀이 기록** lists completed problems in newest-first order. Click a
problem to expand Jun's prepared approach, answer, complexity, review hints and
edge cases, with the actual Accepted code and recorded learning alongside it.
Each expanded review also includes **영어 면접 스크립트 · 그대로 말하기**:
ready-to-say first-person English for confirming the task, explaining the approach,
walking through a concrete example, justifying correctness, and explaining time
and space costs. Read sections 1–5 aloud in order and memorize them. Section 6
is a spoken response for follow-up questions about improvements or tradeoffs;
**외워 쓸 표현** pairs expressions from the script with Korean meanings.
Scripts describe your actual implementation, including allocations and library
calls; proposed optimizations are identified as follow-ups.
Historical hints retain their source; generated review hints are labeled
separately. A solution review requires the actual Accepted code: notes never
substitute for the implementation. Problems without downloaded code stay pending,
including any formerly cached notes-only reviews. Recorded learning remains in
**학습 완료 기록** and supplements code-backed reviews.

`leetcode_review.py` caches reviews privately in
`~/.hermes/data/interview/leetcode_reviews.json`, using the configured loopback
model through its background admission queue. Changed code, notes or account
invalidate the relevant summary. The English script schema also invalidates older
reviews, so existing solved problems are rebuilt with scripts by the same
`prepare` command. Clicking a review reads the cache. The existing
06:35 `leetcode-history-sync` cron runs `leetcode_refresh.sh` without an outer
agent or Telegram delivery; workbench background refresh also prepares up to
three missing reviews per run. No new profile, room, bot or schedule is needed.
Use the existing workbench refresh button after background preparation, or run:

```bash
python3 ~/.hermes/scripts/leetcode_review.py prepare
python3 ~/.hermes/scripts/leetcode_review.py list
```

Rina's workbench displays the saved caption sentences directly: long-sentence
practice and up to four additional short sentence/expression prompts, with
source timestamps and listening links. Before today's source is prepared, the
latest saved practice remains visible under **최신 저장 문장 연습** with its actual
date. It also displays the sentences in weekend review sources. The dashboard
reads existing caption records; the 18:00 schedule and source selection remain
in the existing podcast workflow.

### LeetCode account history (optional, read-only)

The Coding Coach can use your solved totals, recent accepted submissions, and
the latest actual Accepted source for each recent problem as supplementary
context. This lets it answer questions such as “How did I solve Anagram?” from
your submitted code rather than a generic solution. It never treats that
history as graded coach feedback. An explicit learning import can record a
verified external completion as described above. It never submits code, edits
your LeetCode profile, or stores a password.
In the LeetCode workbench chat, the referenced problem (including a follow-up
that refers to the immediately preceding problem) automatically provides only
that matching local submission to the coach; the reply and its Telegram mirror
therefore explain the submitted implementation rather than a guessed template.
Opening **요약 보기** shows the exact LeetCode Accepted submission immediately
under **정답과 풀이**, including when the prose summary is still being prepared.
The source is displayed in a labeled code block with monospace text, preserved
indentation/line breaks, horizontal scrolling and local Python syntax colors.
Jun's prose explanation follows the source. Code repeated or rewritten in an
older model summary is omitted so the displayed code is always the fetched
submission. HTML-like source text stays escaped and cannot become page markup.
After a dashboard update, reload the browser tab once to pick up the new
renderer. The dashboard's **새로고침** and workbench's **다시 불러오기** buttons
also reload the full page, preserving the current room; automatic polling
continues to refresh data without reloading the page.

The token is entered through a hidden prompt and is stored only at
`~/.hermes/data/interview/leetcode_session.json` with `0600` permissions; the
separate owner-only snapshot (including submitted source code) is
`~/.hermes/data/interview/leetcode_history.json`.

For a DGX without a monitor, open **Jun → 풀이 기록 → LeetCode 로그인 창
준비하기** in your private Observatory dashboard. After a few seconds, follow
**LeetCode 로그인 창 열기** from Chrome/Chromium on Windows or Mac. The temporary
Chromium runs on DGX and its screen/input use the dashboard's existing address;
no HDMI connection or extra SSH port forwarding is needed. Complete LeetCode
login, Cloudflare verification and any MFA yourself. The browser profile is
isolated from other workflows and deleted afterward.

Google sign-in may reject browsers launched by automation frameworks. The
manual login now opens Chromium as a normal native process; users enter all
credentials and perform all login clicks themselves. The helper attaches only
on loopback to read the issued LeetCode cookies and verifies the linked account.
It does not alter the user agent or browser automation properties. This changes
the launch mode but does not guarantee that Google will accept every account.

If Google still rejects the remote window, expand **Google 로그인 거부 시 · PC
브라우저 세션 연결** in Jun. Sign in to LeetCode using your normal Windows/Mac
Chrome. On the signed-in LeetCode page, open DevTools (F12 or Option–Command–I)
→ Application → Storage → Cookies → `https://leetcode.com`, then copy the Value
of `LEETCODE_SESSION`. Paste that value into Jun's masked field and click
**세션 연결하고 풀이 갱신**. The field clears on submission and is not saved in
browser storage. Only this LeetCode cookie is submitted; no Google credentials
are imported. The backend stops the unused remote login, passes the value to the
existing verifier through stdin, saves it only for the linked account, and starts
the existing code/review refresh in a bounded background unit. Rejected cookies
leave the saved credential intact. No SSH command or HDMI is needed.

The dashboard starts a bounded transient user systemd unit so the window survives
HTTP request completion, SSH disconnection and agent turns. Repeated requests
reuse an active window. The login window expires after 15 minutes. Only a
session verified against the linked handle is saved; the desktop then closes
and actual Accepted-code sync and review preparation run automatically. Jun
shows readiness and sync status. The existing daily source sync stays at 06:35.
No new room, bot, profile or persistent desktop service is added.

To start the same window from a DGX terminal:

```bash
python3 ~/.hermes/scripts/leetcode_browser_login.py --start
```

It uses the linked LeetCode handle; add `--username HANDLE` for a first
connection. Open the resulting link in Jun, or use the dashboard-relative URL
`/leetcode-login/vnc.html?autoconnect=true&resize=scale&path=leetcode-login/websockify`.
The proxy accepts only an active login desktop on fixed loopback ports
18782/15903 and validates WebSocket origin. Credentials are entered directly
into LeetCode and never sent in dashboard API bodies. Diagnostic output stays
in the owner-only `~/.hermes/data/interview/leetcode-login.log`.

If using an attached DGX desktop, manual local login remains available:

```bash
python3 ~/.hermes/scripts/leetcode_sync.py login --headed --username <your-leetcode-handle>
bash ~/.hermes/scripts/leetcode_refresh.sh
```

Alternatively, sign in in a normal personal browser and use
`leetcode_sync.py connect --username HANDLE` to paste the issued
`LEETCODE_SESSION` cookie into its hidden terminal prompt. The plain `login`
command remains headless; LeetCode currently blocks that route with Cloudflare.
Session lifetime is controlled by LeetCode. The previously linked cookie's
metadata specified 14 days from its September 14 refresh; it was past that
period when source access failed. This does not establish a service-wide
maximum or a supported permanent session.
Successful sync now retains nondeleted session/CSRF cookies reissued by LeetCode
after verifying they still authenticate the linked account. It follows server
rotation rather than extending signed cookie contents locally. Deleted or
anonymous sessions never replace the saved credential. This can preserve normal
server renewals; logout, revocation or a required fresh login still need user
interaction, and indefinite access is not guaranteed.
The background sync remains available in the session archive but is omitted from
Observatory recent-activity lists so maintenance does not bury study history.
Opening or reloading LeetCode Gym refreshes account counts and recent accepts
with `sync --stats-only` (at most once per minute). The account total includes
problems solved without reporting to the coach; coach completion records remain
separate. Submitted-source failures cannot prevent counts from updating. If the
account request fails, the room labels the saved snapshot as stale and keeps its
last sync time. Run `python3 ~/.hermes/scripts/leetcode_sync.py sync --stats-only`
for an immediate counts-only refresh.
The room also starts a background `sync --missing-only` source refresh (at most
once every five minutes). It downloads actual Accepted code for recent problems,
including solves never reported to the coach, reuses unchanged submissions, and
retains older downloaded problems. Both the web character chat and Telegram
workbench chat can explain matching downloaded code. The room lists problems
with prepared reviews, actual code and source-access status separately from
the account total. An expired session can still expose public counts while
blocking private code; reconnect using `login --headed` or `connect` above.
If public solves update while missing problems show **LeetCode 재연결 필요**,
the linked session no longer authenticates the account. Saved older code can
still be reviewed; public Accepted history alone does not grant private source
access. Relink a fresh session, then run `bash ~/.hermes/scripts/leetcode_refresh.sh`
and refresh the workbench to replace pending entries with actual-code reviews.
Manual incremental refresh: `python3 ~/.hermes/scripts/leetcode_sync.py sync --missing-only`.
The LeetCode Gym Observatory room shows only the safe snapshot; it never returns
the session cookie. To stop future account access while retaining the already
saved progress snapshot, run:

```bash
python3 ~/.hermes/scripts/leetcode_sync.py disconnect
```

### Dedicated English Telegram bot

Create a new bot with BotFather, then run the following once. The profile setup
stores that bot's token only in `~/.hermes/profiles/english/.env`; it never goes
in this repository or the main David profile.

```bash
bash bootstrap/install_english_bot.sh
hermes -p english gateway setup
# Choose Telegram, enter the new bot token, and message the bot once to pair it.
bash bootstrap/install_english_bot.sh
```

The first command stages the main and English profiles, removes the main profile's
former English skill, and tells you to configure the bot when its token is absent.
Re-running after setup installs the profile gateway and re-syncs the four English
cron jobs with `--profile english`. Papers, interview prep, and the weekly review
remain on the original bot.

The English profile's skill library is repository-owned: staging removes unmanaged
runtime-created skills, while background skill creation and curator maintenance are
disabled for this profile. Edit `profiles/english/` and stage again for durable
changes.

### Evening YouTube watch-history links

David selects videos himself in the YouTube app on weekdays. At **18:00
Monday–Friday, America/Los_Angeles**,
`english-podcast-daily` runs `youtube_history.py notify` and sends the **single most recently watched
podcast** video, including yesterday or older days. A video qualifies if its
channel is **English Goal Podcast** or **Daily English Podcast**, or its title
contains **Podcast** (case insensitive). These are OR conditions; the newest
match wins across all candidates without channel priority. An English title alone
is not enough. It
refreshes history each evening and sends the latest match even if unchanged. It uses the existing English
profile/bot and the dedicated `🎧 Morning Echo` group selected by the validated
`ENGLISH_PODCAST_TELEGRAM_CHAT_ID`. No new Hermes profile, bot, or service is added.
The same evening message adds **two long-sentence speaking exercises** from that
selected video's English captions. `english_podcast.py practice` validates the
fresh watch-history snapshot, downloads/caches exactly that video, and extracts
complete 20–45-word source sentences with timestamps. Caption retrieval prefers `en-orig`, requesting `en` only if no original English
track is available, avoiding a redundant subtitle request. It favors clause connectors
such as `even though`, `because`, `so that`, and `which`. The English agent adds
Korean meanings, two or three clause chunks, reusable sentence frames and one
personal speaking prompt per sentence. It also reads actual SRS weakness cards
and chooses one or two additional short source sentences (8–25 words) from the
same video for weak-pattern practice. If no known weakness fits the available
sentences, it says so rather than inventing personal feedback. The 20:05 tutor
coaching also uses these source records for additional practice; correction and
SRS review remain grounded in actual feedback cards. Quotes stay verbatim; generated examples
are labeled separately. Shadow each sentence three times, then say a personal
version without looking. Automatic captions are identified. If captions are
unavailable or no suitable complete sentences exist, the video link is still
sent with a short explanation, without invented or substituted source sentences.

The previous 09:15 recommendation and automatic 08:25 transcript prefetch are
replaced and remain disabled. The old `english_podcast.py prepare` new-video
assignment is retained for a later explicit opt-in, but current practice and
follow-ups use the selected weekday video or archived weekday material.

At **18:00 Saturday/Sunday**, `english-podcast-weekend-review` runs
`english_podcast.py review` in the same Python environment, profile, bot and
podcast group. It reads only the current week's Monday–Friday source archives
without refreshing history or downloading captions. Saturday emphasizes replay,
shadowing and personal adaptations; Sunday emphasizes retrieval/rewrite with
inline answers and a next-week focus. Repeated weekday selections are merged by
video. No usable records means `[SILENT]`. Both routines use Korean guidance and
keep generated prompts distinct from caption quotations.

The **DGX Spark server is accessed over SSH and has no permanent GUI**. YouTube's official
API does not expose watch history, so the server reads the signed-in history page
with headless Chromium. For account connection, use temporary headed Chromium on
the DGX over an SSH tunnel, or import a personal computer's session. UI changes
or an expired session can require reconnection.

For **direct DGX login**, install the optional desktop runtime from this checkout
once on the DGX (Ubuntu 24.04 arm64):

```bash
python3 bootstrap/install_youtube_history_desktop.py
```

This adds full Chromium, Xvfb, x11vnc, noVNC and websockify to the existing private
YouTube runtime without sudo or a permanent desktop service. Start a temporary
login window on the DGX:

```bash
systemd-run --user --unit=hermes-youtube-login --collect --property=RuntimeMaxSec=25min --property=MemoryMax=2G --property=CPUQuota=200% /home/david/.hermes/venvs/youtube-history/bin/python /home/david/.hermes/profiles/english/scripts/youtube_browser_login.py
```

In a **local Windows PowerShell** terminal, keep this SSH tunnel running:

```powershell
ssh -F /dev/null -N -T -o ExitOnForwardFailure=yes -L 127.0.0.1:18780:127.0.0.1:18780 david@10.0.0.50
```

Open `http://127.0.0.1:18780/vnc.html?autoconnect=true&resize=scale` in local Chrome.
Sign into the same YouTube account/channel as the phone app inside the displayed
DGX Chromium. Credentials are entered directly in the browser. The helper
detects verified YouTube login, saves only YouTube cookies on the server, closes
the temporary display and requires both `connect --saved-cookies` and a separate
`sync` to pass. No extension or local cookie export is needed. The window expires
after 20 minutes and all components bind loopback. To stop it early, run
`systemctl --user stop hermes-youtube-login.service` on the DGX. Safe progress is
stored in `data/youtube-history/login-status.json` and the existing podcast
Observatory room; cookie values and Google pages are excluded from that view.

The English installer provisions Playwright in the explicit server environment
`~/.hermes/venvs/youtube-history/`. For a manual or existing deployment, run
`bash bootstrap/install_youtube_history.sh` on the DGX once. SSH imports and the
18:00 cron both use this environment's absolute Python path; interactive Conda
and SSH/system `python3` can have different installed packages. The installer also
downloads the [matching Playwright headless shell](https://playwright.dev/python/docs/browsers#chromium-headless-shell)
into the environment’s `browsers/` directory and installs yt-dlp for the evening
caption extraction. This fixed cache works even when
Hermes changes HOME. Snap Chromium on this host returned `ERR_ACCESS_DENIED` for
YouTube; the shared Hermes CDP browser is retained for its separate workflows. The SSH command below
uses `ClearAllForwardings=yes` to bypass unrelated default forwarding (such as
an already occupied local port 8501) while importing cookies.

On the **MacBook**, open YouTube in Chrome and sign in with the **same Google
account and YouTube channel as the phone app**. Watch history must be enabled.
Then run these commands in a **local Mac terminal**, replacing the SSH target
with the same host/alias you normally use:

```bash
DGX_SSH='dgx'
scp "${DGX_SSH}:/home/david/.hermes/scripts/export_youtube_cookies.py" ~/export_youtube_cookies.py
python3 -m venv ~/.local/share/hermes-youtube-export
~/.local/share/hermes-youtube-export/bin/python -m pip install yt-dlp
~/.local/share/hermes-youtube-export/bin/python ~/export_youtube_cookies.py --browser chrome
ssh -T -o ClearAllForwardings=yes "$DGX_SSH" '/home/david/.hermes/venvs/youtube-history/bin/python /home/david/.hermes/profiles/english/scripts/youtube_history.py connect --cookies-stdin' < ~/youtube-cookies.txt
```

If macOS asks for Chrome Keychain access, approve it for this local export. Use
`--browser firefox`, `edge`, or `brave` if that is where the matching account is
signed in; `--profile` selects a non-default browser profile. Extraction depends
on browser access and cookie decryption support. The helper exports **only live
YouTube-domain cookies**, converting native Chromium expiration timestamps to
Unix seconds before checking validity and saving atomically with permissions `0600`; it never saves
other sites' sessions or prints cookie values. Send the file via SSH stdin, never
through chat or Telegram. Export/import again if the login expires. Once import
succeeds, the local export file can be deleted.

On **Windows with Chrome**, export a separate session using
[Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc),
listed in the [yt-dlp cookie documentation](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp).
Enable the extension's **Allow in Incognito** setting. In a new incognito window,
sign into the same YouTube account/channel, then navigate in that same tab to
`https://www.youtube.com/robots.txt`. Export only `youtube.com` cookies in
**Netscape** format to `Downloads\youtube-cookies.txt`, then close that incognito
window. The Python browser exporter above reads regular browser profiles; it
does not read incognito sessions. YouTube can rotate credentials in open regular
tabs, so a future cookie expiration does not guarantee the exported session will
stay authenticated; see the
[yt-dlp session export guidance](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies).

Run these commands in **local Windows PowerShell**, outside the DGX SSH shell:

```powershell
scp "$HOME\Downloads\youtube-cookies.txt" dgx:/home/david/.hermes/data/youtube-history/import-cookies.txt
ssh -T -o ClearAllForwardings=yes dgx '/home/david/.hermes/venvs/youtube-history/bin/python /home/david/.hermes/profiles/english/scripts/youtube_history.py connect --cookies-file /home/david/.hermes/data/youtube-history/import-cookies.txt'
```

The upload destination is inside the existing private server directory. After
successful import, remove that temporary server file and the local export. Test
`sync` once more to verify login survives a fresh browser process; a successful
first import alone does not establish continued authentication.

The server saves the filtered session owner-only at
`~/.hermes/data/youtube-history/session.json` before attempting network access.
It records confirmed login separately in `authentication.json`, retaining refreshed
cookies even if history rendering fails. `connection.json` marks a completed
history collection; file presence alone is not proof of login. Authenticated
sessions retry collection automatically without another laptop export. If a network or rendering failure
occurs, retry from the server using the saved session:

```bash
~/.hermes/venvs/youtube-history/bin/python ~/.hermes/profiles/english/scripts/youtube_history.py connect --saved-cookies
```

Login also stays in the owner-only browser directory
`~/.hermes/data/youtube-history/browser/`; each collection starts a short-lived
headless browser process under a lock. Every fresh browser launch restores the
saved session, including when stale cookie names remain in Chromium; refreshed cookies are saved after
a successful read. Errors report a fixed failure stage and safe network code,
never a raw browser exception, cookie value, or page dump. The server also
accepts earlier exports containing native Chromium expiration timestamps, so
those files can be retried without a new export solely for format conversion.
The reader supports modern YouTube lockup title/channel classes as well as older
video rows. A collection-limit/layout error does not request another cookie
export; status and Observatory distinguish confirmed login from pending collection.
If browser application succeeds but YouTube reports signed out, confirm the
personal computer's matching browser profile is signed in and export a fresh session;
cookie presence or a future expiration alone does not establish authentication. Videos outside both channel and title criteria, plus Shorts, are
excluded; a history entry does not prove a completed listen or viewing duration.

```bash
~/.hermes/venvs/youtube-history/bin/python ~/.hermes/profiles/english/scripts/youtube_history.py status
~/.hermes/venvs/youtube-history/bin/python ~/.hermes/profiles/english/scripts/youtube_history.py sync
~/.hermes/venvs/youtube-history/bin/python ~/.hermes/profiles/english/scripts/youtube_history.py notify
/home/david/.hermes/venvs/youtube-history/bin/python /home/david/.hermes/profiles/english/scripts/english_podcast.py practice
/home/david/.hermes/venvs/youtube-history/bin/python /home/david/.hermes/profiles/english/scripts/english_podcast.py review
hermes -p english cron list
```

To override the channel list, repeat `--channel`, for example
`youtube_history.py --channel "Daily English Podcast" --channel "Another Channel" notify`.
Titles containing `Podcast` still qualify alongside the selected channels.

Private snapshots live in `~/.hermes/data/youtube-history/`, separately from the
tutor SRS deck and transcript assignments. Before verified login, `notify`
returns `[SILENT]` without launching Chromium or sending daily setup errors.
No matching episode in the collected history also produces `[SILENT]`; a login, layout, or network error preserves the prior snapshot and
reports the connection error without sending stale links. Observatory's existing
podcast room displays safe session/connection status, collection date, last
successful collection, and the latest watched link. The date records when history
was refreshed, not when the video was watched; older snapshots are labeled as
awaiting refresh. Search is limited to 20 scrolls per run and reports an error if
that limit is reached before finding a match. Caption manifests, transcripts and
practice source records live separately under `~/.hermes/data/english-podcast/watched/`;
`practice.json` is current source state and `practice/YYYY-MM-DD.json` archives
the extracted source sentences; `review.json` describes the current weekend
review. It never changes legacy daily assignments or tutor SRS. No live account verification is claimed
until `connect`/`sync` succeeds.

### Automatic cron recovery

Install the watchdog once after installing the Hermes gateway:

```bash
bash bootstrap/install_cron_watchdog.sh
```

`hermes-cron-watchdog.timer` checks the David and installed English profile
schedulers every five minutes on a minute offset separate from scheduled study
jobs. The David watchdog also makes a credential-free
loopback probe of the Observatory chat API; a TCP listener that has stopped
serving HTTP requests is restarted as well. A due job gets 15 minutes to start;
only a next-run timestamp beyond that grace or a cron tick lock held longer than
20 minutes triggers a restart of the matching gateway. The installed
gateway drop-ins cap shutdown at 45 seconds, so a permanently blocked worker
cannot prevent recovery indefinitely. A job whose latest run is marked failed is
queued once again without restarting a healthy gateway. The profile-local retry
state limits retries across consecutive failures, including a failed retry with
a new execution timestamp. An observed successful run resets that job's retry
allowance; persistent job errors remain visible without creating restart loops.
Automatic recovery reports the observed restart reason, action, verified result
and practical remedies to the owning profile's Telegram home. `--notify-restarts`
enables these messages for manual `cron_health.py --restart` checks as well.
Systemd lifecycle hooks also report David/English restarts after recorded exits,
including OOM, timeout, abnormal exit or clean stop followed by startup. Clean
stops cannot identify the requester; the message says so. No alert is sent on a
first start without an exit record. Notifications do not require a working
gateway and never restart it on delivery failure. The latest report and delivery
status are saved in `cron/last-restart-notice.json`; failed delivery is retried
on later watchdog checks. Watchdog and lifecycle hooks deduplicate one restart.
Unchanged `register_cron.py` jobs are kept in place to preserve their pending run
time and this runtime state. An English profile or Telegram gateway that has not
yet been installed is skipped cleanly.

The same timer runs `connection_health.py --notify` before gateway recovery.
It reports ChatGPT chat sync/login, YouTube login/history, LeetCode private-code
access, Kakao public intake and failed external-data scheduled jobs to David's
existing **Hermes Telegram home**, including a recovery notice after positive
evidence. Existing failures are reported on the first check; repeated failures
within the same incident are silent. Failed deliveries retry on later ticks.
ChatGPT's source-sync status and its scheduled-job outcome form one incident.
Their evidence timestamps decide the current state, so an older failed cron
result cannot reopen an incident after a newer verified sync. Existing duplicate
incident keys are merged while retaining queued delivery and historical events.
Unconfigured or unverified services do not produce a false recovery. Kakao
public-network failures require two consecutive checks (about 5–10 minutes);
other recorded failures normally notify within five minutes.
The Kakao probe sends an empty body and verifies public ingress without saving
feedback; it cannot verify Open Builder deployment or real message delivery.

**Hermes HQ → 외부 연결 상태와 알림** displays current observations, ten recent
incident/recovery events and pending delivery. Safe monitor state lives in
`data/observatory/connection-health.json`; notices omit credentials, private
webhook URLs, chat contents and raw source errors. YouTube sync persists fixed
failure/success evidence in `data/youtube-history/sync-status.json`. This is an
operational helper in the existing HQ room, with no new profile, bot or schedule.
Run `python3 scripts/connection_health.py` for a read-only check; add `--notify`
to deliver detected incidents through the configured Hermes home. Reinstall
`bootstrap/install_cron_watchdog.sh` after staging updates to enable the monitor.

Inspect it without changing state:

```bash
systemctl --user status hermes-cron-watchdog.timer
systemctl --user list-timers hermes-cron-watchdog.timer --all
python3 scripts/cron_health.py
python3 scripts/cron_health.py --hermes-home ~/.hermes/profiles/english \
  --gateway-service hermes-gateway-english.service
```

Check the scheduler and run a Telegram E2E without exposing its token:

```bash
systemctl --user is-active \
  hermes-vllm.service hermes-gateway.service hermes-gateway-english.service
python3 scripts/cron_health.py
hermes send --to telegram "[Hermes E2E] Telegram 연결 테스트"
hermes -p english send --to telegram "[English E2E] Telegram 연결 테스트"
hermes cron list
hermes -p english cron list
hermes cron run <JOB_ID_FROM_LIST>
hermes cron tick
hermes -p english cron run <ENGLISH_JOB_ID_FROM_LIST>
```

`hermes cron list` shows the David bot jobs; `hermes -p english cron list` shows
the isolated tutor-English jobs plus the weekday 18:00 watched-link practice and weekend review jobs. Run each
profile's E2E message only after its Telegram bot has completed pairing.

The gateway only starts after `/v1/models` contains
`Qwen3.8-Flash-Next-UD-IQ4_XS`. Calendar is not part of the active agent runtime.

## Local model note
Hermes requires a model with **≥64K context**. The Qwen3.8 Flash-Next
`UD-IQ4_XS` checkpoint is served on `:8003` with two 64K slots (128K total),
so the main and English gateways can overlap without shrinking either context.
The transformer/expert layers remain GPU-offloaded; the roughly 27GiB n-gram
embedding stays in CPU RAM. This Spark's CPU and GPU share one 128GB memory pool,
so `nvidia-smi` process usage is not an independent VRAM-free figure. The launcher
keeps an 8GiB fit target and avoids SSD-backed lazy n-gram reads for lower
prompt/decode latency. Override `HERMES_MODEL_CONTEXT` and
`HERMES_MODEL_PARALLEL` together if changing the per-slot context; keep their
ratio at least 65536. Its three GGUF shards total about 93.7GB. Paper metadata
ingestion itself is zero-LLM and does not
require a second model server. The model stays outside this configuration repo
under `/home/david/workspace/models`:

```bash
hf download unsloth/Qwen3.8-Flash-Next-GGUF \
  --include 'UD-IQ4_XS/*' --include 'mmproj-F16.gguf' \
  --local-dir /home/david/workspace/models/unsloth/Qwen3.8-Flash-Next-GGUF
```

## Browser note

Hermes's own browser tool uses pinned `agent-browser` and a Chromium service
bound only to `127.0.0.1:19222`. The opt-in LeetCode helper additionally uses
Playwright only to attach to that same local CDP browser for an interactive,
headless password login; it neither launches a cloud browser nor saves a
password. The explicit CDP service avoids a Snap Chromium auto-launch hang
observed on the DGX Spark's ARM64 environment.

### ChatGPT conversation archive (optional)

Hermes can search exported ChatGPT conversations as reference material in the
existing **Hermes HQ** room. Signing in to Codex or using Sign in with ChatGPT
does not grant access to earlier ChatGPT chats. This helper operates the visible
ChatGPT website to index visible chats or import an actual export; it has no private history API,
new bot/profile, automatic polling, or recurring delivery.

The existing temporary desktop runtime is reused, with a separate owner-only
ChatGPT browser profile. If not already installed on the DGX:

```bash
bash bootstrap/install_youtube_history.sh
python3 bootstrap/install_youtube_history_desktop.py
python3 bootstrap/stage.py
```

On the **DGX**, start a bounded browser session (30 minutes by default):

```bash
~/.hermes/venvs/youtube-history/bin/python ~/.hermes/scripts/chatgpt_archive.py login
```

On the **MacBook**, open a **new local terminal outside the DGX SSH session**.
Use the DGX's direct address and leave this command running:

```bash
ssh -F /dev/null -N -o ExitOnForwardFailure=yes -L 127.0.0.1:18781:127.0.0.1:18781 david@10.0.0.50
```

`-F /dev/null` bypasses alias forwarding defaults, including port 8501 which may
already belong to an existing `ssh dgx` session. Replace the direct address if
connecting through a different network; add `-i /path/to/key` if the alias normally
selects a nondefault identity. Do not combine explicit `-L` with
`ClearAllForwardings=yes`: OpenSSH removes command-line forwards too, leaving an
apparently connected SSH session without the browser tunnel.

Open `http://127.0.0.1:18781/vnc.html?autoconnect=true&resize=scale` in the MacBook
browser and sign in directly, completing any additional authentication. The
SSH tunnel is needed only while viewing this remote screen; `Ctrl+C` stops the
tunnel without deleting the DGX browser profile or collected data. The DGX login
browser itself closes at its configured timeout; reopen it for subsequent live
reads. A physical DGX monitor is optional, and Google account sign-in is not required.

For ordinary history retrieval, keep that browser open and run these commands
on the DGX:

```bash
~/.hermes/venvs/youtube-history/bin/python ~/.hermes/scripts/chatgpt_archive.py sync-sidebar
python3 ~/.hermes/scripts/chatgpt_archive.py search "interview"
~/.hermes/venvs/youtube-history/bin/python ~/.hermes/scripts/chatgpt_archive.py read-browser <conversation-id>
python3 ~/.hermes/scripts/chatgpt_archive.py show <conversation-id>
```

The sidebar index contains observed titles and links. Selected chats cache
currently rendered user/assistant text. Both are explicitly partial observations:
scrolling can miss older chats, and long conversations can have unrendered turns.
They are not a complete account export. Existing observations survive later
sidebar scans, and a failed read preserves the previous cached conversation.
Search uses this index/cache when no export has been imported; an imported
export remains the preferred search source. The browser reader supports current
and legacy message layouts and verifies the selected conversation before saving.

To request an official complete export instead, start `login --request-export`.
The helper attempts Settings → Data controls → Export → Confirm export once and
requires a success notice before reporting a confirmed request. If account UI
controls change, use the visible browser to finish; an ambiguous result is never
automatically retried. Some account types or automated-browser restrictions may
prevent exporting. See [OpenAI's export instructions](https://help.openai.com/en/articles/7260999-exporting-your-chatgpt-history-and-data).

Export confirmation can require additional account verification even after
successful sign-in. The helper reports `awaiting_verification` when ChatGPT
redirects to its authentication page; this is not a submitted export. Approve
the request in an already signed-in ChatGPT app or use **Try with email** in the
remote browser and enter the emailed code there. If mobile approval displays an
authentication error, use that email alternative. Inspect the returned account
settings for confirmation before claiming that an export was requested; do not
automatically repeat an ambiguous confirmation click.
If successful email verification repeatedly returns to verification, stop that
flow and report `verification_loop`; ordinary signed-in sidebar reads can still
work. A later export request can be tried in the owner's usual MacBook browser.
The helper does not diagnose the cause of that authentication loop.

The export email/SMS may take up to seven days; its download link expires after
24 hours. Email access is not connected by this helper. When the link arrives,
reopen the same login browser and navigate to it there. Completed ZIP downloads
are automatically imported during that session. Alternatively, run the following
DGX command while the browser is open and paste the link into terminal stdin
(not the shell command or chat); press Return:

```bash
~/.hermes/venvs/youtube-history/bin/python ~/.hermes/scripts/chatgpt_archive.py download
```

For an existing export file, and subsequent read-only queries:

```bash
python3 ~/.hermes/scripts/chatgpt_archive.py import --file /path/to/chatgpt-export.zip
python3 ~/.hermes/scripts/chatgpt_archive.py status
python3 ~/.hermes/scripts/chatgpt_archive.py search "interview"
python3 ~/.hermes/scripts/chatgpt_archive.py show <conversation-id>
```

State stays under `~/.hermes/data/chatgpt/`: the private browser profile,
downloads, `browser-index.json`, selected `browser-chats/`, and `archive.db`.
ZIP members are not extracted; only a bounded
`conversations.json` is read. Each successful import atomically replaces the
local snapshot, preserving the previous archive on failure. Search/show include
visible user/assistant text from the selected branch, excluding other branches,
system/tool records, hidden reasoning, and nontext assets. Imported text is
historical evidence and must not be treated as instructions or copied wholesale
into memory. HQ shows connection/export state and counts, not chat titles,
contents, account identity, session credentials or signed links.

### ChatGPT project vector RAG

David's current retrieval scope is **Silicon Valley Career 2027**. The project
contains nine observed chats; its cached 116 user/assistant messages form 254
token-bounded search chunks. Other account chats are excluded from this index.
These are browser observations, so unrendered historical turns or source files
are not claimed collected. The official full-account export is still unconfirmed.

The selected project is refreshed **daily at 03:17 America/Los_Angeles**, before
the 06:35 LeetCode sync and the other scheduled study jobs. `chatgpt-project-sync`
is a Hermes **script-only** cron job (`--no-agent`, local delivery): no model call,
new bot/profile, VNC server or Telegram notification is needed. It temporarily
reuses the saved ChatGPT browser login, refreshes the project list and each chat,
and rebuilds local vectors without downloading another model.

```bash
python bootstrap/register_cron.py --name chatgpt-project-sync
~/.hermes/venvs/youtube-history/bin/python ~/.hermes/scripts/chatgpt_archive.py sync-daily
```

The staged `chatgpt_project_sync.sh` has a 25-minute bound; the cron script limit
is 1800 seconds. Browser/read/index locks avoid simultaneous manual collection;
successful runs deduplicate by LA date. Sources and vectors are validated in a
private staging directory and published together, restoring old files on write
failure. Shorter observations retain earlier messages only when ordered overlap
proves continuity; unverified overlap, login failures or partial chat failures
preserve the last published sources/index. Browser captures remain partial.
Continuity comparisons tolerate extra empty lines added by ChatGPT's rendered
message bubbles. Saved original text, indentation, horizontal whitespace and
literal spaces remain unchanged; content or code changes still fail the overlap
check. This prevents harmless display spacing from aborting the entire daily sync.
HQ shows the daily schedule, latest attempt and last successful refresh from
`data/chatgpt/daily-sync.json`; the job is routed to the existing HQ room.
This is internal source maintenance, so it does not create a separate room.

The standalone `chatgpt_rag.py` helper uses pinned
[`intfloat/multilingual-e5-small`](https://huggingface.co/intfloat/multilingual-e5-small)
weights on CPU, attention-mask mean pooling and normalized 384-dimensional
vectors. An atomic owner-only SQLite snapshot stores text, source offsets and
vectors; cosine retrieval and literal-term ranks are fused locally. This small
project does not require a separate vector server. Conversation text is never
sent to an embedding API, and normal searches use cached model files only.
See the [semantic search documentation](https://sbert.net/examples/sentence_transformer/applications/semantic-search/README.html)
for the underlying retrieval method.

Install the optional CPU runtime in a separate environment (the DGX already has
CPU PyTorch available through its host Python):

```bash
python3 -m venv --system-site-packages ~/.hermes/venvs/chatgpt-rag
~/.hermes/venvs/chatgpt-rag/bin/python -m pip install -r bootstrap/requirements-chatgpt-rag.txt
python3 bootstrap/stage.py
```

While the bounded login browser is open, collect or refresh only this project:

```bash
~/.hermes/venvs/youtube-history/bin/python ~/.hermes/scripts/chatgpt_archive.py sync-project "Silicon Valley Career 2027"
~/.hermes/venvs/youtube-history/bin/python ~/.hermes/scripts/chatgpt_archive.py read-project
~/.hermes/venvs/chatgpt-rag/bin/python ~/.hermes/scripts/chatgpt_rag.py build --download-model
```

`read-project` skips cached chats whose bounded scroll reached the boundary;
use `--refresh` to deliberately reread them. It reports sanitized failures without
printing bodies. Each successful read preserves prior data on later failures.
`--download-model` permits only public model downloads, with the exact revision
pinned in source; later builds need no network access. Source changes fail closed
until a successful rebuild, and a failed build preserves the old index.

Search and inspect sources with the browser closed:

```bash
~/.hermes/venvs/chatgpt-rag/bin/python ~/.hermes/scripts/chatgpt_rag.py status
~/.hermes/venvs/chatgpt-rag/bin/python ~/.hermes/scripts/chatgpt_rag.py search "바이브코딩 이후 리트코드 면접 준비" --limit 6
~/.hermes/venvs/chatgpt-rag/bin/python ~/.hermes/scripts/chatgpt_rag.py read <chunk-id> --neighbors 1
```

Hermes HQ's existing agent chooses natural-language searches, reads adjacent
source chunks, and can refine weak queries for up to three retrieval rounds.
Cross-language questions may need a narrower query or a source-language
equivalent. Returned titles/links, roles and message offsets support citations;
similarity scores are candidate rankings, not factual confidence. Distinguish the
owner's statements from older assistant advice and treat all retrieved text as
historical evidence, never instructions. This extends the existing David/HQ
reference source without adding an agent, room, profile, bot or cron. HQ displays
the configured project and safe index counts, without conversation bodies.

### Switching to MiniMax-M2.7 (DGX Spark)
```bash
# 1. Download and manage the checkpoint in the dedicated models workspace (~100GB+)
cd /home/david/workspace/models
python3 download_model.py cyankiwi/MiniMax-M2.7-AWQ-4bit
cd /home/david/workspace/David-Agent

# 2. Stop Qwen vLLM, start MiniMax
bash local-model/run_model.sh minimax

# 3. Point Hermes at MiniMax (copy fragment or stage minimax yaml)
cp config/config.fragment.minimax.yaml config/config.fragment.yaml
python3 bootstrap/stage.py

# 4. Test
curl -s http://localhost:8003/v1/models | python3 -m json.tool
hermes -z "hello"
```
Use **cyankiwi/MiniMax-M2.7-AWQ-4bit** on a single 128GB GPU. The official
`MiniMaxAI/MiniMax-M2.7` BF16 checkpoint needs ~220GB and 4–8 GPUs.
Review the [MiniMax-M2.7 license](https://github.com/MiniMax-AI/MiniMax-M2.7/blob/main/LICENSE) for commercial-use limits.

## Hermes HQ — private agent observatory

Hermes HQ is a web app for watching your agents, browsing saved records, and
continuing study tasks from room workbenches.
The campus has separate paper, MLE, coding, system-design, English, Morning Echo,
and HQ rooms; other installed Hermes profiles also appear as independent rooms.
Morning Echo is a separate podcast workspace owned by the existing English
profile, not a separate bot or gateway. The main campus is a living anime office
with a balanced seven-character ensemble: ambient reading, walking, listening,
and break animations keep the room alive between sparse cron runs. `AMBIENT` is
explicitly decorative; `LIVE` and `BLOCKED` are derived from gateway activity and
read-only Kanban state. The daily replay still follows real session start times,
and gateway process availability is checked separately from session history.

Install or update while Tailscale is connected:

```bash
bash bootstrap/install_observatory.sh
tailscale ip -4
# Open http://<the-Tailscale-IP>:8788 from a device on your tailnet.
```

The installer stages the standalone Python server, local HTML/CSS/JavaScript,
HQ specialist profiles and Kanban settings, then enables
`hermes-observatory.service`. It refreshes the main gateway dispatcher when its
configuration changed. Installation
does not make a model request and needs no npm build, external CDN, or new Python
dependency. It listens only on loopback
and the machine's Tailscale IPv4, never `0.0.0.0`. Tailscale access policy governs
remote access; there is no additional app login. HTTP is carried inside the
encrypted Tailscale tunnel. For browser HTTPS, optionally add a separate Serve
listener (this can require sudo; it does not replace an existing port 443 app):

```bash
sudo tailscale serve --bg --https=8443 http://127.0.0.1:8788
# Then open https://<machine-tailnet-DNS-name>:8443
```

The first screen refreshes every ten seconds while preserving character positions.
Specialists remain at their meaningful workstations while idle; Hermes periodically
visits a teammate for a short, decorative check-in. Click a character to open their
workbench directly. The persistent character conversation sits beside current
assignments, progress and notes; on narrow screens they stack vertically.
**대화 이어가기** focuses the composer, and entering a room does not send a message.
The workbench companion is rendered as a complete, uncropped figure. Workbench
navigation is part of browser history, so Back returns to the prior Observatory
screen instead of leaving the site.
**움직임 멈추기** pauses roaming; reduced-motion preferences also stop movement.

The office uses a repository-owned transparent character sheet plus Ellie's
transparent English-tutor cutout under `browser/observatory/assets/`.
`bootstrap/install_observatory.sh` stages them with
the rest of the UI. The 2D cast moves through a zoned studio with paired desks,
research and review boards, an archive shelf, collaboration commons, coaching
lounge, coffee bar, and an enclosed acoustic audio booth. High-contrast wall
plaques identify `IRIS · THEO / RESEARCH · INTERVIEW` and
`JUN · MINA / CODE · SYSTEM DESIGN` above the character plane. Ellie has a
separate labeled English Lounge beside Coffee Club, while Rina stands inside
the `RINA · ON AIR` listening booth rather than alongside it. Mobile
keeps this same room in a horizontally scrollable viewport, with named character
shortcuts and visible next-action cards beneath it. Browser-only animation is
intentionally calm: idle specialists stay in their work areas, while Hermes
makes randomized leadership visits that avoid immediately repeating a teammate
and begin within seconds. A shuffled visit deck covers the whole team before a
teammate can recur, while per-teammate dialogue variants prevent the same exchange
from playing on consecutive visits. Every room displays an evidence-backed next
action such as due English reviews, unread papers, or an unfinished assignment;
clicking it opens the matching workbench. Hidden tabs and other views suspend animation.
Automatic speech now prioritizes each character's evidence-backed next action,
with randomized role lines and paired agent exchanges as supporting variety.
Both Hermes visits and teammate chats use four alternating lines (two complete
exchanges), with readable pauses between replies and no unrelated next-action
notice replacing either speaker before the conversation ends.
Rooms and dialogue scenes avoid immediate repeats, and a new bubble begins about
3.2–6 seconds after the previous exchange so a short office visit still shows
useful activity. Ambient team exchanges are scripted and never presented as actual
work. Selecting a character produces an immediate greeting. Passive bubbles do not
invoke the model or play audio. Hidden views and historical replay suspend small talk.
Hovering a character shows its most recent recorded work and David's next action
for that room without interrupting an active team exchange.
Character name/purpose cards use high-contrast type. The `−/＋` controls and a
two-finger pinch scale the complete office, furniture and cast from 60–140% on mobile.
The stage first auto-fits its actual container, so a full-screen or split-window
MacBook view shows the same complete office; horizontal scrolling appears only
after deliberate magnification. Zooming below 100% keeps the stage background
edge-to-edge instead of leaving an empty strip, while shrinking fixed-size cast and
labels. The mobile floor preserves workstation spacing so
room names and character cards do not collapse into one another. On narrow containers,
including Galaxy Fold landscape with the navigation sidebar open, compact mode
replaces the large character cards with name pills, keeps smaller live speech
bubbles attached directly above each speaking character, and renders next-action
cards in two readable columns.
During a Hermes visit, the two nearby bubbles shift away from each other. The
teammate's reply remains visible for about six seconds and is no longer immediately
replaced by a next-action notice while Hermes is still speaking.
On laptop and desktop, use the `‹` control on the sidebar edge to slide navigation
away and let the office fill the window; `›` restores it. The preference persists
in that browser, while the compact mobile navigation always remains available.

Office conversations use separate persisted `office_<room>` sessions on the
existing HQ API, classified into their matching Observatory rooms. They are
web-only conversations with the visual personas, not separate agent profiles and
not the English profile's private learner-memory sessions. The English and
podcast characters ask for relevant lesson text when needed. Existing dedicated
profile workbenches and Telegram coaching retain their original ownership.
Opening a character never invokes a model; pressing **보내기** does. The existing
four workbench Telegram composers remain separately labeled.
Session setup fails with a visible gateway error after 15 seconds instead of
hanging indefinitely; an active local-model turn may run for up to ten minutes.

- **LeetCode / System Design**: resume unfinished assignments or prepare today's
  assignment. System Design allows only one new interview per ISO week. In the
  LeetCode room, **작업 이어가기 · 새 문제** always selects the next uncompleted
  unskipped curriculum problem; **잠시 스킵 · 다음 문제**, **스킵 기록**, and
  **주제별 문제 목록** preserve unfinished work while changing problems/topics.
  **복습하기** is the separate action that selects a prior weak or due problem.
  Scheduled sessions keep the selected new problem and may suggest a weak review.
  The new-problem path follows the 35-minute Tue/Thu/Sat progression from Two
  Sum/HashMap through Two Pointers, Sliding Window, Stack, Binary Search,
  Tree/BFS/DFS, Heap, and Graph. Use a
  timer and submit actual practice results. Coding feedback records duration,
  confidence, hints and solution use. Design chat persists the answer, follow-ups,
  complete rubric, evidence-backed feedback, and the gated solution state. These update the existing coach
  state and review schedule. Opening a room alone does not assign or complete work.
- **English**: reveal due-card answers and mark each attempt correct or needing
  more practice. Results update the shared SRS deck used by Telegram drills.
- **Morning Echo**: see latest watched podcast link (channels or Podcast title), source date,
  last successful collection and selected long-sentence quotes, then reopen a video
  at each sentence’s timestamp. Its
  schedule and session history remain separate from tutor/SRS activity while it
  shares the English profile's learner memory.
- **Papers**: browse recent catalog entries, save a reading list, and mark papers
  read or unread. Original links open the source paper.
- **MLE Interview**: reopen the latest saved drill and keep your answer in room
  notes.
- **Dashboard chat**: Papers, MLE Interview, LeetCode, and System Design each
  have a persistent **Hermes에게 바로 질문하기** composer. Hermes answers with
  that room's coaching rules, retains the dashboard conversation as a normal
  session, and posts the question and answer to the matching Telegram group.
- **HQ Command Center**: submit a goal with context and priority. Hermes' Kanban
  decomposer turns it into a dependency graph, routes work to the `papers`,
  `interview`, `coding`, `design`, `english`, or existing `clawgram` profile, and asks the default HQ
  profile to synthesize dependent results. The live board shows queued, running,
  blocked, and completed work. Open a card for its body, parents/children, worker
  attempts, comments, errors, and final handoff; blocked work can be retried and
  non-running work can be reassigned.
- **Room notes**: save notes on the server and browse earlier versions under
  **기록 보관소 → 캠퍼스 노트 · 읽기 활동**. Unsaved note/form drafts, timer state,
  and the last opened room are retained in that browser's local storage.

Study workbenches use existing saved content and deterministic helpers. Sending
a dashboard chat message explicitly invokes Hermes through its key-authenticated
loopback API; the browser never receives that key or a Telegram token. HQ missions
are the orchestration path; submitting **계획 · 실행 시작** places real work on the
private `hermes-hq` board. Automatic grading is not used.

Use **대화 & 작업 기록** to search message text, titles, or tool names, select a
profile/room/date range, and page through transcripts and tool calls. An absent
session end timestamp is shown as unknown, not as evidence of an active agent.
Use **알림 스케줄** for next runs, prior execution status and delivery errors;
absence of a delivery error is not a receipt confirmation.

**기록 보관소** provides searchable, paginated learning assignments, submitted
feedback, English SRS cards, paper metadata and original links, current profile
memories, retained cron output, text lesson files, and noncompressed gateway logs.
Learning, papers and lesson sources are shared; memories, logs and outputs follow
the selected profile. Other profiles such as ClawGram are observed read-only;
their external project databases are not integrated or modified.

Sources are existing `state.db`, `sessions/sessions.json`, `gateway_state.json`,
`cron/jobs.json`, `cron/output/`, `memories/{MEMORY,USER}.md`, shared paper/learning
data and `~/english-lessons/`. SQLite archive connections use read-only/query-only
mode. Explicit dashboard chat submissions are the only workbench action that runs
Hermes and posts to a Telegram group. Other explicit study actions call the existing
`interview_progress.py` and `english_srs.py` helpers; notes and reading activity
are stored in `~/.hermes/data/observatory/workspace.json`. HQ tasks, dependencies,
comments, worker attempts, failures, and results are retained by Hermes under
`~/.hermes/kanban/boards/hermes-hq/`. Writes require a
same-origin JSON request with the action header and validated inputs. Coach
feedback is idempotent; SRS reviews use locking and a review counter to reject
stale retries; notebook revisions prevent stale overwrites across devices. Mission
creation also has an idempotency key so a network retry cannot duplicate a goal.

The installer creates a private random API key at
`~/.hermes/observatory/api.env`, enables Hermes' API server on
`127.0.0.1:8642`, and gives only the gateway and observatory services access to
that file. The browser connects only to the observatory on port 8788. Dashboard
chat delivery is restricted to the four explicit Telegram destinations already
registered by the cron configuration; chat IDs and bot credentials are not
returned to the browser.
The app excludes system
message rows, private reasoning columns, request dumps, auth/config files, audio,
compressed logs, and text attachments larger than 2 MB. Recognizable credentials
are redacted and transcript text is rendered without executing HTML. Missing or
deleted history cannot be reconstructed, and there is no separate durable event
collector; replay uses the retained session history.

```bash
systemctl --user status hermes-observatory.service
journalctl --user -u hermes-observatory.service -n 30 --no-pager
systemctl --user restart hermes-observatory.service
# Stop the observatory:
systemctl --user disable --now hermes-observatory.service
# If you enabled its optional HTTPS listener:
sudo tailscale serve --https=8443 off
```

Re-run the installer after changing the UI, service settings, Tailscale address,
or machine DNS name. `bootstrap/stage.py` copies the server alongside other
standalone helpers; the observatory installer owns UI staging and service setup.
It also stages the study helpers, including the SRS helper in the existing English
profile, so web and scheduled reviews share the same locking behavior. The four
headless specialist profiles are repository-owned and do not run Telegram gateways;
the default gateway dispatches their work. With the shared local Qwen endpoint,
`max_in_progress: 1` deliberately executes one mission worker at a time.

## Development
```bash
python3 -m pytest -q          # run the test suite
python3 bootstrap/stage.py --home /tmp/h   # dry stage into a scratch home
python3 bootstrap/register_cron.py --dry-run
```
Helper scripts must stay standalone (no repo-relative imports) so they run from
`~/.hermes/scripts/`. Keep logic in importable functions with a thin CLI, and add
tests for new behavior. See `AGENTS.md` for full conventions.
