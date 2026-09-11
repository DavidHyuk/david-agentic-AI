# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Validate cron/jobs.yaml and the register_cron command builder."""
from pathlib import Path

import pytest

import register_cron as rc

REPO = Path(__file__).resolve().parent.parent
JOBS = REPO / "cron" / "jobs.yaml"
EXPECTED_JOBS = {
    "papers-digest", "interview-prep", "english-intake", "english-drill",
    "english-weekly-review", "weekly-review",
}


def test_jobs_yaml_loads_and_validates():
    jobs = rc.load_jobs(JOBS)
    names = {j["name"] for j in jobs}
    assert EXPECTED_JOBS <= names, f"missing expected jobs: {EXPECTED_JOBS - names}"


def test_defaults_applied_deliver_telegram():
    jobs = rc.load_jobs(JOBS)
    assert all(j["deliver"] == "telegram" for j in jobs)


def test_papers_digest_uses_dedicated_telegram_chat_from_environment():
    jobs = {job["name"]: job for job in rc.load_jobs(JOBS)}
    papers = jobs["papers-digest"]
    assert papers["deliver_chat_id_env"] == "PAPERS_TELEGRAM_CHAT_ID"

    cmd = rc.build_create_command(
        papers,
        environment={"PAPERS_TELEGRAM_CHAT_ID": "-1001234567890"},
    )
    assert cmd[cmd.index("--deliver") + 1] == "telegram:-1001234567890"


def test_papers_digest_requires_valid_dedicated_chat_id():
    jobs = {job["name"]: job for job in rc.load_jobs(JOBS)}
    papers = jobs["papers-digest"]
    with pytest.raises(ValueError, match="requires PAPERS_TELEGRAM_CHAT_ID"):
        rc.build_create_command(papers, environment={})
    with pytest.raises(ValueError, match="numeric Telegram chat ID"):
        rc.build_create_command(
            papers,
            environment={"PAPERS_TELEGRAM_CHAT_ID": "papers-room"},
        )


def test_env_file_loader_supports_export_and_quotes(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# local routing\n"
        "export PAPERS_TELEGRAM_CHAT_ID='-1001234567890'\n"
        "INVALID LINE\n"
    )
    assert rc.load_env_file(env_file) == {
        "PAPERS_TELEGRAM_CHAT_ID": "-1001234567890"
    }


def test_english_jobs_use_the_isolated_english_profile():
    jobs = {job["name"]: job for job in rc.load_jobs(JOBS)}
    assert jobs["english-intake"]["profile"] == "english"
    assert jobs["english-drill"]["profile"] == "english"
    assert jobs["english-weekly-review"]["profile"] == "english"
    assert "english-practice" not in jobs["weekly-review"]["skills"]


def test_calendar_brief_is_not_scheduled_while_integration_is_deferred():
    jobs = rc.load_jobs(JOBS)
    assert "morning-brief" not in {job["name"] for job in jobs}


def test_english_intake_coaches_without_feedback_on_weekdays():
    jobs = {job["name"]: job for job in rc.load_jobs(JOBS)}
    prompt = jobs["english-intake"]["prompt"]
    assert "Do not stay silent" in prompt
    assert "weaknesses" in prompt
    assert jobs["english-intake"]["schedule"] == "0 20 * * 1-6"
    assert "[SILENT]" not in prompt


def test_english_weekly_review_is_a_dedicated_sunday_job():
    jobs = {job["name"]: job for job in rc.load_jobs(JOBS)}
    review = jobs["english-weekly-review"]
    assert review["schedule"] == "0 20 * * 0"
    assert "Procedure E" in review["prompt"]
    assert "standalone weekly review" in review["prompt"]


def test_english_drill_always_includes_inline_answers():
    jobs = {job["name"]: job for job in rc.load_jobs(JOBS)}
    prompt = jobs["english-drill"]["prompt"]
    assert "each answer immediately below" in prompt
    assert "Never send a drill without answers" in prompt
    assert "separate answer key" in prompt


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


def test_build_remove_command_targets_the_same_profile():
    assert rc.build_remove_command("english-drill", "english") == [
        "hermes", "-p", "english", "cron", "remove", "english-drill"
    ]
    assert rc.build_remove_command("papers-digest") == [
        "hermes", "cron", "remove", "papers-digest"
    ]


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
    rc.register(jobs, dry_run=True, environment={})
    out = capsys.readouterr().out
    assert "hermes cron create" in out
    assert "telegram:<PAPERS_TELEGRAM_CHAT_ID>" in out


def test_interview_coaches_fill_noon_without_replacing_mle_drills():
    jobs = {j['name']: j for j in rc.load_jobs(JOBS)}
    for name, schedule in {'interview-prep': '0 12 * * 1,3,5',
                           'coding-coach': '0 12 * * 2,4,6',
                           'system-design-coach': '0 12 * * 0'}.items():
        assert jobs[name]['schedule'] == schedule
        assert jobs[name]['skills'] == ['interview-prep']
        assert not jobs[name].get('profile')
        assert jobs[name]['deliver'] == 'telegram'
    assert 'interview_trends.py' in jobs['interview-prep']['prompt']
    assert jobs['papers-digest']['schedule'] == '30 8 * * *'
    assert jobs['english-drill']['schedule'] == '0 21 * * *'


def test_coach_cron_requires_material_canonical_links_and_real_feedback():
    jobs = {j['name']: j for j in rc.load_jobs(JOBS)}
    coding = jobs['coding-coach']['prompt']
    assert 'python3 ~/.hermes/scripts/interview_progress.py plan coding' in coding
    assert 'canonical NeetCode and LeetCode URLs' in coding
    assert '35-minute' in coding and '20 minutes without AI' in coding
    assert 'never a solution first' in coding
    assert 'until I report results' in coding
    design = jobs['system-design-coach']['prompt']
    assert 'plan system_design' in design and 'canonical Hello Interview URL' in design
    assert '45–60 minute' in design and '3–5' in design
    assert '45-minute mock' in design and 'Agent/Hermes' in design
    assert 'without my results' in design


def test_sunday_weekly_review_keeps_papers_and_adds_coach_metrics():
    jobs = {j['name']: j for j in rc.load_jobs(JOBS)}
    job = jobs['weekly-review']
    assert job['schedule'] == '0 18 * * 0'
    assert job['skills'] == ['papers-digest', 'interview-prep']
    for phrase in ('papers', 'interview_progress.py weekly', 'new vs review',
                   'weak patterns', 'solving time', 'hint usage', 'topics covered',
                   'weakest design dimension', "next week's recommended focus"):
        assert phrase in job['prompt']
