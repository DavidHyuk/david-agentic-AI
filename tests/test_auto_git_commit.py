# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for the Cursor stop hook commit-message builder."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK_PATH = REPO / ".cursor" / "hooks" / "auto_git_commit.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("auto_git_commit", HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["auto_git_commit"] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()

V021_PATHS = [
    ".cursor/hooks.json",
    ".cursor/hooks/auto_git_commit.py",
    "config/config.fragment.yaml",
    "config/env.example",
    "docs/dev-history.md",
    "scripts/cron_health.py",
    "tests/test_auto_git_commit.py",
    "tests/test_cron_health.py",
]


def test_build_commit_message_mixed_source_and_tests_uses_productive_type():
    msg = hook.build_commit_message(V021_PATHS)
    assert msg.startswith("chore(cron):")
    assert "cursor" not in msg.lower()
    assert "created by" not in msg.lower()


def test_build_commit_message_cron_release_theme():
    msg = hook.build_commit_message(V021_PATHS)
    assert "harden scheduler" in msg
    assert "auto-commit hook" in msg


def test_build_commit_message_test_only_changes():
    msg = hook.build_commit_message(["tests/test_cron_health.py"])
    assert msg.startswith("test(")


def test_build_commit_message_docs_scope():
    msg = hook.build_commit_message(["docs/dev-history.md"])
    assert msg == "docs(docs): record dev history"


def test_should_skip_secrets():
    assert hook._should_skip(".env") is True
    assert hook._should_skip("config/.env.local") is True
    assert hook._should_skip("scripts/cron_health.py") is False
