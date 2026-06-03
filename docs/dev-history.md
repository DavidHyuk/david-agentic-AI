# Development History

All notable changes to `david-agentic-ai` are documented here. Versions follow
semantic versioning (major.minor.patch).

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
