# Project Context — david-agentic-ai

This repo is the **version-controlled configuration** for David Choi's personal
Hermes Agent (Nous Research). The repo is the single source of truth; assets are
synced into `~/.hermes` (HERMES_HOME) by `bootstrap/stage.py`.

## What this agent is for
A proactive, always-on partner that helps David land a **Staff/Senior ML Engineer**
role in Silicon Valley, stay current on **LLM/LVM research**, practice **English**,
and manage his **calendar** — with regular **WhatsApp** notifications.

## Layout
- `config/soul/SOUL.md` — agent personality (staged to `$HERMES_HOME/SOUL.md`).
- `config/memory/{MEMORY,USER}.md` — seed memory (staged to `$HERMES_HOME/memories/`).
- `config/config.fragment.yaml` — non-secret settings, deep-merged into config.yaml.
- `skills/<category>/<name>/SKILL.md` — the four custom skills.
- `scripts/*.py` — standalone helpers staged to `$HERMES_HOME/scripts/` and unit-tested.
- `cron/jobs.yaml` — declarative WhatsApp notification schedule.
- `bootstrap/` — `install.sh`, `stage.py`, `register_cron.py`.
- `local-model/run_hermes_model.sh` — launch local gpt-oss-120b at 64K+ context.
- `tests/` — pytest suite for the scripts, skill frontmatter, and cron schema.

## Conventions
- Helper scripts MUST stay standalone (no repo-relative imports) so they run from
  `~/.hermes/scripts/`. Keep pure logic in importable functions + a thin CLI.
- Every code file that needs explanation starts with the author tag and a purpose
  docstring/comment.
- Add/adjust unit tests in `tests/` for any new helper logic.
- Memory seeds must respect Hermes limits: USER.md ≤ 1375 chars, MEMORY.md ≤ 2200.
- Run `pytest -q` before considering a change done.

## Key external paths
- Subscribe-Papers DB: `/home/david/workspace/Subscribe-Papers/data/papers.db`
- Local LLM endpoint: `http://localhost:8080/v1` (llama.cpp, must be ≥64K ctx)
- English lessons inbox: `~/english-lessons/`
