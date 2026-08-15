# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for bootstrap/stage.py staging into a throwaway HERMES_HOME."""
from pathlib import Path

import stage


def test_deep_merge():
    base = {"model": {"provider": "x", "ctx": 1}, "keep": True}
    overlay = {"model": {"provider": "y"}, "new": 1}
    merged = stage.deep_merge(base, overlay)
    assert merged == {"model": {"provider": "y", "ctx": 1}, "keep": True, "new": 1}


def test_stage_all_populates_home(tmp_path):
    home = tmp_path / "hermes"
    report = stage.stage_all(home)
    # SOUL + memory + skills + scripts + config land where Hermes expects them.
    assert (home / "SOUL.md").exists()
    assert (home / "memories" / "USER.md").exists()
    assert (home / "memories" / "MEMORY.md").exists()
    assert (home / "skills" / "research" / "papers-digest" / "SKILL.md").exists()
    assert (home / "skills" / "personal" / "family-letter" / "SKILL.md").exists()
    assert (home / "scripts" / "papers_digest.py").exists()
    assert (home / "scripts" / "papers_ingest.py").exists()
    assert (home / "data" / "papers").is_dir()
    assert (home / "config.yaml").exists()
    assert report["config_merged"] is True
    assert "research/papers-digest" in report["skills"]
    assert "personal/family-letter" in report["skills"]


def test_config_merge_preserves_existing(tmp_path):
    home = tmp_path / "hermes"
    home.mkdir()
    (home / "config.yaml").write_text("existing_key: 123\nmodel:\n  foo: bar\n")
    stage.stage_config(home)
    import yaml
    cfg = yaml.safe_load((home / "config.yaml").read_text())
    assert cfg["existing_key"] == 123                              # preserved
    assert cfg["model"]["provider"] == "custom:qwen36-fp8-hermes"  # merged from fragment
    assert cfg["model"]["foo"] == "bar"                            # preserved alongside merge
    assert "qwen36-fp8-hermes" in cfg["providers"]
    provider = cfg["providers"]["qwen36-fp8-hermes"]
    assert provider["base_url"] == "http://localhost:8003/v1"
    assert provider["model"] == "Qwen3.6-35B-A3B-FP8"
    assert provider["context_length"] == 131072
    eb = provider["extra_body"]
    assert eb["presence_penalty"] == 1.5
    assert eb["repetition_penalty"] == 1.0
    assert cfg["browser"] == {
        "cloud_provider": "local",
        "engine": "chrome",
        "cdp_url": "http://127.0.0.1:19222",
        "command_timeout": 30,
    }
    assert cfg["skills"]["disabled"] == ["calendar-assistant"]


def test_memory_not_clobbered_when_present(tmp_path):
    home = tmp_path / "hermes"
    (home / "memories").mkdir(parents=True)
    (home / "memories" / "USER.md").write_text("AGENT-CURATED FACTS")
    staged = stage.stage_memory(home)
    assert "USER.md" not in staged  # skipped because non-empty
    assert (home / "memories" / "USER.md").read_text() == "AGENT-CURATED FACTS"


def test_force_memory_overwrites_with_backup(tmp_path):
    home = tmp_path / "hermes"
    (home / "memories").mkdir(parents=True)
    (home / "memories" / "USER.md").write_text("OLD")
    staged = stage.stage_memory(home, force=True)
    assert "USER.md" in staged
    assert (home / "memories" / "USER.md").read_text() != "OLD"
    backups = list((home / "memories").glob("USER.md.bak-*"))
    assert backups, "expected a backup of the overwritten memory file"


def test_idempotent_rerun(tmp_path):
    home = tmp_path / "hermes"
    stage.stage_all(home)
    # second run should not raise and skills dir should still be intact
    stage.stage_all(home)
    assert (home / "skills" / "career" / "interview-prep" / "SKILL.md").exists()
    # supporting reference files copied too
    assert (home / "skills" / "career" / "interview-prep" / "references" / "curriculum.md").exists()
