# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for the shared agent stop hook commit-message builder."""
from __future__ import annotations

import importlib.util
import subprocess
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


def test_should_skip_unallowlisted_and_binary_paths():
    assert hook._should_skip("카카오톡 챗봇관리자.png") is True
    assert hook._should_skip(".git/config") is True
    assert hook._should_skip("browser/browser_smoke.py") is False
    assert hook._should_skip("mcp/calendar_smoke.py") is False
    assert hook._should_skip("README.md") is False
    assert hook._should_skip("AGENTS.md") is False
    assert hook._should_skip("CODEX.md") is False
    assert hook._should_skip(".codex/hooks.json") is False


def test_codex_hook_uses_stop_command():
    import json

    config = json.loads((REPO / ".codex" / "hooks.json").read_text())
    command = config["hooks"]["Stop"][0]["hooks"][0]
    assert command["type"] == "command"
    assert "auto_git_commit.py" in command["command"]
    assert "$(" not in command["command"]


def test_push_if_needed_retries_existing_local_commits(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(cmd, *, cwd):
        calls.append(cmd)
        if cmd[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(cmd, 0, "origin/main\n", "")
        if cmd[:2] == ["git", "rev-list"]:
            return subprocess.CompletedProcess(cmd, 0, "2\n", "")
        if cmd == ["git", "push"]:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        raise AssertionError(cmd)

    monkeypatch.setattr(hook, "_run", fake_run)
    ok, detail = hook._push_if_needed(tmp_path)

    assert ok is True
    assert detail == "pushed 2 commit(s)"
    assert ["git", "push"] in calls


def test_large_cross_cutting_change_uses_compact_release_message():
    paths = [
        "AGENTS.md",
        "README.md",
        "bootstrap/install.sh",
        "browser/browser_smoke.py",
        "config/config.fragment.yaml",
        "cron/jobs.yaml",
        "docs/dev-history.md",
        "local-model/run_model.sh",
        "mcp/calendar_smoke.py",
        "scripts/kakao_webhook.py",
    ]

    assert (
        hook.build_commit_message(paths)
        == "feat(agent): sync runtime integrations and automation"
    )


def test_record_result_writes_local_git_diagnostic(tmp_path, capsys):
    (tmp_path / ".git").mkdir()

    hook._record_result(tmp_path, False, "push failed")

    assert "error: push failed" in capsys.readouterr().err
    log = (tmp_path / ".git" / "codex-auto-commit.log").read_text()
    assert "error: push failed" in log
