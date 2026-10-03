# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for transcript parsing and daily English podcast assignment state."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import pytest

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
    assert fake.calls[1][fake.calls[1].index('--sub-langs') + 1] == 'en-orig'

    repeated = podcast.prepare_daily(
        tmp_path,
        lesson_date="2026-09-13",
        runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()),
    )
    assert repeated["video_id"] == "video123"

    delivered = podcast.mark_delivered(tmp_path, "video123", "2026-09-13")
    assert delivered["delivered_at"]
    assert podcast.status(tmp_path)["delivered_count"] == 1


LONG_SENTENCE = ('Even though I felt nervous about speaking in front of my colleagues, '
                 'I decided to explain my idea clearly because I wanted to become more confident.')
SECOND_SENTENCE = ('When you give yourself enough time to prepare for a difficult conversation, '
                   'you can focus on what matters instead of worrying about every small mistake.')


def test_long_sentences_join_caption_cues_without_rewriting_and_keep_start_times():
    boundary = LONG_SENTENCE.index('I decided')
    cues = [{'text': 'A short introduction.', 'start_ms': 0},
            {'text': LONG_SENTENCE[:boundary], 'start_ms': 61000},
            {'text': LONG_SENTENCE[boundary:], 'start_ms': 62000},
            {'text': SECOND_SENTENCE, 'start_ms': 120000}]
    url = 'https://www.youtube.com/watch?v=abcdefghijk'
    result = podcast.select_long_sentences(cues, url)
    assert {item['source_quote'] for item in result} == {LONG_SENTENCE, SECOND_SENTENCE}
    first = next(item for item in result if item['source_quote'] == LONG_SENTENCE)
    assert first['timestamp'] == '01:01'
    assert first['url'] == url + '&t=61'
    assert {item['marker'] for item in first['patterns']} == {'even though', 'because'}


def test_no_punctuation_is_not_repaired_into_a_fabricated_complete_sentence():
    assert podcast.select_long_sentences([{'start_ms': 0, 'text': LONG_SENTENCE.rstrip('.')}], 'url') == []


def test_sentence_selection_deduplicates_and_limits_lengths_and_count():
    cues = [{'text': text, 'start_ms': index * 1000} for index, text in enumerate([
        LONG_SENTENCE, LONG_SENTENCE, SECOND_SENTENCE,
        ' '.join(['word'] * 46) + '.', 'Too short.',
        ' '.join(['word'] * 25) + '.',
    ])]
    result = podcast.select_long_sentences(cues, 'url')
    assert len(result) == 2
    assert {item['source_quote'] for item in result} == {LONG_SENTENCE, SECOND_SENTENCE}


def test_practice_omits_nonspoken_speaker_label_and_rejects_cross_speaker_sentence():
    cues = [{'text': '>> ' + LONG_SENTENCE, 'start_ms': 3000},
            {'text': SECOND_SENTENCE.replace('you can', '>> you can'), 'start_ms': 4000}]
    result = podcast.select_long_sentences(cues, 'https://www.youtube.com/watch?v=abcdefghijk')
    assert len(result) == 1
    assert result[0]['source_quote'] == LONG_SENTENCE
    assert result[0]['word_count'] == len(LONG_SENTENCE.split())
    assert result[0]['timestamp'] == '00:03'


def watched_history(path, *, lesson_date='2026-10-03', video_id='abcdefghijk'):
    path.write_text(json.dumps({'date': lesson_date, 'selection': 'latest', 'videos': [{
        'video_id': video_id, 'url': 'https://www.youtube.com/watch?v=' + video_id,
        'title': 'My watched episode', 'channel': 'Daily English Podcast',
    }]}))


def watched_caption_runner(command, **kwargs):
    assert '--flat-playlist' not in command
    assert command[-1] == 'https://www.youtube.com/watch?v=abcdefghijk'
    directory = Path(command[command.index('--output') + 1]).parent
    (directory / 'abcdefghijk.en.json3').write_text(json.dumps({'events': [
        {'tStartMs': 61000, 'segs': [{'utf8': LONG_SENTENCE}]},
        {'tStartMs': 120000, 'segs': [{'utf8': SECOND_SENTENCE}]},
    ]}))
    (directory / 'abcdefghijk.info.json').write_text(json.dumps({
        'id': 'abcdefghijk', 'channel_id': 'another-channel', 'channel': 'Daily English Podcast',
        'automatic_captions': {'en': [{}]},
    }))
    return subprocess.CompletedProcess(command, 0, '', '')


def test_watched_practice_downloads_exact_video_from_other_channel_and_reuses_captions(tmp_path):
    history_path = tmp_path / 'history.json'
    watched_history(history_path)
    root = tmp_path / 'watched'
    result = podcast.prepare_watched_practice(root, history_path, lesson_date='2026-10-03',
                                              runner=watched_caption_runner)
    assert result['status'] == 'ready'
    assert result['video_id'] == 'abcdefghijk'
    assert result['caption_kind'] == 'automatic'
    assert len(result['sentences']) == 2
    assert not (root / 'state.json').exists()
    assert json.loads((root / 'practice.json').read_text()) == result
    assert (root / 'practice/2026-10-03.json').exists()
    def no_download(*args, **kwargs):
        pytest.fail('Verified captions should be reused for the same video.')
    repeated = podcast.prepare_watched_practice(root, history_path, lesson_date='2026-10-03', runner=no_download)
    assert repeated == result


@pytest.mark.parametrize('failure', [RuntimeError('private-secret'), subprocess.TimeoutExpired('secret-command', 180)])
def test_watched_caption_failure_is_safe_and_does_not_reuse_prior_practice(tmp_path, failure):
    history_path = tmp_path / 'history.json'
    watched_history(history_path)
    root = tmp_path / 'watched'
    root.mkdir()
    (root / 'practice.json').write_text('{"sentences":[{"source_quote":"old unrelated text"}]}')
    def unavailable(*args, **kwargs):
        raise failure
    result = podcast.prepare_watched_practice(root, history_path, lesson_date='2026-10-03', runner=unavailable)
    assert result['status'] == 'unavailable'
    assert result['sentences'] == []
    assert 'secret' not in json.dumps(result)
    assert 'old unrelated text' not in (root / 'practice.json').read_text()


@pytest.mark.parametrize('change', ['old_date', 'invalid_url', 'multiple_videos'])
def test_practice_rejects_stale_or_invalid_history_before_any_network_call(tmp_path, change):
    history_path = tmp_path / 'history.json'
    watched_history(history_path)
    history = json.loads(history_path.read_text())
    if change == 'old_date':
        history['date'] = '2000-01-01'
    elif change == 'invalid_url':
        history['videos'][0]['url'] = 'https://evil.example/watch?v=abcdefghijk'
    else:
        history['videos'].append(history['videos'][0])
    history_path.write_text(json.dumps(history))
    with pytest.raises(ValueError):
        podcast.prepare_watched_practice(tmp_path / 'practice', history_path, lesson_date='2026-10-03',
                                        runner=lambda *a, **kw: pytest.fail('Must not fetch unverified video.'))


def test_wrong_downloaded_video_never_becomes_a_source_quote(tmp_path):
    history_path = tmp_path / 'history.json'
    watched_history(history_path)
    def wrong_video(command, **kwargs):
        result = watched_caption_runner(command, **kwargs)
        directory = Path(command[command.index('--output') + 1]).parent
        (directory / 'abcdefghijk.info.json').write_text('{"id":"bbbbbbbbbbb"}')
        return result
    result = podcast.prepare_watched_practice(tmp_path / 'practice', history_path,
                                              lesson_date='2026-10-03', runner=wrong_video)
    assert result['status'] == 'unavailable'
    assert result['sentences'] == []


def test_practice_cli_uses_explicit_source_and_safe_failure_output(tmp_path, monkeypatch, capsys):
    history_path = tmp_path / 'missing-history.json'
    assert podcast.main(['--date', '2026-10-03', 'practice', '--history-file', str(history_path),
                         '--practice-dir', str(tmp_path / 'practice')]) == 1
    output = capsys.readouterr()
    assert output.out == ''
    assert 'missing-history.json' not in output.err
    assert '이전 연습 자료는 전달하지 않습니다' in output.err


def test_shorter_weakness_candidates_are_source_sentences_within_practice_length():
    quote = 'I have been practicing English every morning because I want to feel more comfortable in meetings.'
    candidates = podcast.select_caption_sentences([{'start_ms': 1000, 'text': quote}],
                                                 'url', min_words=8, max_words=25, limit=12)
    assert candidates[0]['source_quote'] == quote
    assert 8 <= candidates[0]['word_count'] <= 25


@pytest.mark.parametrize('lesson_date', ['2026-10-03', '2026-10-04'])
def test_weekend_review_uses_weekdays_of_current_week_and_merges_repeat_videos(tmp_path, lesson_date):
    directory = tmp_path / 'practice'
    directory.mkdir()
    for source_date in ('2026-09-25', '2026-09-28', '2026-09-29', '2026-10-02', '2026-10-03'):
        video_id = 'bbbbbbbbbbb' if source_date in ('2026-09-25', '2026-10-03') else 'abcdefghijk'
        (directory / f'{source_date}.json').write_text(json.dumps({
            'lesson_date': source_date, 'video_id': video_id,
            'url': 'https://www.youtube.com/watch?v=' + video_id,
            'status': 'ready', 'sentences': [{'source_quote': LONG_SENTENCE}],
        }))
    result = podcast.prepare_weekend_review(tmp_path, lesson_date=lesson_date)
    assert result['week_start'] == '2026-09-28'
    assert result['week_end'] == '2026-10-02'
    assert result['status'] == 'ready'
    assert len(result['episodes']) == 1
    assert result['episodes'][0]['source_dates'] == ['2026-09-28', '2026-09-29', '2026-10-02']
    assert result['episodes'][0]['sentences'][0]['source_quote'] == LONG_SENTENCE


def test_weekend_review_missing_or_failed_sources_does_not_fall_back_to_old_practice(tmp_path):
    (tmp_path / 'practice').mkdir()
    (tmp_path / 'practice/2026-09-28.json').write_text('malformed')
    (tmp_path / 'practice/2026-09-29.json').write_text(json.dumps({
        'lesson_date': '2026-09-29', 'video_id': 'abcdefghijk', 'status': 'unavailable',
        'url': 'https://www.youtube.com/watch?v=abcdefghijk', 'sentences': [{'source_quote': 'old'}],
    }))
    (tmp_path / 'practice.json').write_text('{"sentences":[{"source_quote":"old"}]}')
    result = podcast.prepare_weekend_review(tmp_path, lesson_date='2026-10-03')
    assert result['status'] == 'unavailable'
    assert result['episodes'] == []


def test_caption_download_requests_en_only_when_original_track_is_absent(tmp_path):
    languages = []
    def runner(command, **kwargs):
        language = command[command.index('--sub-langs') + 1]
        languages.append(language)
        if language == 'en-orig':
            return subprocess.CompletedProcess(command, 0, '', '')
        return watched_caption_runner(command, **kwargs)
    manifest = podcast.download_transcript({'id': 'abcdefghijk', 'url': 'https://www.youtube.com/watch?v=abcdefghijk'},
                                           tmp_path, runner=runner, expected_channel_id=None)
    assert languages == ['en-orig', 'en']
    assert manifest['caption_language'] == 'en'
