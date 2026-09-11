# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Verify repository-owned specialist profiles are isolated and reproducible."""

from pathlib import Path

import yaml

import stage_specialist_profiles


def test_stage_specialists_assigns_identity_and_only_role_skills(tmp_path: Path):
    root = tmp_path / "profiles"
    results = stage_specialist_profiles.stage_all(root)
    assert [item["name"] for item in results] == [
        "papers", "interview", "coding", "design",
    ]
    papers = root / "papers"
    assert "research specialist" in (papers / "SOUL.md").read_text()
    assert (papers / "skills/research/papers-digest/SKILL.md").is_file()
    assert not (papers / "skills/career/interview-prep").exists()
    assert (root / "coding/skills/career/interview-prep/SKILL.md").is_file()
    metadata = yaml.safe_load((root / "design/profile.yaml").read_text())
    assert "system design" in metadata["description"].lower()
    config = yaml.safe_load((root / "interview/config.yaml").read_text())
    assert config["kanban"]["max_in_progress"] == 1
    assert (root / "coding/.no-bundled-skills").is_file()


def test_stage_specialist_preserves_existing_env_and_memory(tmp_path: Path):
    root = tmp_path / "profiles"
    papers = root / "papers"
    (papers / "memories").mkdir(parents=True)
    (papers / ".env").write_text("PRIVATE_SETTING=kept\n")
    (papers / "memories/USER.md").write_text("curated")
    stale = papers / "skills/stale/example"
    stale.mkdir(parents=True)
    (stale / "SKILL.md").write_text("stale")
    stage_specialist_profiles.stage_all(root)
    environment = (papers / ".env").read_text()
    assert "PRIVATE_SETTING=kept" in environment
    assert environment.count("OPENAI_API_KEY=") == 1
    assert (papers / "memories/USER.md").read_text() == "curated"
    assert not stale.exists()
