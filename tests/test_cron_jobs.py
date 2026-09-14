# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Validate cron/jobs.yaml and the register_cron command builder."""
from pathlib import Path

import pytest

import register_cron as rc

REPO = Path(__file__).resolve().parent.parent
JOBS = REPO / "cron" / "jobs.yaml"
EXPECTED_JOBS = {
    "papers-digest", "interview-prep", "english-intake", "english-drill",
    "english-weekly-review", "english-podcast-daily", "weekly-review",
    "leetcode-history-sync",
}


def test_jobs_yaml_loads_and_validates():
    jobs = rc.load_jobs(JOBS)
    names = {j["name"] for j in jobs}
    assert EXPECTED_JOBS <= names, f"missing expected jobs: {EXPECTED_JOBS - names}"


def test_defaults_applied_deliver_telegram():
    jobs = rc.load_jobs(JOBS)
    assert all(j["deliver"] == "telegram" for j in jobs if j["name"] != "leetcode-history-sync")
    assert next(j for j in jobs if j["name"] == "leetcode-history-sync")["deliver"] is None


def test_leetcode_history_sync_is_read_only_and_has_no_delivery():
    jobs = {job["name"]: job for job in rc.load_jobs(JOBS)}
    sync = jobs["leetcode-history-sync"]
    assert sync["schedule"] == "15 */4 * * *"
    assert "leetcode_sync.py sync" in sync["prompt"]
    assert "read-only" in sync["prompt"]
    assert "--deliver" not in rc.build_create_command(sync, environment={})


def test_papers_digest_uses_dedicated_telegram_chat_from_environment():
    jobs = {job["name"]: job for job in rc.load_jobs(JOBS)}
    papers = jobs["papers-digest"]
    assert papers["deliver_chat_id_env"] == "PAPERS_TELEGRAM_CHAT_ID"

    cmd = rc.build_create_command(
        papers,
        environment={"PAPERS_TELEGRAM_CHAT_ID": "-1001234567890"},
    )
    assert cmd[cmd.index("--deliver") + 1] == "telegram:-1001234567890"


def test_papers_digest_runs_twice_weekly_and_selects_three():
    jobs = {job["name"]: job for job in rc.load_jobs(JOBS)}
    papers = jobs["papers-digest"]
    assert papers["schedule"] == "30 8 * * 2,5"
    assert "exactly the three hottest high-signal papers" in papers["prompt"]


def test_interview_system_design_and_leetcode_use_separate_topic_chats():
    jobs = {job["name"]: job for job in rc.load_jobs(JOBS)}
    assert jobs["interview-prep"]["deliver_chat_id_env"] == (
        "INTERVIEW_TELEGRAM_CHAT_ID"
    )
    assert jobs["system-design-coach"]["deliver_chat_id_env"] == (
        "SYSTEM_DESIGN_TELEGRAM_CHAT_ID"
    )
    assert jobs["coding-coach"]["deliver_chat_id_env"] == (
        "LEETCODE_TELEGRAM_CHAT_ID"
    )
    assert "deliver_chat_id_env" not in jobs["weekly-review"]

    environment = {
        "INTERVIEW_TELEGRAM_CHAT_ID": "-1001111111111",
        "LEETCODE_TELEGRAM_CHAT_ID": "-1002222222222",
        "SYSTEM_DESIGN_TELEGRAM_CHAT_ID": "-1003333333333",
    }
    interview_cmd = rc.build_create_command(
        jobs["interview-prep"], environment=environment
    )
    design_cmd = rc.build_create_command(
        jobs["system-design-coach"], environment=environment
    )
    coding_cmd = rc.build_create_command(
        jobs["coding-coach"], environment=environment
    )
    assert interview_cmd[interview_cmd.index("--deliver") + 1] == (
        "telegram:-1001111111111"
    )
    assert design_cmd[design_cmd.index("--deliver") + 1] == (
        "telegram:-1003333333333"
    )
    assert coding_cmd[coding_cmd.index("--deliver") + 1] == (
        "telegram:-1002222222222"
    )


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


def test_english_podcast_job_is_daily_at_nine_in_existing_english_profile():
    jobs = {job["name"]: job for job in rc.load_jobs(JOBS)}
    podcast = jobs["english-podcast-daily"]
    assert podcast["schedule"] == "0 9 * * *"
    assert podcast["profile"] == "english"
    assert podcast["deliver_chat_id_env"] == "ENGLISH_PODCAST_TELEGRAM_CHAT_ID"
    assert podcast["skills"] == ["english-podcast-coach"]
    assert "transcript_path" in podcast["prompt"]
    assert "exactly three short" in podcast["prompt"]

    command = rc.build_create_command(
        podcast, environment={"ENGLISH_PODCAST_TELEGRAM_CHAT_ID": "-1001234567894"}
    )
    assert command[command.index("--deliver") + 1] == "telegram:-1001234567894"


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


def test_build_edit_command_preserves_the_existing_job_id():
    job = {
        "name": "papers-digest",
        "schedule": "30 8 * * 2,5",
        "prompt": "Send  my digest",
        "skills": ["papers-digest"],
        "deliver": "telegram",
    }
    command = rc.build_edit_command("job-123", job)
    assert command[:4] == ["hermes", "cron", "edit", "job-123"]
    assert command[command.index("--prompt") + 1] == "Send my digest"
    assert command[command.index("--skill") + 1] == "papers-digest"


def test_register_keeps_an_unchanged_job_and_its_runtime_state(tmp_path, monkeypatch, capsys):
    job = {
        "name": "papers-digest",
        "schedule": "30 8 * * 2,5",
        "prompt": "Send my digest",
        "skills": ["papers-digest"],
        "deliver": "telegram",
    }
    jobs_path = tmp_path / "cron" / "jobs.json"
    jobs_path.parent.mkdir()
    jobs_path.write_text(
        '{"jobs": [{"id": "existing", "name": "papers-digest", '
        '"schedule": {"expr": "30 8 * * 2,5"}, "prompt": "Send my digest", '
        '"skills": ["papers-digest"], "deliver": "telegram", '
        '"last_run_at": "2026-09-13T08:30:00-07:00"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(rc.shutil, "which", lambda _name: "/usr/bin/hermes")
    monkeypatch.setattr(
        rc.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("unchanged job must not be recreated"),
    )

    rc.register([job], environment={}, hermes_home=tmp_path)

    assert "papers-digest: unchanged" in capsys.readouterr().out


def test_register_edits_changed_job_in_place(tmp_path, monkeypatch):
    job = {
        "name": "papers-digest",
        "schedule": "30 8 * * 2,5",
        "prompt": "Send updated digest",
        "skills": ["papers-digest"],
        "deliver": "telegram",
    }
    jobs_path = tmp_path / "cron" / "jobs.json"
    jobs_path.parent.mkdir()
    jobs_path.write_text(
        '{"jobs": [{"id": "existing", "name": "papers-digest", '
        '"schedule": {"expr": "30 8 * * 2,5"}, "prompt": "Old digest", '
        '"skills": ["papers-digest"], "deliver": "telegram"}]}',
        encoding="utf-8",
    )
    commands = []
    monkeypatch.setattr(rc.shutil, "which", lambda _name: "/usr/bin/hermes")
    monkeypatch.setattr(
        rc.subprocess,
        "run",
        lambda command, **_kwargs: (commands.append(command) or type("Result", (), {"returncode": 0, "stderr": ""})()),
    )

    rc.register([job], environment={}, hermes_home=tmp_path)

    assert commands[0][:4] == ["hermes", "cron", "edit", "existing"]


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
    assert "telegram:<INTERVIEW_TELEGRAM_CHAT_ID>" in out
    assert "telegram:<LEETCODE_TELEGRAM_CHAT_ID>" in out
    assert "telegram:<SYSTEM_DESIGN_TELEGRAM_CHAT_ID>" in out


def test_main_can_register_one_named_job(monkeypatch, capsys):
    captured = []
    monkeypatch.setattr(rc, "register", lambda jobs, dry_run=False: captured.extend(jobs))
    assert rc.main(["--jobs", str(JOBS), "--name", "english-podcast-daily"]) == 0
    assert [job["name"] for job in captured] == ["english-podcast-daily"]
    assert "Loaded 1 cron jobs" in capsys.readouterr().out


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
    assert jobs['papers-digest']['schedule'] == '30 8 * * 2,5'
    assert jobs['english-drill']['schedule'] == '0 21 * * *'


def test_coach_cron_requires_material_canonical_links_and_real_feedback():
    jobs = {j['name']: j for j in rc.load_jobs(JOBS)}
    coding = jobs['coding-coach']['prompt']
    assert 'leetcode_sync.py sync' in coding
    assert 'history snapshot' in coding
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
