# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for english_intake.py session grouping + processed-state tracking."""
import english_intake as ei


def test_parse_date_from_name():
    assert ei.parse_date_from_name("lesson_2026-06-01.mp3") == "2026-06-01"
    assert ei.parse_date_from_name("20260601_corrections.txt") == "2026-06-01"
    assert ei.parse_date_from_name("no-date-here.mp3") is None


def test_scan_groups_by_subfolder(tmp_path):
    d = tmp_path / "2026-06-01"
    d.mkdir()
    (d / "rec.mp3").write_bytes(b"x")
    (d / "corrections.txt").write_text("you said X -> better Y")
    sessions = ei.scan_sessions(str(tmp_path))
    assert len(sessions) == 1
    s = sessions[0]
    assert s["session_id"] == "2026-06-01"
    assert len(s["audio"]) == 1 and len(s["corrections"]) == 1


def test_scan_groups_flat_files_by_filename_date(tmp_path):
    (tmp_path / "lesson_2026-06-02.m4a").write_bytes(b"x")
    (tmp_path / "lesson_2026-06-02.md").write_text("note")
    (tmp_path / "lesson_2026-06-03.wav").write_bytes(b"x")
    sessions = ei.scan_sessions(str(tmp_path))
    ids = sorted(s["session_id"] for s in sessions)
    assert ids == ["2026-06-02", "2026-06-03"]


def test_ignores_unrecognized_files(tmp_path):
    (tmp_path / "thumb.png").write_bytes(b"x")
    assert ei.scan_sessions(str(tmp_path)) == []


def test_new_sessions_and_marking(tmp_path):
    (tmp_path / "lesson_2026-06-02.m4a").write_bytes(b"x")
    sessions = ei.scan_sessions(str(tmp_path))
    state = {"processed": []}
    assert len(ei.new_sessions(sessions, state)) == 1
    state = ei.mark_processed(state, sessions)
    assert ei.new_sessions(sessions, state) == []


def test_state_roundtrip(tmp_path):
    state_path = tmp_path / "state.json"
    ei.save_state(str(state_path), {"processed": ["2026-06-02"]})
    loaded = ei.load_state(str(state_path))
    assert loaded["processed"] == ["2026-06-02"]


def test_missing_dir_returns_empty(tmp_path):
    assert ei.scan_sessions(str(tmp_path / "nope")) == []


def test_save_from_telegram_copies_file(tmp_path):
    src = tmp_path / "rec.mp4"
    src.write_bytes(b"video")
    lessons_dir = tmp_path / "lessons"
    dest = ei.save_from_telegram(str(src), str(lessons_dir))
    assert dest.endswith("rec.mp4")
    assert open(dest, "rb").read() == b"video"
    # saved under a YYYY-MM-DD subfolder
    import re, os
    assert re.match(r"\d{4}-\d{2}-\d{2}", os.path.basename(os.path.dirname(dest)))
