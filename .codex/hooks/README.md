# Codex hook

The project hook definition lives in `../hooks.json`. The implementation is
shared with the existing Cursor hook at `.cursor/hooks/auto_git_commit.py` so
both agent clients use the same safety filters and Conventional Commits logic.

After changing the hook definition or implementation, open `/hooks` in Codex
and review/trust the changed command before expecting it to run.

The hook prints its result and appends the same short diagnostic to
`.git/codex-auto-commit.log`, which is local Git metadata and can never be
staged. A failed push is retried on the next Stop event even when the worktree
has no new commit-worthy changes.

To run the exact hook manually:

```bash
python3 .cursor/hooks/auto_git_commit.py </dev/null
```
