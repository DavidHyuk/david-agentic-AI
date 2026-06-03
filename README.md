# david-agentic-ai

A personalized, always-on AI partner for **David Choi**, built on the
[**Hermes Agent**](https://github.com/NousResearch/hermes-agent) framework
(Nous Research). It learns David's life and goals over time and proactively helps
with four things, delivered to **WhatsApp**:

1. **LLM/LVM research** — daily digest from the existing `Subscribe-Papers` project.
2. **Staff/Senior MLE interview prep** — a rotating curriculum with drills + rubrics.
3. **English practice** — turns tutor recordings + corrections into spaced-repetition drills.
4. **Calendar** — a prioritized Google Calendar brief with conflicts, free slots, and suggestions.

This repository is the **single source of truth** for the agent's configuration.
Assets are synced into the Hermes runtime home (`~/.hermes`) by `bootstrap/stage.py`.

## Why a config repo instead of ad-hoc setup?
Hermes stores skills, memory, personality, scripts, and cron jobs under `~/.hermes`.
Keeping them version-controlled here makes the setup **reproducible, testable, and
maintainable**: edit in the repo, re-run `stage.py`, done. The runtime stays a
disposable cache.

## Architecture

```
Local DGX Spark (llama.cpp @ :8080, >=64K ctx)
        │  OpenAI-compatible API
        ▼
   Hermes Agent  ──────────────────────────────────────────────► WhatsApp
        │ skills (procedural)   │ cron (schedule)   │ memory (who David is)
        ├─ papers-digest  ── reads Subscribe-Papers/data/papers.db
        ├─ interview-prep ── curriculum + progress log
        ├─ english-practice ─ english_intake.py + english_srs.py (~/english-lessons)
        └─ calendar-assistant ─ google-calendar MCP + agenda.py
```

## Repository layout
| Path | Purpose |
|---|---|
| `config/soul/SOUL.md` | Agent personality (→ `~/.hermes/SOUL.md`) |
| `config/memory/{USER,MEMORY}.md` | Seed memory (→ `~/.hermes/memories/`) |
| `config/config.fragment.yaml` | Non-secret settings merged into `config.yaml` |
| `config/env.example` | Template for `~/.hermes/.env` secrets |
| `skills/<category>/<name>/SKILL.md` | The four custom skills |
| `scripts/*.py` | Standalone, unit-tested helpers (→ `~/.hermes/scripts/`) |
| `cron/jobs.yaml` | Declarative WhatsApp notification schedule |
| `bootstrap/install.sh` | One-shot installer + orchestrator |
| `bootstrap/stage.py` | Idempotently stage repo → `~/.hermes` |
| `bootstrap/register_cron.py` | Register `jobs.yaml` with `hermes cron` |
| `local-model/run_hermes_model.sh` | Launch Qwen3.5-122B (vLLM) for Hermes |
| `local-model/download_minimax_m27.sh` | Download MiniMax-M2.7 AWQ 4-bit |
| `local-model/run_hermes_model_minimax.sh` | Launch MiniMax-M2.7 for Hermes |
| `config/config.fragment.minimax.yaml` | Hermes provider config for MiniMax |
| `tests/` | Pytest suite |

## Quick start

```bash
# 0. Install Python tooling deps
python3 -m pip install -r requirements.txt

# 1. Run the bootstrap (installs Hermes if missing, stages config, sets model)
bash bootstrap/install.sh

# 2. Start the local model at >=64K context (NOT the 8K Subscribe-Papers script)
sh local-model/run_hermes_model.sh

# 3. Verify a plain chat
hermes -q "Which model are you, and what do you know about me?"
```

Then complete the **interactive, one-time** steps `install.sh` prints:
- `hermes gateway setup` → connect **WhatsApp** (QR device link), then `hermes gateway install`.
- `hermes mcp add google-calendar` → authorize **Google Calendar** (OAuth).
- `python3 bootstrap/register_cron.py` → schedule the WhatsApp briefs.
- Drop tutor recordings + corrections into `~/english-lessons/`.

## Scheduled WhatsApp notifications (`cron/jobs.yaml`)
| Job | When (local) | What |
|---|---|---|
| `morning-brief` | 07:30 daily | Calendar agenda + suggested plan |
| `papers-digest` | 08:30 weekdays | LLM/LVM research signal |
| `interview-prep` | 12:00 Mon/Wed/Fri | One focused Staff/Senior MLE drill |
| `english-intake` | 20:00 daily | Ingest new lessons → SRS cards |
| `english-drill` | 21:00 daily | Tonight's spaced-repetition drill |
| `weekly-review` | 18:00 Sunday | Papers + prep + English weekly summary |

## Local model note
Hermes requires a model with **≥64K context**. The Subscribe-Papers `run_model.sh`
serves at `-c 8192`, which Hermes rejects. Use `local-model/run_hermes_model.sh`
(Qwen3.5 on `:8003`) or `local-model/run_hermes_model_minimax.sh` (MiniMax-M2.7).
Only one large model should run at a time on 128GB VRAM.

### Switching to MiniMax-M2.7 (DGX Spark)
```bash
# 1. Download (~100GB+, inside Docker /app or repo root)
bash local-model/download_minimax_m27.sh

# 2. Stop Qwen vLLM, start MiniMax
bash local-model/run_hermes_model_minimax.sh

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

## Development
```bash
python3 -m pytest -q          # run the test suite
python3 bootstrap/stage.py --home /tmp/h   # dry stage into a scratch home
python3 bootstrap/register_cron.py --dry-run
```
Helper scripts must stay standalone (no repo-relative imports) so they run from
`~/.hermes/scripts/`. Keep logic in importable functions with a thin CLI, and add
tests for new behavior. See `AGENTS.md` for full conventions.
