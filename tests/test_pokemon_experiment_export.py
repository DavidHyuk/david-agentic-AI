# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Verify complete card imports, private exports, label denominators and timing honesty."""
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "local-model/eval/experiment_tracker.py"
spec = importlib.util.spec_from_file_location("pokemon_tracker", SCRIPT)
tracker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tracker)


def fixture_run(tmp_path):
    inputs = [{"filename": "PRIVATE-PHOTO-a.jpg", "source_sha256": "a" * 64},
              {"filename": "PRIVATE-PHOTO-b.jpg", "source_sha256": "b" * 64}]
    metadata = {"status": "completed", "input_errors": [], "inputs": inputs,
        "resolutions": ["0.3MP", "2MP"], "model": "test-model",
        "prompt": "PRIVATE PROMPT", "parameters": {"temperature": 0, "max_tokens": 256},
        "preprocessing": "EXIF full Lanczos no upscale", "created_utc": "2026-10-11T06:00:00+00:00",
        "finished_utc": "2026-10-11T06:05:00+00:00"}
    rows = []
    for source in inputs:
        for resolution in metadata["resolutions"]:
            rows.append({**source, "resolution": resolution, "width": 474, "height": 632,
                "pixels": 299568, "actual_mp": .299568, "capped_by_original": False,
                "http_status": 200, "latency_seconds": 3.5, "api_error": False,
                "parse_error": False, "image_error": False,
                "raw_model_response": "PRIVATE COMPLETION", "raw_api_response": "PRIVATE API IMAGE BASE64",
                "image_path": "/PRIVATE/PATH.png", "pokemon_name": "PRIVATE NAME",
                "pokemon_type": "unknown", "hp": "100", "card_number": "001/100",
                **{field + "_correct": None for field in tracker.POKEMON_FIELDS}})
    for name, data in [("metadata.json", metadata), ("results.json", rows),
                       ("ground_truth.snapshot.json", {})]:
        (tmp_path / name).write_text(json.dumps(data))
    return metadata, rows


def rewrite(tmp_path, name, data):
    (tmp_path / name).write_text(json.dumps(data))


def test_resolution_groups_share_items_and_export_no_card_content(tmp_path):
    fixture_run(tmp_path)
    runs = tracker.import_pokemon(tmp_path, gpu_clock_min=300, gpu_clock_max=2200)
    assert len(runs) == 2 and all(len(run["records"]) == 2 for run in runs)
    assert runs[0]["dataset_digest"] == runs[1]["dataset_digest"]
    assert [r["id"] for r in runs[0]["records"]] == [r["id"] for r in runs[1]["records"]]
    assert runs[0]["run_id"] != runs[1]["run_id"]
    payload = tracker.langfuse_payload(runs)
    exported = json.dumps(payload)
    assert "PRIVATE" not in exported
    spans = payload["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert len({span["traceId"] for span in spans}) == 4
    assert all(span["startTimeUnixNano"] == span["endTimeUnixNano"] for span in spans)
    assert "completion_start_time" not in exported
    assert "gpu_clock_max_mhz_reported" in exported and "resolution" in exported
    scores = tracker.langfuse_scores(runs, payload)
    assert not any(event["body"]["name"].endswith("_accuracy") for event in scores["batch"])
    assert scores == tracker.langfuse_scores(tracker.import_pokemon(tmp_path), payload)


def test_labeled_accuracy_and_invalid_unknown_have_distinct_denominators(tmp_path):
    _, rows = fixture_run(tmp_path)
    rows[0].update(pokemon_name_correct=True, hp_correct=False)
    rows[1].update(parse_error=True, pokemon_name="unknown", pokemon_type="unknown",
                   hp="unknown", card_number="unknown", pokemon_name_correct=False)
    rewrite(tmp_path, "results.json", rows)
    rewrite(tmp_path, "ground_truth.snapshot.json", {rows[0]["filename"]: {"pokemon_name": "PRIVATE NAME", "hp": "200"}})
    runs = tracker.import_pokemon(tmp_path)
    valid, invalid = runs[0]["records"][0], runs[1]["records"][0]
    assert valid["metrics"]["pokemon_name_accuracy"] == 1
    assert valid["metrics"]["hp_accuracy"] == 0
    assert valid["metrics"]["unknown_response_rate"] == 1
    assert valid["metrics"]["unknown_field_rate"] == .25
    assert invalid["metrics"]["pokemon_name_accuracy"] == 0
    assert invalid["metrics"]["unknown_response_rate"] is None
    scores = tracker.langfuse_scores(runs, tracker.langfuse_payload(runs))["batch"]
    names = [event["body"]["name"] for event in scores]
    assert names.count("pokemon_name_accuracy") == 2
    assert names.count("hp_accuracy") == 1
    assert names.count("unknown_response_rate") == 3


@pytest.mark.parametrize("status", ["running", "interrupted_host_reboot", "completed_with_input_errors"])
def test_interrupted_runs_are_not_imported_as_completed(tmp_path, status):
    metadata, _ = fixture_run(tmp_path)
    metadata["status"] = status
    rewrite(tmp_path, "metadata.json", metadata)
    with pytest.raises(ValueError, match="completed run"):
        tracker.import_pokemon(tmp_path)


@pytest.mark.parametrize("damage", ["missing", "duplicate", "unexpected", "hash"])
def test_complete_flag_cannot_hide_incomplete_or_mismatched_rows(tmp_path, damage):
    _, rows = fixture_run(tmp_path)
    if damage == "missing":
        rows.pop()
    elif damage == "duplicate":
        rows[-1] = rows[0].copy()
    elif damage == "unexpected":
        rows[-1]["resolution"] = "Original"
    else:
        rows[-1]["source_sha256"] = "wrong"
    rewrite(tmp_path, "results.json", rows)
    with pytest.raises(ValueError, match="records|hash"):
        tracker.import_pokemon(tmp_path)


def test_host_extrema_stay_run_wide_and_missing_metrics_stay_missing(tmp_path):
    fixture_run(tmp_path)
    host = tmp_path / "host.json"
    rewrite(tmp_path, host.name, {"samples": 80, "minimum_available_gib": 33.2,
        "maximum_gpu_temperature_c": 81, "maximum_board_temperature_c": 94})
    telemetry = tracker.import_pokemon(tmp_path, host)[0]["records"][0]["telemetry"]
    assert telemetry["min_available_gib"] == 33.2
    assert telemetry["min_free_gib"] is None
    assert "run-wide" in telemetry["accounting"]


def test_changed_labels_define_a_new_dataset_without_exporting_labels(tmp_path):
    fixture_run(tmp_path)
    before = tracker.import_pokemon(tmp_path)
    rewrite(tmp_path, "ground_truth.snapshot.json", {"PRIVATE-PHOTO-a.jpg": {"hp": "100"}})
    after = tracker.import_pokemon(tmp_path)
    assert before[0]["dataset_digest"] != after[0]["dataset_digest"]
    assert before[0]["run_id"] != after[0]["run_id"]
    assert "PRIVATE" not in json.dumps(tracker.langfuse_payload(after))


def test_roi_reference_identity_and_stage_provenance_survive_private_export(tmp_path):
    metadata, rows = fixture_run(tmp_path)
    metadata.update(evaluation_mode="guided_roi_with_reference", reference_sha256="first-guide",
        reference_path="PRIVATE REFERENCE PATH", parent_prompt_sha256="parent-prompt-hash",
        roi_policy={"type": [.7, .05, .9, .2], "number": [.05, .8, .5, .95]},
        latency_scope="Sum of saved parent HTTP and ROI HTTP, not live wall-clock",
        label_scope="Development set, not holdout")
    rows[0]["parent_raw_model_response"] = "PRIVATE PARENT RESPONSE"
    rewrite(tmp_path, "metadata.json", metadata)
    rewrite(tmp_path, "results.json", rows)
    before = tracker.import_pokemon(tmp_path)
    exported = json.dumps(tracker.langfuse_payload(before))
    assert "PRIVATE" not in exported
    assert "latency_scope" in exported and "reference_sha256" in exported
    metadata["reference_sha256"] = "second-guide"
    rewrite(tmp_path, "metadata.json", metadata)
    after = tracker.import_pokemon(tmp_path)
    assert before[0]["dataset_digest"] != after[0]["dataset_digest"]
    rows[0]["parent_raw_model_response"] = "CHANGED PARENT RESPONSE"
    rewrite(tmp_path, "results.json", rows)
    assert tracker.import_pokemon(tmp_path)[0]["records"][0]["output_sha256"] != after[0]["records"][0]["output_sha256"]


def test_missing_labels_cannot_become_scores_from_stale_correctness_flags(tmp_path):
    _, rows = fixture_run(tmp_path)
    rows[0]["pokemon_name_correct"] = True
    rewrite(tmp_path, "results.json", rows)
    runs = tracker.import_pokemon(tmp_path)
    assert runs[0]["records"][0]["metrics"]["pokemon_name_accuracy"] is None


def test_prompt_variants_share_dataset_and_export_a_distinct_tcg_type_score(tmp_path):
    metadata, rows = fixture_run(tmp_path)
    rows[0].update(pokemon_type='Metal', pokemon_type_correct=True)
    rewrite(tmp_path, 'results.json', rows)
    rewrite(tmp_path, 'ground_truth.snapshot.json', {rows[0]['filename']: {'pokemon_type': 'Metal'}})
    before = tracker.import_pokemon(tmp_path)
    metadata.update(prompt='new icon-only instruction', prompt_version='tcg-symbol-v2')
    rewrite(tmp_path, 'metadata.json', metadata)
    after = tracker.import_pokemon(tmp_path)
    assert before[0]['dataset_digest'] == after[0]['dataset_digest']
    assert before[0]['records'][0]['prompt_sha256'] != after[0]['records'][0]['prompt_sha256']
    assert after[0]['prompt_version'] == 'tcg-symbol-v2'
    assert after[0]['records'][0]['metrics']['tcg_type_accuracy'] == 1
    events = tracker.langfuse_scores(after, tracker.langfuse_payload(after))['batch']
    assert sum(e['body']['name'] == 'tcg_type_accuracy' for e in events) == 1
    assert not any(e['body']['name'] == 'pokemon_type_accuracy' for e in events)
