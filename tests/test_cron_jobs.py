# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Validate cron/jobs.yaml and the register_cron command builder."""
from pathlib import Path

import pytest

import register_cron as rc

REPO = Path(__file__).resolve().parent.parent
JOBS = REPO / "cron" / "jobs.yaml"
EXPECTED_JOBS = {
    "papers-digest", "interview-prep", "english-intake", "english-drill",
    "weekly-review",
}


def test_jobs_yaml_loads_and_validates():
    jobs = rc.load_jobs(JOBS)
    names = {j["name"] for j in jobs}
    assert EXPECTED_JOBS <= names, f"missing expected jobs: {EXPECTED_JOBS - names}"


def test_defaults_applied_deliver_telegram():
    jobs = rc.load_jobs(JOBS)
    assert all(j["deliver"] == "telegram" for j in jobs)


def test_english_jobs_use_the_isolated_english_profile():
    jobs = {job["name"]: job for job in rc.load_jobs(JOBS)}
    assert jobs["english-intake"]["profile"] == "english"
    assert jobs["english-drill"]["profile"] == "english"
    assert "english-practice" not in jobs["weekly-review"]["skills"]


def test_calendar_brief_is_not_scheduled_while_integration_is_deferred():
    jobs = rc.load_jobs(JOBS)
    assert "morning-brief" not in {job["name"] for job in jobs}


def test_english_intake_coaches_without_feedback_and_reviews_on_sunday():
    jobs = {job["name"]: job for job in rc.load_jobs(JOBS)}
    prompt = jobs["english-intake"]["prompt"]
    assert "Do not stay silent" in prompt
    assert "weaknesses" in prompt
    assert "On Sunday" in prompt
    assert "[SILENT]" not in prompt


def test_build_create_command_shape():
    job = {
        "name": "papers-digest",
        "schedule": "30 8 * * 1-5",
        "prompt": "Send   my   digest",   # collapsed whitespace expected
        "skills": ["papers-digest"],
        "deliver": "whatsapp",
        "profile": "research",
    }
    cmd = rc.build_create_command(job)
    assert cmd[:3] == ["hermes", "cron", "create"]
    assert cmd[3] == "30 8 * * 1-5"
    assert "Send my digest" in cmd        # whitespace collapsed
    assert "--name" in cmd and "papers-digest" in cmd
    assert cmd[cmd.index("--skill") + 1] == "papers-digest"
    assert cmd[cmd.index("--deliver") + 1] == "whatsapp"
    assert cmd[cmd.index("--profile") + 1] == "research"


def test_missing_required_field_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("jobs:\n  - name: x\n    schedule: '* * * * *'\n")  # no prompt
    with pytest.raises(ValueError):
        rc.load_jobs(bad)


def test_duplicate_names_raise(tmp_path):
    bad = tmp_path / "dup.yaml"
    bad.write_text(
        "defaults: {deliver: whatsapp}\n"
        "jobs:\n"
        "  - {name: a, schedule: '* * * * *', prompt: p}\n"
        "  - {name: a, schedule: '* * * * *', prompt: q}\n"
    )
    with pytest.raises(ValueError):
        rc.load_jobs(bad)


def test_register_dry_run_smoke(capsys):
    jobs = rc.load_jobs(JOBS)
    rc.register(jobs, dry_run=True)
    out = capsys.readouterr().out
    assert "hermes cron create" in out
