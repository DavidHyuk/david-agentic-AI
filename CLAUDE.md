# Claude Project Guidelines

## Testing

When implementing a new feature, write unit tests that verify the feature behaves exactly as intended. Tests live in `tests/` and follow the existing pytest conventions in this repo. Tests must pass before the work is considered done.

## Version History

If a change constitutes a project version update, record it in `docs/dev-history.md`. Use semantic versioning:

- **Major** — breaking changes or significant architectural shifts
- **Minor** — new features or non-breaking capability additions
- **Patch** — bug fixes, small improvements, config/doc updates

Document what changed and why, not just that it changed.

## Commit Style

Commits follow the Conventional Commits format used in Silicon Valley teams:

```
<type>(<optional scope>): <short imperative summary>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`

Examples:
- `feat(skills): add papers-digest skill with SRS integration`
- `fix(gateway): resolve skill ambiguity caused by duplicate external_dirs`
- `refactor(stage): replace shutil.copy with symlinks for skills`

## Living Documentation

After any change that affects structure, capabilities, or usage, update the docs:

- **`docs/dev-history.md`** — every version bump (already required above).
- **`docs/project-overview.md`** — keep in sync with the current state whenever any of
  these change: directory structure, scripts list, test count, cron schedule table,
  skill capabilities, model/engine options, or "발전을 이끄는 핵심 기술" section.

The goal is that a reader of `project-overview.md` can understand the system *today*
without reading git history. If a change makes the doc stale, fix the doc in the same
commit.

## Maintainability

Write code for the next person, not just the current task:

- Prefer explicit over clever. A clear 10-line function beats a cryptic one-liner.
- Keep functions small and single-purpose.
- Name things by what they represent, not how they're implemented.
- Avoid deep nesting — flatten with early returns.
- Don't add abstraction until there are at least two concrete use cases for it.
