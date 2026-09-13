# Project Context — david-agentic-ai

This repo is the **version-controlled configuration** for David Choi's personal
Hermes Agent (Nous Research). The repo is the single source of truth; assets are
synced into `~/.hermes` (HERMES_HOME) by `bootstrap/stage.py`.

## What this agent is for
A proactive, always-on partner that helps David land a **Staff/Senior ML Engineer**
role in Silicon Valley, stay current on **LLM/LVM research**, and practice
**English** — with regular notifications through a dedicated **English Telegram
bot**. Calendar support is
retained in source but intentionally deferred and disabled. English
tutor feedback enters through the KakaoTalk Channel chatbot and is processed
locally before the review and SRS drill are delivered through Telegram.
The existing English profile also pre-downloads one English Goal Podcast
transcript each morning and delivers a personalized 09:00 lesson in the same
English Telegram chat.

## Layout
- `config/soul/SOUL.md` — agent personality (staged to `$HERMES_HOME/SOUL.md`).
- `config/memory/{MEMORY,USER}.md` — seed memory (staged to `$HERMES_HOME/memories/`).
- `config/config.fragment.yaml` — non-secret settings, deep-merged into config.yaml.
- `skills/<category>/<name>/SKILL.md` — the David profile skills; English is
  isolated under `profiles/english/skills/`.
- `profiles/english/` — isolated SOUL, memory, config, and English-practice
  skill, staged to `~/.hermes/profiles/english`.
- `profiles/english/skills/learning/english-podcast-coach/` — transcript-backed
  daily podcast workflow that shares the existing English profile, memory, and
  Telegram bot while keeping download state separate.
- `scripts/*.py` — standalone helpers staged to `$HERMES_HOME/scripts/` and unit-tested.
- `cron/jobs.yaml` — declarative Telegram notification schedule.
- `bootstrap/` — staging, cron registration, and systemd service installers,
  including the automatic cron watchdog.
- `local-model/run_model.sh` — launch the default Qwen3.6 FP8 vLLM backend at
  128K context or a supported alternative model.
- `browser/` — Hermes Built-in Browser backed by localhost-only Chromium CDP.
- `mcp/` — deferred Google Calendar read-only MCP setup retained for later.
- `tests/` — pytest suite for the scripts, skill frontmatter, and cron schema.

## Conventions
- Helper scripts MUST stay standalone (no repo-relative imports) so they run from
  `~/.hermes/scripts/`. Keep pure logic in importable functions + a thin CLI.
- Every code file that needs explanation starts with the author tag and a purpose
  docstring/comment.
- Add/adjust unit tests in `tests/` for any new helper logic.
- Memory seeds must respect Hermes limits: USER.md ≤ 1375 chars, MEMORY.md ≤ 2200.
- For changes to executable source code, helper scripts, or tests, run `pytest -q`
  before considering the change done. For documentation, configuration, memory,
  skill-content, or other non-code-only changes, run only directly relevant
  checks (or skip tests when none apply).
- When a source-code change adds a new feature, update `README.md` with the
  feature's usage instructions.
- Codex lifecycle hooks live in `.codex/hooks.json`; after changing a hook,
  review and trust it through Codex `/hooks` before expecting execution.
- Automatic git commits use the Conventional Commits rules in this file and
  must never stage secrets, runtime files, or binary assets.

## Version History

If a change constitutes a project version update, record it in
`docs/dev-history.md` using semantic versioning:

- **Major** — breaking changes or significant architectural shifts
- **Minor** — new features or non-breaking capability additions
- **Patch** — bug fixes, small improvements, or config/documentation updates

Document what changed and why, not just that it changed.

## Commit Style

Commits follow the Conventional Commits format:

```
<type>(<optional scope>): <short imperative summary>
```

Allowed types are `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`,
and `perf`.

Examples:

- `feat(skills): add papers-digest skill with SRS integration`
- `fix(gateway): resolve skill ambiguity caused by duplicate external_dirs`
- `refactor(stage): replace shutil.copy with symlinks for skills`

## Automatic Commit Hook

`AGENTS.md` is the single source of truth for both project instructions and
automatic commit rules. Codex owns the shared implementation at
`.codex/hooks/auto_git_commit.py`; Cursor may delegate to it but Codex must not
depend on a Cursor-owned script. On a trusted Codex `Stop` or Cursor `stop`
event, the hook must:

1. stage only allowlisted project source, configuration, test, and documentation
   paths;
2. exclude secrets, runtime data, databases, model weights, and binary assets;
3. require `pytest -q` to pass;
4. create one Conventional Commit using the rules above; and
5. push the current branch when it has a configured upstream.

Hook failures remain fail-open for the agent turn but must be observable in
stdout/stderr and `.git/codex-auto-commit.log`. A failed push must be retried on
the next Stop event even if no new commit-worthy changes exist.

## Living Documentation

After changes affecting structure, capabilities, or usage, keep these documents
current:

- `docs/dev-history.md` — every version bump.
- `docs/project-overview.md` — directory structure, scripts, test count, cron
  schedule, skill capabilities, model/engine options, and the core technology
  section.

The project overview should describe the current system without requiring the
reader to reconstruct it from git history.

## Maintainability

- Prefer explicit over clever; clear small functions are preferred.
- Name things by what they represent, not how they are implemented.
- Avoid deep nesting and premature abstractions.

## New Agent and Telegram Routing Policy

When adding an agent-like capability, default to a new skill and cron job on the
best-matching existing Hermes profile and Telegram bot. Decide the Telegram chat
destination separately; reusing a profile or bot does not require mixing every
workflow into one chat. Keep mutable state in a separate data path when that
prevents coupling. Do not create a new profile, gateway, Telegram bot token, or
parallel service merely to give the capability a distinct name.

Create a separate profile or bot only when at least one concrete boundary
requires it:

- a different audience, credential, privacy, or delivery destination;
- identity or memory isolation that would otherwise contaminate behavior;
- incompatible model, tool, configuration, security, or lifecycle needs;
- independent failure/restart isolation with a demonstrated operational value;
- an explicit user request for a separate bot or profile.

Before introducing a new profile or gateway, check for token polling conflicts,
duplicate cron delivery, memory and state ownership, staging cleanup behavior,
watchdog changes, and installation burden. Prefer the design with fewer runtime
components when it provides equivalent behavior without side effects. Record
the routing decision in `docs/dev-history.md` and keep
`docs/project-overview.md` current.

Evaluate chat-room separation independently from profile and bot isolation:

- Use a separate chat or group when a recurring content feed would bury an
  interactive workflow, the workflows have meaningfully different cadence or
  response loops, separate history/search or notification controls add value,
  or the user requests a topic boundary.
- Reuse the same chat when messages are infrequent, form one continuous
  conversation, or separation would fragment context without a practical UX
  benefit.
- Prefer one existing bot in multiple chats over multiple bots when identity,
  memory, permissions, and ownership should remain shared.
- Route a dedicated chat through a validated `deliver_chat_id_env` value. If a
  dedicated destination is selected, fail closed when its numeric chat ID is
  missing or invalid; never silently fall back to the bot's default chat.

For the English Goal Podcast workflow, the preferred target is a dedicated
Podcast English Telegram group served by the existing `english` profile and bot:
daily podcast posts remain separate from tutor/SRS interaction while learner
memory and credentials stay shared.

Every new user-visible agent or agent-like workflow must also be registered in
Hermes Personal Observatory in the same change. Treat an Observatory room as a
UX and history boundary, not as evidence that a separate Hermes profile, gateway,
or bot is required. Reuse the owning profile while giving a distinct workflow
its own room when that improves schedule visibility, session classification,
source-state inspection, or interaction. Update the room definition, cron and
current/historical session routing, owning-profile mapping, useful workbench
state, tests, `README.md`, `docs/project-overview.md`, and
`docs/dev-history.md`. Do not add an empty room for a purely internal helper
that has no user-facing schedule, history, state, or action; record that reason
instead.

## Key external paths
- Subscribe-Papers DB: `/home/david/workspace/Subscribe-Papers/data/papers.db`
- Hermes paper catalog: `~/.hermes/data/papers/papers.db`
- Local LLM checkpoint:
  `/home/david/workspace/models/Qwen/Qwen3.6-35B-A3B-FP8`
- Local LLM endpoint: `http://localhost:8003/v1` (vLLM, 128K context)
- English lessons inbox: `~/english-lessons/`
