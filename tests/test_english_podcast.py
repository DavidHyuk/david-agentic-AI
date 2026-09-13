# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for transcript parsing and daily English podcast assignment state."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import english_podcast as podcast


def test_json3_cues_normalize_segments_and_keep_timestamps() -> None:
    cues = podcast.json3_cues(
        {
            "events": [
                {"tStartMs": 1250, "segs": [{"utf8": "Try"}, {"utf8": " again."}]},
                {"tStartMs": 2500, "segs": [{"utf8": "\n"}]},
                {"tStartMs": 61000, "segs": [{"utf8": "  Keep   going "}]},
            ]
        }
    )
    assert cues == [
        {"start_ms": 1250, "duration_ms": 0, "text": "Try again."},
        {"start_ms": 61000, "duration_ms": 0, "text": "Keep going"},
    ]
    assert podcast.timestamp(61000) == "01:01"


def test_select_unassigned_preserves_newest_first_channel_order() -> None:
    entries = [{"id": "new"}, {"id": "used"}, {"id": "older"}]
    state = {
        "assignments": {
            "2026-09-12": {"video_id": "used"},
        }
    }
    assert [item["id"] for item in podcast.select_unassigned(entries, state)] == [
        "new",
        "older",
    ]


def test_channel_listing_rejects_a_similarly_named_wrong_channel() -> None:
    def fake_run(command, **_kwargs):
        document = {"channel_id": "wrong", "entries": [{"id": "video123"}]}
        return subprocess.CompletedProcess(command, 0, json.dumps(document), "")

    try:
        podcast.fetch_channel_entries(podcast.DEFAULT_CHANNEL_URL, runner=fake_run)
    except RuntimeError as exc:
        assert podcast.EXPECTED_CHANNEL_ID in str(exc)
    else:
        raise AssertionError("wrong channel identity was accepted")


class FakeYtDlp:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, command, **_kwargs):
        self.calls.append(command)
        if "--flat-playlist" in command:
            document = {
                "channel_id": "UC8oq85HHmW3BDhYWc1YcsIA",
                "entries": [
                    {
                        "id": "video123",
                        "title": "One More Time",
                        "duration": 180,
                    }
                ]
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(document), "")

        template = Path(command[command.index("--output") + 1])
        directory = template.parent
        directory.mkdir(parents=True, exist_ok=True)
        events = [
            {
                "tStartMs": index * 1000,
                "dDurationMs": 1000,
                "segs": [{"utf8": f"useful phrase number {index}"}],
            }
            for index in range(20)
        ]
        (directory / "video123.en-orig.json3").write_text(
            json.dumps({"events": events}), encoding="utf-8"
        )
        (directory / "video123.info.json").write_text(
            json.dumps(
                {
                    "id": "video123",
                    "title": "One More Time",
                    "webpage_url": "https://www.youtube.com/watch?v=video123",
                    "channel": "English Goal Podcast",
                    "channel_id": "UC8oq85HHmW3BDhYWc1YcsIA",
                    "duration": 180,
                    "upload_date": "20260910",
                    "automatic_captions": {"en-orig": [{}]},
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")


def test_prepare_downloads_transcript_and_is_idempotent_per_day(tmp_path: Path) -> None:
    fake = FakeYtDlp()
    manifest = podcast.prepare_daily(
        tmp_path,
        lesson_date="2026-09-13",
        runner=fake,
    )
    transcript = Path(manifest["transcript_path"])
    caption = Path(manifest["caption_path"])
    assert transcript.is_file()
    assert caption.is_file()
    assert "[00:00] useful phrase number 0" in transcript.read_text()
    assert manifest["word_count"] == 80
    assert len(fake.calls) == 2

    repeated = podcast.prepare_daily(
        tmp_path,
        lesson_date="2026-09-13",
        runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()),
    )
    assert repeated["video_id"] == "video123"

    delivered = podcast.mark_delivered(tmp_path, "video123", "2026-09-13")
    assert delivered["delivered_at"]
    assert podcast.status(tmp_path)["delivered_count"] == 1
