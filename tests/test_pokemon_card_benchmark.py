# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Verify image preservation, scoring denominators and sequential API failures."""
import json

import pytest
import requests
from PIL import Image

import pokemon_card_benchmark as b


def prediction(**changes):
    row = {"filename": "card.jpg", "resolution": "2MP", "pixels": 2_000_000,
           "pokemon_name": "Pikachu", "pokemon_type": "Lightning", "hp": "60",
           "card_number": "025/100", "api_error": False, "parse_error": False,
           "image_error": False, "http_status": 200, "latency_seconds": 2.5}
    return {**row, **changes}


@pytest.mark.parametrize("pixels", list(b.RESOLUTIONS.values()))
def test_resize_respects_pixel_budget_and_aspect(pixels):
    w, h = b.target_size(4032, 3024, pixels)
    assert w <= 4032 and h <= 3024
    assert abs(w / h - 4 / 3) < .005
    if pixels:
        assert pixels * .99 < w * h <= pixels
    else:
        assert (w, h) == (4032, 3024)


def test_no_upscale_and_preserve_original_bytes(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    Image.new("RGB", (200, 100), "red").save(source / "card.JPG")
    before = (source / "card.JPG").read_bytes()
    entries, errors = b.prepare_images(source, tmp_path / "images", b.RESOLUTIONS)
    assert not errors
    assert (source / "card.JPG").read_bytes() == before
    assert len(entries[0]["variants"]) == 7
    for variant in entries[0]["variants"]:
        assert (variant["width"], variant["height"]) == (200, 100)
        assert Image.open(variant["image_path"]).format == "PNG"


def test_exif_rotation_is_applied_to_derived_image(tmp_path):
    path = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (120, 80)).save(path, exif=exif)
    original = path.read_bytes()
    image = b.load_image(path)
    assert image.size == (80, 120)
    assert not image.getexif().get(274)
    assert path.read_bytes() == original


def test_heic_decoding(tmp_path):
    heif = pytest.importorskip("pillow_heif")
    heif.register_heif_opener()
    path = tmp_path / "card.HEIC"
    Image.new("RGB", (120, 80), "green").save(path, format="HEIF")
    original = path.read_bytes()
    assert b.load_image(path).size == (120, 80)
    assert path.read_bytes() == original


def test_same_stem_different_extension_and_corrupt_input(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    for ext in ("jpg", "png"):
        Image.new("RGB", (32, 48)).save(source / ("card." + ext))
    (source / "bad.jpg").write_bytes(b"not an image")
    entries, errors = b.prepare_images(source, tmp_path / "images", b.RESOLUTIONS)
    assert len(entries) == 2 and len(errors) == 1
    assert errors[0]["filename"] == "bad.jpg"
    assert len({v["image_path"] for e in entries for v in e["variants"]}) == 14


def test_truth_init_appends_without_overwriting_labels(tmp_path):
    b.initialize(tmp_path)
    Image.new("RGB", (32, 48)).save(tmp_path / "input" / "card.jpg")
    b.initialize(tmp_path)
    b.write_csv(tmp_path / "ground_truth.csv", [{"filename": "card.jpg", "pokemon_name": "피카츄"}],
                ("filename", *b.FIELDS))
    Image.new("RGB", (32, 48)).save(tmp_path / "input" / "second.png")
    b.initialize(tmp_path)
    truth = b.read_truth(tmp_path / "ground_truth.csv")
    assert truth["card.jpg"]["pokemon_name"] == "피카츄"
    assert truth["second.png"]["pokemon_name"] == ""


def test_duplicate_ground_truth_fails_explicitly(tmp_path):
    path = tmp_path / "truth.csv"
    b.write_csv(path, [{"filename": "card.jpg"}] * 2, ("filename", *b.FIELDS))
    with pytest.raises(ValueError, match="Duplicate"):
        b.read_truth(path)


def test_unlabeled_is_never_scored_as_zero_or_success():
    summary = b.summarize(b.score_rows([prediction()], {}), ["2MP", "5MP"])
    assert summary[0]["pokemon_name_accuracy"] is None
    assert summary[0]["pokemon_name_labeled"] == 0
    assert summary[1]["average_latency_seconds"] is None
    assert summary[1]["unknown_response_rate"] is None


def test_errors_are_wrong_but_not_unknown_model_responses():
    rows = [prediction(), prediction(filename="bad.jpg", api_error=True, http_status=500,
                                    pokemon_name="unknown", latency_seconds=9)]
    truth = {name: {"pokemon_name": "Pikachu", "hp": "unknown"} for name in ("card.jpg", "bad.jpg")}
    summary = b.summarize(b.score_rows(rows, truth), ["2MP"])[0]
    assert summary["pokemon_name_accuracy"] == .5
    assert summary["pokemon_name_labeled"] == 2
    assert summary["hp_accuracy"] is None
    assert summary["unknown_response_rate"] == 0
    assert summary["average_latency_seconds"] == 2.5
    assert summary["api_errors"] == 1


def test_partial_unknown_and_normalization():
    truth = {"card.jpg": {"pokemon_name": "  PIKACHU  ", "hp": "60 HP", "card_number": "025 / 100"}}
    rows = b.score_rows([prediction(pokemon_type="unknown")], truth)
    assert all(rows[0][f + "_correct"] is True for f in ("pokemon_name", "hp", "card_number"))
    summary = b.summarize(rows, ["2MP"])[0]
    assert summary["unknown_response_rate"] == 1
    assert summary["unknown_field_rate"] == .25
    assert b.normalize("card_number", "025/100") != b.normalize("card_number", "25/100")


@pytest.mark.parametrize("raw", ['{}', '```json\n{}\n```', '{"pokemon_name": 7}', 'null'])
def test_malformed_json_is_not_guessed(raw):
    with pytest.raises((ValueError, TypeError)):
        b.parse_prediction(raw)


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response, self.error = response, error
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


def response(body, status=200):
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps(body).encode()
    return r


def test_direct_api_payload_and_raw_response_preserved(tmp_path):
    image = tmp_path / "image.png"
    Image.new("RGB", (32, 48)).save(image)
    expected = {k: prediction()[k] for k in b.FIELDS}
    raw = json.dumps(expected)
    session = FakeSession(response({"choices": [{"finish_reason": "stop", "message": {"content": raw}}]}))
    result = b.infer(session, b.DEFAULT_URL, b.DEFAULT_MODEL, image, 30)
    assert not result["api_error"] and not result["parse_error"]
    assert result["raw_model_response"] == raw
    payload = session.calls[0][1]["json"]
    assert payload["temperature"] == 0
    assert payload["messages"][0]["content"][0]["text"] == b.PROMPT
    assert payload["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert payload["response_format"]["schema"] == b.SCHEMA
    assert len(session.calls) == 1


@pytest.mark.parametrize("failure", ["http", "timeout", "parse"])
def test_api_failures_recorded_without_retry(tmp_path, failure):
    image = tmp_path / "image.png"
    Image.new("RGB", (32, 48)).save(image)
    session = FakeSession(response({"error": "broken"}, 500) if failure == "http"
                          else response({"choices": [{"message": {"content": "bad json"}}]}),
                          requests.Timeout("timeout") if failure == "timeout" else None)
    result = b.infer(session, b.DEFAULT_URL, b.DEFAULT_MODEL, image, 30)
    assert result["parse_error"] if failure == "parse" else result["api_error"]
    assert result["error"]
    assert len(session.calls) == 1
    if failure != "timeout":
        assert result["raw_api_response"]


def test_idle_guard_does_not_post_when_busy():
    session = FakeSession()
    session.get = lambda *a, **kw: response([{"is_processing": True}])
    with pytest.raises(RuntimeError, match="busy"):
        b.wait_for_idle(session, b.DEFAULT_URL, 0)
    assert not session.calls


def test_idle_guard_fails_closed_on_unknown_schema():
    session = FakeSession()
    session.get = lambda *a, **kw: response([{}])
    with pytest.raises(ValueError, match="idle state"):
        b.wait_for_idle(session, b.DEFAULT_URL, 0)


def test_paired_comparison_excludes_duplicate_image_sizes():
    rows = b.score_rows([prediction(), prediction(resolution="5MP")],
                        {"card.jpg": {"pokemon_name": "Pikachu"}})
    assert b.paired_comparison(rows, "2MP", "5MP")["pairs"] == 0
    rows[1]["pixels"] = 5_000_000
    rows[0]["pokemon_name_correct"] = False
    pair = b.paired_comparison(rows, "2MP", "5MP")
    assert pair["pairs"] == 1 and pair["improved"] == 1
    assert pair["accuracy_delta"] == 1
    assert pair["mcnemar_exact_p"] == 1


def test_no_recommendation_without_enough_truth():
    rows = b.score_rows([prediction(resolution="0.3MP")], {})
    analysis = b.analyze(rows, b.summarize(rows, b.RESOLUTIONS), .95)
    assert "정답이 없어" in analysis["answers"][0]
    assert "추천을 확정할 수 없습니다" in analysis["answers"][-1]


def test_workspace_lock_excludes_second_process(tmp_path):
    with b.workspace_lock(tmp_path):
        with pytest.raises(RuntimeError, match="lock"):
            with b.workspace_lock(tmp_path):
                pass


def test_report_rescores_without_api_and_missing_accuracy(tmp_path, monkeypatch):
    run = tmp_path / "run"
    run.mkdir()
    b.write_json(run / "metadata.json", {"status": "completed", "resolutions": list(b.RESOLUTIONS),
                                        "inputs": [{}], "input_errors": []})
    (run / "results.jsonl").write_text(json.dumps(prediction()) + "\n")
    truth = tmp_path / "truth.csv"
    b.write_csv(truth, [], ("filename", *b.FIELDS))
    monkeypatch.setattr(b, "make_plots", lambda *a: None)
    summary = b.generate_report(run, truth)
    assert summary[1]["pokemon_name_accuracy"] is None
    assert "N/A (0)" in (run / "report.md").read_text()
    b.write_csv(truth, [{"filename": "card.jpg", "pokemon_name": "Pikachu"}], ("filename", *b.FIELDS))
    summary = b.generate_report(run, truth)
    assert summary[1]["pokemon_name_accuracy"] == 1
    for name in ("results.csv", "results.json", "summary.csv", "summary.json", "failures.csv", "failures.json"):
        assert (run / name).exists()


def test_compare_rejects_different_truth(tmp_path):
    dirs = [tmp_path / "before", tmp_path / "after"]
    for index, directory in enumerate(dirs):
        directory.mkdir()
        b.write_json(directory / "metadata.json", {"status": "completed", "inputs": []})
        b.write_json(directory / "ground_truth.snapshot.json", {"label": index})
    with pytest.raises(ValueError, match="ground truth"):
        b.compare_runs(*dirs, tmp_path / "comparison")
    result = json.loads((tmp_path / "comparison" / "comparison.json").read_text())
    assert result["comparable"] is False


def test_crash_tail_is_excluded_without_modifying_evidence(tmp_path):
    path = tmp_path / 'results.jsonl'
    data = json.dumps(prediction()).encode() + b'\n' + b'\0' * 1148
    path.write_bytes(data)
    rows, warning = b.load_saved_results(path)
    assert len(rows) == 1
    assert 'corrupt' in warning
    assert path.read_bytes() == data


def test_nonfinal_corrupt_result_is_not_silently_skipped(tmp_path):
    path = tmp_path / 'results.jsonl'
    path.write_text('bad\n' + json.dumps(prediction()) + '\n')
    with pytest.raises(ValueError, match='non-final'):
        b.load_saved_results(path)


@pytest.mark.parametrize('available,free,pressure,accept', [
    (50, 30, 0, True), (39, 30, 0, False), (50, 23, 0, False), (50, 30, .1, False)])
def test_memory_admission(tmp_path, available, free, pressure, accept):
    meminfo = tmp_path / 'meminfo'
    meminfo.write_text(f'MemAvailable: {available*2**20} kB\nMemFree: {free*2**20} kB\n')
    psi = tmp_path / 'psi'
    psi.write_text(f'full avg10={pressure} avg60=0.00 avg300=0.00 total=0\n')
    if accept:
        assert b.check_memory(40, 24, meminfo, psi)['mem_available_gib'] == available
    else:
        with pytest.raises(RuntimeError, match='No evaluation request sent'):
            b.check_memory(40, 24, meminfo, psi)
