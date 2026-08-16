# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Validate that every SKILL.md has well-formed agentskills.io-style frontmatter."""
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
SKILLS = sorted(
    list((REPO / "skills").rglob("SKILL.md"))
    + list((REPO / "profiles").rglob("SKILL.md"))
)
EXPECTED = {
    "papers-digest",
    "interview-prep",
    "english-practice",
    "calendar-assistant",
}


def _frontmatter(text: str) -> dict:
    assert text.startswith("---"), "frontmatter must start with ---"
    _, fm, _ = text.split("---", 2)
    return yaml.safe_load(fm)


def test_all_expected_skills_present():
    names = {_frontmatter(p.read_text())["name"] for p in SKILLS}
    assert EXPECTED <= names, f"missing skills: {EXPECTED - names}"
    assert not (REPO / "skills" / "learning" / "english-practice" / "SKILL.md").exists()
    assert (
        REPO
        / "profiles"
        / "english"
        / "skills"
        / "learning"
        / "english-practice"
        / "SKILL.md"
    ).exists()


def test_each_skill_has_required_fields():
    for p in SKILLS:
        fm = _frontmatter(p.read_text())
        assert fm.get("name"), f"{p}: missing name"
        assert fm.get("description"), f"{p}: missing description"
        assert fm.get("version"), f"{p}: missing version"
        hermes = (fm.get("metadata") or {}).get("hermes") or {}
        assert hermes.get("category"), f"{p}: missing metadata.hermes.category"
        assert isinstance(hermes.get("tags"), list), f"{p}: tags must be a list"


def test_skill_dir_name_matches_frontmatter_name():
    for p in SKILLS:
        fm = _frontmatter(p.read_text())
        assert p.parent.name == fm["name"], f"{p}: dir != name"


def test_skill_body_has_core_sections():
    for p in SKILLS:
        body = p.read_text()
        for section in ("## When to Use", "## Procedure"):
            assert section in body, f"{p}: missing '{section}'"


def test_english_drill_requires_inline_answers():
    path = (
        REPO
        / "profiles"
        / "english"
        / "skills"
        / "learning"
        / "english-practice"
        / "SKILL.md"
    )
    body = path.read_text()
    assert "immediately followed by its answer" in body
    assert "Do not collect all answers in a separate answer key" in body
