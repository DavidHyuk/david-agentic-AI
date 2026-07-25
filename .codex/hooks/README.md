# Codex hook

The project hook definition lives in `../hooks.json`, and its Codex-owned
implementation lives beside this file at `auto_git_commit.py`. Cursor delegates
to that implementation through `.cursor/hooks.json`; Codex never depends on a
Cursor-owned script.

After changing the hook definition or implementation, open `/hooks` in Codex
and review/trust the changed command before expecting it to run.

The hook prints its result and appends the same short diagnostic to
`.git/codex-auto-commit.log`, which is local Git metadata and can never be
staged. A failed push is retried on the next Stop event even when the worktree
has no new commit-worthy changes.

To run the exact hook manually:

```bash
python3 .codex/hooks/auto_git_commit.py </dev/null
```
