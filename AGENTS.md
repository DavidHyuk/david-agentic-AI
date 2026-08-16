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
locally before the review and SRS drill are delivered through Telegram. ClawGram
runs as a separate Hermes profile and Telegram bot, with approval and KakaoTalk
delivery outside agent authority.

## Layout
- `config/soul/SOUL.md` — agent personality (staged to `$HERMES_HOME/SOUL.md`).
- `config/memory/{MEMORY,USER}.md` — seed memory (staged to `$HERMES_HOME/memories/`).
- `config/config.fragment.yaml` — non-secret settings, deep-merged into config.yaml.
- `skills/<category>/<name>/SKILL.md` — the David profile skills; English is
  isolated under `profiles/english/skills/`.
- `profiles/english/` — isolated SOUL, memory, config, and English-practice
  skill, staged to `~/.hermes/profiles/english`.
- `profiles/clawgram/` — isolated SOUL, memory, config, and family-letter skill.
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

## Key external paths
- Subscribe-Papers DB: `/home/david/workspace/Subscribe-Papers/data/papers.db`
- Hermes paper catalog: `~/.hermes/data/papers/papers.db`
- Local LLM checkpoint:
  `/home/david/workspace/models/Qwen/Qwen3.6-35B-A3B-FP8`
- Local LLM endpoint: `http://localhost:8003/v1` (vLLM, 128K context)
- English lessons inbox: `~/english-lessons/`
