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


@pytest.mark.parametrize("box", [(0, 0, 0, 1), (-.1, 0, 1, 1), (0, 0, 1.1, 1),
                                 (0, float("nan"), 1, 1)])
def test_invalid_roi_cannot_silently_crop_a_different_region(box):
    with pytest.raises(ValueError, match="ROI"):
        b.roi_box((480, 640), box)


def test_crops_retain_only_pixels_of_the_resized_input(tmp_path):
    original = Image.new("RGB", (480, 640))
    original.putpixel((400, 65), (255, 0, 0))
    source = tmp_path / "resized.png"
    original.save(source)
    before = source.read_bytes()
    regions = b.crop_regions(source, tmp_path / "crops")
    assert source.read_bytes() == before
    for region in regions:
        assert not region["upscaled"]
        crop = Image.open(region["image_path"])
        assert crop.tobytes() == original.crop(region["box"]).tobytes()
        assert crop.size == (region["width"], region["height"])
        assert region["source_image_sha256"] == b.sha256(source)


def test_focus_request_has_only_regions_and_independent_reference(tmp_path):
    images = []
    for name, color in [("type", "gray"), ("number", "white"), ("reference", "green")]:
        path = tmp_path / (name + ".png")
        Image.new("RGB", (32, 32), color).save(path)
        images.append(path)
    raw = json.dumps({"pokemon_type": "Metal", "card_number": "017/101"})
    session = FakeSession(response({"choices": [{"finish_reason": "stop", "message": {"content": raw}}]}))
    result = b.infer(session, b.DEFAULT_URL, b.DEFAULT_MODEL, images[0], 30,
        prompt=b.FOCUS_PROMPT, parameters=b.FOCUS_PARAMETERS, extra_images=images[1:], fields=b.FOCUS_FIELDS)
    assert result["pokemon_type"] == "Metal" and result["card_number"] == "017/101"
    payload = session.calls[0][1]["json"]
    assert len(payload["messages"][0]["content"]) == 4
    assert payload["response_format"]["schema"]["required"] == list(b.FOCUS_FIELDS)
    assert "pokemon_name" not in result
    assert payload["temperature"] == 0 and len(session.calls) == 1


def test_focus_rejects_full_photo_schema_instead_of_guessing_fields(tmp_path):
    path = tmp_path / "type.png"
    Image.new("RGB", (32, 32)).save(path)
    raw = json.dumps({k: prediction()[k] for k in b.FIELDS})
    session = FakeSession(response({"choices": [{"finish_reason": "stop", "message": {"content": raw}}]}))
    result = b.infer(session, b.DEFAULT_URL, b.DEFAULT_MODEL, path, 30,
        prompt=b.FOCUS_PROMPT, parameters=b.FOCUS_PARAMETERS, fields=b.FOCUS_FIELDS)
    assert result["parse_error"] and result["raw_model_response"] == raw


@pytest.mark.parametrize("number", ["069/100 RR", "sv9 069/100", "69", "069/100RR"])
def test_number_output_contract_rejects_extra_text_without_stripping_it(number):
    raw = json.dumps({"pokemon_type": "Metal", "card_number": number})
    with pytest.raises(ValueError, match="Card number"):
        b.parse_prediction(raw, b.FOCUS_FIELDS)


@pytest.mark.parametrize("number", ["069/100", "TG05/TG30", "unknown"])
def test_collector_number_preserves_prefixes_zeros_and_unknown(number):
    raw = json.dumps({"pokemon_type": "Metal", "card_number": number})
    assert b.parse_prediction(raw, b.FOCUS_FIELDS)["card_number"] == number


@pytest.mark.parametrize("focused_type", ["Metal", "unknown"])
def test_refinement_preserves_parent_evidence_and_reports_honest_latency(tmp_path, monkeypatch, focused_type):
    from types import SimpleNamespace
    parent = tmp_path / "runs" / "parent"
    parent.mkdir(parents=True)
    image = parent / "image.png"
    Image.new("RGB", (480, 640)).save(image)
    truth_path = tmp_path / "ground_truth.csv"
    b.write_csv(truth_path, [{"filename": "card.jpg", "pokemon_type": "Metal"}], ("filename", *b.FIELDS))
    saved = prediction(pokemon_type="Fighting", image_path=str(image), image_sha256=b.sha256(image),
        source_sha256="source", raw_model_response="historical response", raw_api_response="historical API")
    b.write_json(parent / "results.json", [saved])
    b.write_json(parent / "ground_truth.snapshot.json", b.read_truth(truth_path))
    b.write_json(parent / "metadata.json", {"status": "completed", "model": b.DEFAULT_MODEL,
        "inputs": [{"filename": "card.jpg"}], "input_errors": [], "resolutions": ["2MP"],
        "prompt": "historical prompt", "preprocessing": "full photo", "parameters": b.PARAMETERS})
    original_metadata = (parent / "metadata.json").read_bytes()
    reference = tmp_path / "reference.png"
    Image.new("RGB", (32, 32)).save(reference)
    class Session:
        trust_env = True
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setattr(b.requests, "Session", Session)
    monkeypatch.setattr(b, "check_memory", lambda *args: {})
    monkeypatch.setattr(b, "inspect_server", lambda *args: {})
    monkeypatch.setattr(b, "wait_for_idle", lambda *args: None)
    monkeypatch.setattr(b, "make_plots", lambda *args: None)
    focused = {"pokemon_type": focused_type, "card_number": "017/101", "latency_seconds": 1.5,
        "raw_model_response": "focus response", "raw_api_response": "focus API", "api_error": False,
        "parse_error": False, "image_error": False, "http_status": 200}
    monkeypatch.setattr(b, "infer", lambda *args, **kwargs: focused)
    args = SimpleNamespace(root=tmp_path, parent_run=parent, type_reference=reference,
        model=b.DEFAULT_MODEL, base_url=b.DEFAULT_URL, truth=truth_path, label="focus",
        type_roi=b.TYPE_ROI, number_roi=b.NUMBER_ROI, min_available_gib=0, min_free_gib=0,
        allow_busy=False, idle_timeout=1, timeout=30, gap=0, name_target=.95)
    result = b.refine_benchmark(args)
    row = json.loads((result / "results.json").read_text())[0]
    assert row["pokemon_type"] == focused_type
    assert row["pokemon_name"] == saved["pokemon_name"] and row["hp"] == saved["hp"]
    assert row["latency_seconds"] == 4 and row["focus_latency_seconds"] == 1.5
    assert row["parent_raw_model_response"] == "historical response"
    assert row["raw_model_response"] == "focus response"
    assert (parent / "metadata.json").read_bytes() == original_metadata
    assert "not live pipeline wall-clock" in (result / "report.md").read_text()
    labels = json.loads((result / "crop_labels.json").read_text())
    assert labels[0]["label"] == "Metal" and labels[1]["label"] == ""
    assert all(label["label_role"] == "development_evaluation" for label in labels)


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


@pytest.mark.parametrize('location', ['repo', 'workspace', 'script', 'fallback'])
def test_workspace_discovery_after_move(tmp_path, location):
    repo = tmp_path / 'repo'
    root = repo / 'pokemon-card-benchmark'
    script = repo / 'scripts/benchmark.py'
    cwd = repo
    if location != 'fallback':
        (root / 'input').mkdir(parents=True)
    if location == 'workspace':
        cwd = root
    elif location in {'script', 'fallback'}:
        cwd = tmp_path
    expected = root if location != 'fallback' else tmp_path / 'home/pokemon-card-benchmark'
    assert b.default_root(cwd, script, tmp_path / 'home') == expected


def test_custom_truth_is_preferred_and_not_rewritten(tmp_path):
    (tmp_path / 'input').mkdir()
    Image.new('RGB', (20, 10)).save(tmp_path / 'input/card.jpg')
    custom = tmp_path / 'pokebot_ground_truth.csv'
    data = 'filename,pokemon_name,pokemon_type,hp,card_number\ncard.jpg,Pikachu,Lightning,60,025/100\n'
    custom.write_text(data)
    assert b.initialize(tmp_path) == custom
    assert custom.read_text() == data
    assert not (tmp_path / 'ground_truth.csv').exists()
    Image.new('RGB', (20, 10)).save(tmp_path / 'input/new.jpg')
    b.initialize(tmp_path)
    assert b.read_truth(custom)['card.jpg']['pokemon_type'] == 'Lightning'
    assert b.read_truth(custom)['new.jpg']['hp'] == ''


def test_tcg_type_is_scored_separately_from_species_knowledge():
    rows = b.score_rows([prediction(pokemon_name='Groudon', pokemon_type='Ground'),
                        prediction(filename='correct.jpg', pokemon_name='Groudon', pokemon_type='Fighting')],
                       {'card.jpg': {'pokemon_type': 'Fighting'}, 'correct.jpg': {'pokemon_type': 'Fighting'}})
    summary = b.summarize(rows, ['2MP'])[0]
    assert rows[0]['pokemon_type_correct'] is False
    assert rows[1]['pokemon_type_correct'] is True
    assert summary['tcg_type_accuracy'] == .5
    assert summary['tcg_type_labeled'] == 2
    assert summary['pokemon_name_accuracy'] is None


def test_rescore_after_move_preserves_recorded_prompt_and_raw_paths(tmp_path, monkeypatch):
    run = tmp_path / 'run'
    image = run / 'images/2MP/card.jpg.png'
    image.parent.mkdir(parents=True)
    Image.new('RGB', (20, 10)).save(image)
    row = prediction(image_path='/old/moved/card.jpg.png', image_sha256=b.sha256(image), pokemon_type='Metal')
    raw = json.dumps(row) + '\n'
    (run / 'results.jsonl').write_text(raw)
    metadata = {'status': 'completed', 'resolutions': ['2MP'], 'inputs': [{}],
                'input_errors': [], 'prompt': 'recorded old prompt'}
    b.write_json(run / 'metadata.json', metadata)
    truth = tmp_path / 'truth.csv'
    b.write_csv(truth, [{'filename': 'card.jpg', 'pokemon_type': 'Metal'}], ['filename', *b.FIELDS])
    monkeypatch.setattr(b, 'make_plots', lambda *args: None)
    b.generate_report(run, truth)
    assert json.loads((run / 'metadata.json').read_text()) == metadata
    assert (run / 'results.jsonl').read_text() == raw
    scored = json.loads((run / 'results.json').read_text())[0]
    assert scored['image_path'] == str(image)
    assert scored['image_path_recorded'] == row['image_path']
    report = (run / 'report.md').read_text()
    assert 'TCG Type Accuracy' in report and 'legacy-v1' in report
    assert 'Metal → Metal' not in report  # Correct rows are not listed as failures.
