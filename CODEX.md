# Codex project workflow

Codex uses `.codex/hooks.json` for project lifecycle hooks. The Stop hook shares
its implementation with Cursor at `.cursor/hooks/auto_git_commit.py`.

## Automatic commit and push

At the end of a trusted Codex turn, the hook:

1. selects only allowlisted source, configuration, test, and documentation paths;
2. excludes secrets, runtime data, databases, model weights, and binary assets;
3. requires `pytest -q` to pass;
4. creates one Conventional Commit; and
5. pushes the current branch when it has an upstream.

Push failures remain fail-open for the agent turn but are printed, recorded in
`.git/codex-auto-commit.log`, and retried on the next Stop event.

After this file or either hook file changes, review and trust the command through
Codex `/hooks`. Until it is trusted, run the hook manually if a verified commit
and push is required:

```bash
python3 .cursor/hooks/auto_git_commit.py </dev/null
```

## Commit messages

Use:

```text
<type>(<optional scope>): <short imperative summary>
```

Allowed types are `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`,
and `perf`. Never add assistant branding or co-author trailers.
