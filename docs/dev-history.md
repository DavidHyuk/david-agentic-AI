# Development History

All notable changes to `david-agentic-ai` are documented here. Versions follow
semantic versioning (major.minor.patch).

## v0.7.1 — 2026-07-25 (patch: centralize checkpoint management)

### Changed
- Removed the duplicate `local-model/download_model.sh`; Hugging Face checkpoint
  downloads are now managed exclusively by `/home/david/workspace/models/download_model.py`.
- Updated model configuration comments, installer guidance, README, and project
  overview to use the dedicated models workspace while retaining `run_model.sh`
  as the vLLM service launcher.

## v0.7.0 — 2026-07-25 (minor: add vLLM service restart helper)

### Added
- Added `local-model/restart_service.sh` to restart `hermes-vllm.service`,
  verify that systemd activated it, and optionally wait for the OpenAI-compatible
  `/v1/models` endpoint after model loading.
- Added README and project-overview usage guidance plus regression coverage for
  the helper's safe command interface.

## v0.6.6 — 2026-07-25 (patch: document vLLM service operation)

### Changed
- Added README instructions for installing, starting, stopping, restarting, and
  observing the always-on `hermes-vllm.service`.
- Documented the persistent `HERMES_VLLM_GPU_UTIL` systemd override, including
  the 0.50 single-user recommendation and the distinction between vLLM KV cache
  capacity and Hermes persistent memory.
- Updated the project overview with the deployed service lifecycle and GPU
  memory-tuning guidance.

## v0.6.5 — 2026-07-25 (patch: fix Codex Stop hook output)

### Fixed
- The Codex-owned automatic commit hook now keeps stdout empty and sends its
  human-readable status to stderr. Codex treats non-empty `Stop` hook stdout as
  JSON, so the previous success message caused
  `hook returned invalid stop hook JSON output` after otherwise successful
  commits and pushes.
- The test gate now invokes `pytest -q` from the Codex session's inherited
  `PATH`. The hook itself runs under `/usr/bin/python3`, where the project's
  Conda-installed pytest module is not available.
- Hook documentation now records the Codex stdout contract and the local
  `.git/codex-auto-commit.log` diagnostic path.

### Verified
- Added regression coverage for both successful and failed diagnostics,
  including an assertion that stdout remains empty.
- Full suite: `135 passed`.

## v0.6.4 — 2026-07-25 (patch: make the Stop hook Codex-owned)

### Fixed
- Moved the shared auto-commit implementation from `.cursor/hooks/` to
  `.codex/hooks/`; Codex no longer depends on a Cursor-owned path.
- `.codex/hooks.json` now resolves the implementation from the Git root, as
  recommended for sessions started from repository subdirectories.
- Cursor's stop configuration delegates to the Codex-owned implementation.
- Automatic commits now preserve both sides of renames, stage deletions with
  `git add -A`, and use a normal commit so moved/deleted files are not left in
  the index.
- The hook refuses to mix pre-existing user-staged changes into its commit and
  removes any newly staged path that fails the secret/binary allowlist.

### Changed
- Hook tests, README, `AGENTS.md`, and hook-specific documentation now identify
  `.codex/hooks/auto_git_commit.py` as the canonical implementation.

### Verified
- The repository is already trusted in `~/.codex/config.toml`.
- Full suite: `133 passed`.

## v0.6.3 — 2026-07-25 (patch: consolidate Codex instructions)

### Changed
- Removed the redundant `CODEX.md`. Codex automatically discovers
  `AGENTS.md`, while `CODEX.md` was only an ordinary project document.
- `AGENTS.md` is now the single source of truth for project behavior,
  Conventional Commits, hook staging exclusions, test gating, push retry, and
  diagnostics.
- The auto-commit root allowlist and tests no longer treat `CODEX.md` as a
  managed instruction file.

### Verified
- Full suite: `131 passed`.

## v0.6.2 — 2026-07-25 (patch: runtime instructions and hook observability)

### Fixed
- `AGENTS.md` now describes the deployed Telegram notification path,
  Kakao-to-Telegram English flow, Qwen3.6 FP8 checkpoint, vLLM `:8003`
  endpoint, 128K context, and current model/browser/MCP paths instead of the
  stale WhatsApp + llama.cpp `:8080` setup.
- The Codex Stop hook no longer relies on shell command substitution and now
  prints and records test, commit, and push outcomes instead of silently
  discarding every failure.
- The safe-path allowlist now includes the implemented `browser/` and `mcp/`
  source trees, which were previously omitted from automatic commits.
- A failed push is retried on a later Stop event even when no new files need to
  be committed.

### Added
- `CODEX.md` documents Conventional Commits, staging exclusions, hook trust,
  manual execution, and failure recovery.
- Local hook diagnostics at `.git/codex-auto-commit.log`; Git metadata keeps
  this log outside the worktree and prevents recursive auto-commits.
- Tests for `CODEX.md`/browser/MCP allowlisting, compact cross-cutting commit
  messages, command portability, push retries, and local diagnostic output.

### Verified
- Focused hook suite: `10 passed`.
- Full suite: `131 passed`.

## v0.6.1 — 2026-07-25 (patch: Kakao intake E2E hardening)

### Fixed
- English intake now records processed file versions instead of treating an
  entire date folder as permanently complete. A second Kakao correction on the
  same day is returned once, then suppressed after `--mark`.
- Legacy `processed.json` session IDs are migrated by snapshotting their
  existing files, preventing historical reprocessing during the upgrade.
- Kakao webhook startup and HTTP request logs no longer expose the high-entropy
  endpoint path or raw Kakao user IDs.
- Restarting the webhook no longer stops its Quick Tunnel dependency and rotates
  the public hostname. The installer reads logs from the current cloudflared PID
  and refreshes the private URL only after that tunnel is registered.
- Open Builder setup instructions now explicitly select **스킬데이터로 사용**
  before removing the mandatory static fallback response; merely editing or
  emptying the default text does not render the webhook's `template`.
- Real-channel troubleshooting now distinguishes Channel Manager's operating-hours
  and chat-disabled messages from chatbot responses, documents the bot-only
  channel setup, and clarifies that an existing 1:1 room never converts into a
  chatbot room.
- Sender enrollment instructions now distinguish Open Builder's bot-test
  identity from real KakaoTalk app identities and require re-sending the first
  intentionally rejected message after approval.

### Added
- Private mode-0600 sender observation state and
  `--approve-latest-sender`, which adds a known recent sender to
  `KAKAO_ALLOWED_USER_IDS` without printing its raw ID.
- `--rotate-path` installation flow that invalidates the old endpoint,
  restarts the webhook/tunnel, and writes the current Open Builder URL to a
  mode-0600 runtime file.
- systemd sandboxing and mode-0700 write directories for English lesson and
  sender-state data.

### Verified
- Three synthetic Kakao HTTP requests produced three correction files; the
  first intake found two files and a later same-day intake found only the new
  third file.
- The public HTTPS endpoint reached the local webhook and rejected an invalid
  payload with Kakao schema version 2.0.
- After allowlisting the real test sender, the current public endpoint returned
  HTTP 200 with a valid Kakao `simpleText` response in 421 ms.
- Recent runtime logs contain neither the rotated secret path nor raw sender IDs.
- The deployed real KakaoTalk Channel chatbot enforced sender enrollment, then
  accepted the approved real-app sender, returned HTTP 200, and queued the
  feedback file at 13:34 local time.

## v0.6.0 — 2026-07-25 (minor: independent paper ingestion v2)

### Added
- `scripts/papers_ingest.py` — standalone, zero-LLM metadata ingestion for arXiv
  `cs.AI`, `cs.CL`, `cs.LG`, `cs.CV` and Hugging Face Daily Papers.
- A versioned SQLite catalog under `~/.hermes/data/papers/papers.db` with
  canonical arXiv-ID deduplication, source provenance, personal relevance
  scores, and durable ingestion run status/errors.
- One-time, read-only migration of the existing Subscribe-Papers rows and PDF
  paths; the legacy database and its 45 papers remain untouched.
- `hermes-papers-ingest.service` and `.timer`, plus
  `bootstrap/install_papers_service.sh`, for daily 08:00 ingestion independent
  of Hermes, the gateway, and the local LLM.
- Offline tests for source parsing, canonical IDs, relevance scoring, source
  merging, legacy migration, partial failures, schema upgrades, and systemd
  wiring.

### Changed
- `papers-digest` v2.0.0 and `papers_digest.py` now consume the new catalog
  read-only and support `recommended`, `recent`, and `trending` views.
- The 08:30 digest reads at most five candidates after the independent timer;
  on stale data it reports ingestion health instead of launching scrapers.
- `interview_trends.py` now uses the same runtime paper catalog.
- README, project overview, bootstrap instructions, environment template, and
  runtime data staging document the new operating model.

### Why
The old Subscribe-Papers prototype had useful data but its scheduler had been
stale since February and coupled scraping, PDF downloads, and LLM analysis.
Separating cheap metadata ingestion from agent reasoning gives Hermes a fresh,
observable source while preserving the legacy assets. SQLite remains the
source of truth; PDF-on-demand, OpenReview, Semantic Scholar, and Qdrant remain
deliberate later phases.

### Verified
- Live temporary-catalog smoke: arXiv 3 + Hugging Face 3 records, successful
  source parsing, persistence, and status reporting.
- Production first run: 284 unique papers, including all 45 legacy PDF/analysis
  rows; 200 current arXiv and 50 Hugging Face observations completed with
  `success`, and SQLite reported `integrity_check=ok`.
- `hermes-papers-ingest.timer` is active/enabled for the next 08:00 run, and
  the 08:30 `papers-digest` cron entry was refreshed.
- Hermes/Qwen3.6 E2E invoked the staged helper against the new catalog and
  returned two real titles with `PAPERS_DIGEST_OK`.
- `pytest -q`: **118 passed**.

## v0.5.0 — 2026-07-25 (minor: official Google Calendar MCP)

### Added
- `mcp/google-calendar.yaml` — Google's official remote Calendar MCP endpoint,
  three read-only OAuth scopes, and a three-tool read-only allowlist.
- `mcp/setup_google_calendar.py` — validates a Web OAuth client, atomically
  configures Hermes, and restricts `~/.hermes/config.yaml` to mode `0600`.
- `mcp/calendar_smoke.py` — MCP discovery plus a privacy-preserving Qwen3.6
  `list_calendars` E2E check.
- `docs/google-calendar-mcp.md` — Cloud API, consent screen, callback URI,
  authorization, verification, and revocation procedure.
- Unit tests for OAuth client validation, callback enforcement, tool
  allowlisting, secure config writes, and smoke-output recognition.

### Changed
- `calendar-assistant` v1.1.0 now uses the official Google Calendar MCP,
  explicitly treats calendar content as untrusted, and forbids mutation tools.
- Bootstrap and README now point to the reproducible Calendar MCP setup instead
  of the incomplete `hermes mcp add google-calendar` command.

### Security
- Only `list_calendars`, `list_events`, and `get_event` are exposed.
- OAuth is limited to Calendar list/event read and free-busy scopes.
- OAuth secrets remain outside git; runtime config is written with mode `0600`.

### Interactive follow-up
- Live calendar authorization and E2E require David to choose a Google Cloud
  project and provide its downloaded Web OAuth client JSON.
- The agreed following work is recorded in `docs/next-steps.md`: ask David for
  paper/job ingestion requirements before Qdrant design, then run a real Kakao
  English-sentence E2E together.

### Verified
- `pytest -q`: **104 passed**.
- Google's protected-resource metadata endpoint resolves to the official
  Calendar MCP resource and Google OAuth authorization server.
- Existing `hermes-vllm`, `hermes-browser`, and `hermes-gateway` services remain
  active. The MCP entry is intentionally not enabled before OAuth credentials
  are supplied.

## v0.4.0 — 2026-07-25 (minor: Qwen3.6 FP8 + built-in browser)

### Added
- `local-model/setup_vllm.sh`, `model_preflight.py`, `smoke_test.py` — isolated
  CUDA-compatible vLLM setup, checkpoint validation, and OpenAI tool-call smoke test.
- `local-model/hermes-vllm.service` + `install_service.sh` — always-on Qwen3.6
  FP8 user service.
- `browser/setup_browser.sh` + `hermes-browser.service` — pinned
  `agent-browser 0.33.0` and a localhost-only Chromium CDP backend.
- `browser/browser_smoke.py` — deterministic navigation, title, click, DOM text,
  and accessibility-snapshot verification.
- Unit tests for model preflight/launch/smoke logic and browser response validation.

### Changed
- Hermes now uses `/home/david/workspace/models/Qwen/Qwen3.6-35B-A3B-FP8`
  through vLLM `0.19.0+cu130` at `:8003`, with 131072-token context,
  `qwen3` reasoning parsing, and `qwen3_coder` tool-call parsing.
- All config fragments explicitly select Hermes's local Built-in Browser and
  connect it to `http://127.0.0.1:19222`.
- Bootstrap now installs and verifies the browser runtime after staging config.

### Why
The Qwen3.6 FP8 checkpoint is the validated local Hermes backend on the DGX
Spark. For browsing, direct Snap Chromium auto-launch hangs on this ARM64 host;
starting the same browser as a localhost-only CDP service is reliable while
preserving the intended `Hermes Built-in Browser` abstraction. LangGraph,
direct Playwright code, and Qdrant remain intentionally deferred until their
workflow/state or retrieval value is demonstrated.

### Verified
- `pytest -q`: **94 passed**.
- Model smoke: Qwen3.6 endpoint discovery and forced `get_weather` tool call passed.
- Browser smoke: navigation, title, click, DOM text, and accessibility snapshot passed.
- Hermes E2E: Qwen3.6 invoked the browser tool and returned
  `HERMES_BROWSER_OK: Example Domain`.
- `hermes-vllm`, `hermes-browser`, and `hermes-gateway` user services are active
  and enabled.

## v0.3.0 — 2026-07-25 (minor: Codex auto commit/push)

### Added
- `.codex/hooks.json` — trusted Codex `Stop` hook configuration.
- `.codex/hooks/README.md` — hook review and trust instructions.

### Changed
- The shared agent hook runs `pytest -q` before committing, stages only known
  source/documentation paths, filters secrets and binary assets, and creates
  Conventional Commits messages according to `AGENTS.md` before pushing the
  current branch upstream.

### Why
The existing `.cursor` hook did not configure Codex. The project now has a
Codex-native lifecycle entry point while retaining one implementation for both
clients.

## v0.2.1 — 2026-06-10 (patch: cron hardening + auto-commit hook)

### Added
- `scripts/cron_health.py` — detects a stuck `~/.hermes/cron/.tick.lock` or stale
  `jobs.json` `last_run_at` timestamps; optional `--restart` runs
  `hermes gateway restart`.
- `tests/test_cron_health.py` — 6 cases (lock age, overdue jobs, disabled jobs,
  assess/report, CLI exit codes).
- `.cursor/hooks.json` + `.cursor/hooks/auto_git_commit.py` — `stop` hook that
  commits and pushes repo changes after an agent session using Conventional
  Commits messages derived from the diff (no Cursor branding).
- `tests/test_auto_git_commit.py` — 3 cases (message format, docs scope, secret
  path filtering).

### Changed
- `config/config.fragment.yaml` (+ qwen36/minimax variants) — `cron.max_parallel_jobs: 1`
  so cron jobs run sequentially and a single hung agent call cannot wedge the
  scheduler behind a stuck tick lock.
- `config/env.example` — documents optional `HERMES_CRON_MAX_PARALLEL` and
  `HERMES_CRON_TIMEOUT` overrides.

### Why
After a five-day cron outage caused by a stuck tick lock, we needed operational
guardrails (health check + sequential jobs) and a low-friction way to keep the
version-controlled repo in sync when iterating in Cursor.

---

## v0.2.0 — 2026-06-03 (minor: live interview-trend ingestion)

### Added
- `scripts/interview_trends.py` — a deterministic data layer that pulls *current*
  interview signal so drills reflect what Staff/Senior MLE candidates are actually
  asked now, instead of recycling the static `question-bank.md` seed. Sources are all
  free / no-auth: **Hacker News** (Algolia API, discourse), **GitHub search** (trending
  interview-prep repos + hot ML tooling), and the **Subscribe-Papers DB** (frontier
  grounding, reusing `papers_digest`). Per-pillar query plans feed a source-diverse
  ranking that round-robins sources so GitHub's huge star counts don't bury fresh HN/
  paper signal. Network fetches are isolated and degrade gracefully (a failed source
  yields an empty list, never a broken drill); results cache to
  `~/.hermes/data/interview/trends.json`. Full brief runs in ~7s.
- `tests/test_interview_trends.py` — 12 cases (normalization, source-diverse ranking,
  cache roundtrip, pillar orchestration with the network stubbed, graceful failure).

### Changed
- `skills/career/interview-prep/SKILL.md` — drills now lead with the live trend brief
  (`interview_trends.py --pillar <pillar>`) and fall back to the seed bank only when the
  fetch is thin. Added `interview.trends_cache` config key; updated procedure, resources,
  and verification to require current, real resources (repo/thread/paper) over evergreen
  guesses.
- `cron/jobs.yaml` — the `interview-prep` job prompt now instructs running
  `interview_trends.py` for the chosen pillar before composing the drill.

### Why
The biggest weakness of the prep loop was staleness: a fixed seed bank can't track
shifting interview expectations (e.g. LLM-serving system design, agent eval, current
behavioral bar). Grounding each drill in live, ranked, multi-source signal keeps prep
aligned with the present-day Silicon Valley MLE bar with zero manual curation.

---

## v0.1.1 — 2026-06-02 (patch: switch model backend to vLLM + Qwen3.5)

### Changed
- `local-model/run_hermes_model.sh` — replaced llama.cpp invocation with `vllm serve`,
  pointing at the same `Qwen3.5-122B-A10B-AWQ` weights already on disk in ClawGram
  (`/home/david/workspace/ClawGram/models/Qwen/Qwen3.5-122B-A10B-AWQ`). Serves on
  `:8003` (separate from ClawGram's `:8001`/`:8002`) with `--max-model-len 65536`
  (satisfying Hermes's ≥64K requirement). Sampling penalties moved to
  `providers.qwen-hermes.extra_body` (vLLM has no `--presence-penalty` CLI).
- `config/config.fragment.yaml` — updated `model.base_url` to `http://localhost:8003/v1`
  and `model.default` to `Qwen3.5-122B-A10B-AWQ` (matching `--served-model-name`).
- `config/memory/MEMORY.md` — reflects new engine and both endpoints (vLLM on `:8003`
  for Hermes; llama.cpp on `:8080` for Subscribe-Papers — unchanged).
- `~/.hermes/config.yaml` — live config updated via `hermes config set`.

---

## v0.1.0 — 2026-06-02 (minor: initial release)

Initial implementation of David's personalized Hermes Agent configuration package.

### Added
- **Agent identity**
  - `config/soul/SOUL.md` — personality of "Hermes", a proactive ML-career/learning
    partner for David (Staff/Senior MLE candidate, LLM/LVM researcher).
  - `config/memory/USER.md` (926/1375 chars) and `config/memory/MEMORY.md`
    (1182/2200 chars) — seed persistent memory within Hermes limits.
- **Skills** (`skills/<category>/<name>/SKILL.md`)
  - `papers-digest` — LLM/LVM research digest from the Subscribe-Papers SQLite DB,
    with interview-relevance framing.
  - `interview-prep` — Staff/Senior MLE rotating 5-pillar curriculum, drills, rubrics,
    progress log; ships `references/curriculum.md` + `references/question-bank.md`.
  - `english-practice` — ingest tutor recordings/corrections → transcripts → SRS drills.
  - `calendar-assistant` — Google Calendar (MCP) daily brief with conflicts, free
    slots, and schedule-aware suggestions.
- **Helper scripts** (standalone + unit-tested, staged to `~/.hermes/scripts/`)
  - `papers_digest.py`, `english_intake.py`, `english_srs.py` (Leitner SRS), `agenda.py`.
- **Automation**
  - `cron/jobs.yaml` — six declarative WhatsApp notification jobs.
  - `bootstrap/register_cron.py` — sync `jobs.yaml` → `hermes cron`.
- **Bootstrap**
  - `bootstrap/install.sh` — install Hermes, stage config, configure local endpoint,
    print interactive steps.
  - `bootstrap/stage.py` — idempotent staging into `~/.hermes` with backups + YAML
    deep-merge; memory seeds are never clobbered by default.
  - `config/config.fragment.yaml` — local DGX Spark custom endpoint + memory + cron
    settings.
  - `local-model/run_hermes_model.sh` — launch gpt-oss-120b at `-c 65536` (Hermes
    needs ≥64K context; Subscribe-Papers used 8K).
- **Quality**
  - `tests/` — 45 pytest cases covering the scripts, skill frontmatter, cron schema,
    and staging behavior.
  - `AGENTS.md`, `README.md`, `.gitignore`, `requirements.txt`.

### Notes / follow-ups (require user-interactive setup)
- WhatsApp gateway device link (`hermes gateway setup`).
- Google Calendar MCP OAuth (`hermes mcp add google-calendar`).
- Confirm the served model name via `curl -s localhost:8080/v1/models`.
