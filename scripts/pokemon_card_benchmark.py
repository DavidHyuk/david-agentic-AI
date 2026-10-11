#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Standalone, sequential Pokemon-card resolution benchmark for an existing VLM.

Read-only server inspection; no models, services, credentials or Hermes changes.
Images and complete raw responses stay in a user-owned workspace outside Git.
"""
from __future__ import annotations

import argparse
import base64
import csv
import fcntl
import hashlib
import json
import math
import os
import platform
import random
import re
import sys
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image, ImageOps

FIELDS = ("pokemon_name", "pokemon_type", "hp", "card_number")
RESOLUTIONS = {"0.3MP": 300_000, "2MP": 2_000_000, "3MP": 3_000_000,
               "5MP": 5_000_000, "8MP": 8_000_000, "12MP": 12_000_000,
               "Original": None}
EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
DEFAULT_MODEL = "Qwen3.8-Flash-Next-UD-IQ4_XS"
DEFAULT_URL = "http://127.0.0.1:8004/v1"
PROMPT_VERSION = "tcg-symbol-number-v3"
PROMPT = ('Read only the visible Pokemon trading card in this full photograph. '
          'Extract the printed Pokemon name, HP, and collector '
          'card number. Locate the collector number near the BOTTOM-LEFT OF THE CARD, '
          'using the card orientation rather than the photograph orientation. '
          'Return ONLY the collector number and printed set total separated by a slash '
          '(for example 017/101); preserve leading zeros and any letters that are part '
          'of the collector number itself. EXCLUDE separate set codes such as sv9 or sv3a, '
          'rarity labels such as R, RR, AR or SAR, regulation marks and other nearby text. '
          'Read both sides of the slash independently; if either is unreadable, return '
          '"unknown" rather than guessing a familiar card number. Never identify '
          'a field from artwork, memory, or guesses. If a field is unreadable or '
          'absent, return "unknown". Preserve the printed name language and suffixes '
          '(such as ex, GX, or V). '
          'For pokemon_type, identify the Pokemon TCG card type by visually examining '
          'the TYPE SYMBOL at the TOP-RIGHT corner OF THE CARD, next to its HP value. '
          'The type is represented by an icon, not a printed English type name. '
          'Use the card orientation even if the card is rotated in the photograph. '
          'Do NOT infer the type from the Pokemon name, artwork, appearance, known '
          'Pokedex type, species category, or memory. Do NOT use energy symbols next '
          'to attacks, weakness, resistance, or retreat cost. Allowed English labels '
          'are Grass, Fire, Water, Lightning, Psychic, Fighting, Darkness, Metal, '
          'Dragon, Colorless, Fairy. If the HP-adjacent type symbol is not clearly '
          'recognizable, return "unknown" for pokemon_type. '
          'Return only a JSON object with exactly four string '
          'keys: "pokemon_name", "pokemon_type", "hp", "card_number". HP must be '
          'digits without HP.')
CARD_NUMBER_PATTERN = r"^(unknown|[A-Za-z]*[0-9]+/[A-Za-z]*[0-9]+)$"
TYPE_LABELS = ("Grass", "Fire", "Water", "Lightning", "Psychic", "Fighting",
               "Darkness", "Metal", "Dragon", "Colorless", "Fairy")
SCHEMA = {"type": "object", "properties": {k: {"type": "string"} for k in FIELDS},
          "required": list(FIELDS), "additionalProperties": False}
SCHEMA["properties"]["card_number"]["pattern"] = CARD_NUMBER_PATTERN
SCHEMA["properties"]["pokemon_type"]["enum"] = [*TYPE_LABELS, "unknown"]
PARAMETERS = {"temperature": 0, "seed": 42, "top_p": 1, "top_k": 0, "min_p": 0,
              "repeat_penalty": 1, "presence_penalty": 0, "frequency_penalty": 0,
              "max_tokens": 256, "stream": False, "cache_prompt": False,
              "chat_template_kwargs": {"enable_thinking": False},
              "response_format": {"type": "json_object", "schema": SCHEMA}}

FOCUS_FIELDS = ("pokemon_type", "card_number")
FOCUS_VERSION = "tcg-reference-roi-v2"
FOCUS_PROMPT = (
    'You are reading two cropped regions from ONE Pokemon TCG card photograph. '
    'IMAGE 1 is the top-right HP-adjacent TYPE SYMBOL region. IMAGE 2 is the '
    'bottom-left COLLECTOR NUMBER region. IMAGE 3 is a labeled reference chart '
    'of the eleven official TCG type symbols; it is a guide, NOT the target card. '
    'For pokemon_type, compare the symbol shape in IMAGE 1 with IMAGE 3 and '
    'return its English label. Ignore background/card color and the HP digits. '
    'Metal has three angular lobes around a central opening; Fighting has '
    'a clenched fist. Dragon has a curved dragon-head silhouette; Colorless '
    'has a pointed star. Darkness has a dark orb/crescent. Match the actual '
    'shape, not just the color. Never infer from Pokemon identity or card number. '
    'Allowed labels: Grass, Fire, Water, Lightning, Psychic, Fighting, Darkness, '
    'Metal, Dragon, Colorless, Fairy. Return "unknown" if the target symbol '
    'cannot be distinguished; do not use symbols from the number region. '
    'For card_number, read ONLY the collector number/set-total in IMAGE 2 '
    '(format example 017/101). Preserve leading zeros and letters belonging '
    'to the collector number. EXCLUDE separate set codes, regulation marks, '
    'rarity labels R/RR/AR/SAR and all other text. Read both sides of the slash '
    'independently. If either side is unreadable, return "unknown". '
    'Return ONLY a JSON object with exactly two string keys: '
    '"pokemon_type" and "card_number".')
FOCUS_PARAMETERS = {**PARAMETERS, "response_format": {"type": "json_object", "schema": {
    "type": "object", "properties": {k: SCHEMA["properties"][k] for k in FOCUS_FIELDS},
    "required": list(FOCUS_FIELDS), "additionalProperties": False}}}
TYPE_ROI = (.77, .045, .94, .19)
NUMBER_ROI = (.055, .825, .46, .955)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
                    + "\n", encoding="utf-8")
    temp.replace(path)


def write_csv(path, rows, columns):
    path = Path(path)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict))
                             else v for k, v in row.items()})
    temp.replace(path)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover(input_dir):
    return sorted(p for p in Path(input_dir).rglob("*")
                  if p.is_file() and p.suffix.lower() in EXTENSIONS)


def read_truth(path):
    if not Path(path).exists():
        return {}
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not set(("filename", *FIELDS)).issubset(reader.fieldnames or []):
            raise ValueError("ground_truth.csv requires filename," + ",".join(FIELDS))
        truth = {}
        for row in reader:
            name = row["filename"].strip()
            if not name:
                continue
            if name in truth:
                raise ValueError(f"Duplicate ground-truth filename: {name}")
            truth[name] = {k: (row.get(k) or "").strip() for k in FIELDS}
    return truth


def default_root(cwd=None, script_path=None, home=None):
    """Find the existing workspace after a move; retain the original home fallback."""
    cwd = Path.cwd() if cwd is None else Path(cwd)
    script = Path(__file__).resolve() if script_path is None else Path(script_path)
    candidates = [cwd / "pokemon-card-benchmark", script.parent.parent / "pokemon-card-benchmark"]
    if cwd.name == "pokemon-card-benchmark":
        candidates.insert(0, cwd)
    for candidate in candidates:
        if (candidate / "input").is_dir():
            return candidate.resolve()
    return (Path.home() if home is None else Path(home)) / "pokemon-card-benchmark"


def default_truth_path(root):
    custom = Path(root) / "pokebot_ground_truth.csv"
    return custom if custom.exists() else Path(root) / "ground_truth.csv"


def initialize(root, truth_path=None):
    for name in ("input", "images", "runs", "validation"):
        (root / name).mkdir(parents=True, exist_ok=True)
    truth_path = default_truth_path(root) if truth_path is None else Path(truth_path).expanduser().resolve()
    truth = read_truth(truth_path)
    changed = not truth_path.exists()
    for path in discover(root / "input"):
        name = path.relative_to(root / "input").as_posix()
        if name not in truth:
            truth[name] = dict.fromkeys(FIELDS, "")
            changed = True
    if changed:
        write_csv(truth_path, [{"filename": name, **values} for name, values in truth.items()],
                  ("filename", *FIELDS))
    return truth_path


@contextmanager
def workspace_lock(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".benchmark.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another benchmark owns this workspace lock") from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def target_size(width, height, pixels):
    if pixels is None or width * height <= pixels:
        return width, height
    scale = math.sqrt(pixels / (width * height))
    return max(1, math.floor(width * scale)), max(1, math.floor(height * scale))


def load_image(path):
    if Path(path).suffix.lower() in {".heic", ".heif"}:
        try:
            import pillow_heif
        except ImportError as exc:
            raise RuntimeError("HEIC support requires pillow-heif in this Python environment") from exc
        pillow_heif.register_heif_opener()
    with Image.open(path) as original:
        original.load()
        image = ImageOps.exif_transpose(original)
        if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
            rgba = image.convert("RGBA")
            background = Image.new("RGBA", image.size, "white")
            image = Image.alpha_composite(background, rgba)
        return image.convert("RGB")


def prepare_images(input_dir, output_dir, resolutions, limit=None):
    files = discover(input_dir)
    if limit:
        files = files[:limit]
    entries, errors = [], []
    for source in files:
        name = source.relative_to(input_dir).as_posix()
        try:
            original_hash = sha256(source)
            image = load_image(source)
            width, height = image.size
            variants = []
            for label in resolutions:
                size = target_size(width, height, RESOLUTIONS[label])
                resized = image if size == image.size else image.resize(size, Image.Resampling.LANCZOS)
                # Keep extensions in the derived name: card.jpg and card.png cannot collide.
                destination = output_dir / label / (name + ".png")
                destination.parent.mkdir(parents=True, exist_ok=True)
                resized.save(destination, format="PNG")
                variants.append({"resolution": label, "image_path": str(destination),
                                 "width": size[0], "height": size[1], "pixels": size[0] * size[1],
                                 "actual_mp": size[0] * size[1] / 1e6,
                                 "capped_by_original": RESOLUTIONS[label] is not None
                                 and width * height < RESOLUTIONS[label],
                                 "image_sha256": sha256(destination)})
            if sha256(source) != original_hash:
                raise RuntimeError("Source changed during image preparation; discard this run")
            entries.append({"filename": name, "source_sha256": original_hash,
                            "original_width": width, "original_height": height,
                            "variants": variants})
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append({"filename": name, "error": str(exc)})
    return entries, errors


def inspect_server(session, base_url, model):
    response = session.get(base_url + "/models", timeout=(10, 15))
    response.raise_for_status()
    models = response.json()
    ids = [m.get("id") for m in models.get("data", [])]
    if model not in ids:
        raise ValueError(f"Expected existing model {model!r}; /v1/models returned {ids!r}")
    server = {"models": models}
    try:
        response = session.get(base_url.removesuffix("/v1") + "/props", timeout=(10, 15))
        response.raise_for_status()
        props = response.json()
        server["props"] = {k: props.get(k) for k in
                           ("model_alias", "model_ftype", "model_path", "modalities", "total_slots",
                            "build_info", "default_generation_settings")}
    except (requests.RequestException, ValueError) as exc:
        server["props_error"] = str(exc)
    return server


def wait_for_idle(session, base_url, max_wait):
    """Read slots before sending; no slot state mutation and no parallel requests."""
    deadline = time.monotonic() + max_wait
    while True:
        response = session.get(base_url.removesuffix("/v1") + "/slots", timeout=(10, 15))
        response.raise_for_status()
        slots = response.json()
        if not isinstance(slots, list) or not slots or any("is_processing" not in s for s in slots):
            raise ValueError("Cannot verify server idle state from /slots")
        if not any(s["is_processing"] for s in slots):
            return
        if time.monotonic() >= deadline:
            raise RuntimeError("Server remains busy; no evaluation request was sent")
        time.sleep(2)


def check_memory(min_available_gib, min_free_gib, meminfo_path=Path('/proc/meminfo'),
                 pressure_path=Path('/proc/pressure/memory')):
    """Conservative admission check, not containment for CUDA/driver faults."""
    stats = {}
    for line in meminfo_path.read_text().splitlines():
        key, value = line.split(':', 1)
        stats[key] = int(value.split()[0]) * 1024
    available = stats['MemAvailable'] / 2**30
    free = stats['MemFree'] / 2**30
    pressure = None
    if pressure_path.exists():
        for line in pressure_path.read_text().splitlines():
            if line.startswith('full '):
                values = dict(part.split('=') for part in line.split()[1:])
                pressure = float(values['avg10'])
    snapshot = {'mem_available_gib': available, 'mem_free_gib': free,
                'memory_full_psi_avg10': pressure}
    if available < min_available_gib or free < min_free_gib or (pressure is not None and pressure >= .1):
        raise RuntimeError(f"Memory admission refused: {snapshot}; requires available >= "
                           f"{min_available_gib} GiB, free >= {min_free_gib} GiB, full PSI < 0.1. "
                           "No evaluation request sent. This guard cannot guarantee GPU allocation safety.")
    return snapshot


def load_saved_results(path):
    """Recover a torn final JSONL record without changing original crash evidence."""
    lines = [line for line in path.read_bytes().splitlines() if line.strip()]
    rows, warning = [], None
    for index, line in enumerate(lines):
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError('Result row is not an object')
            rows.append(row)
        except (ValueError, UnicodeDecodeError):
            if index != len(lines) - 1:
                raise ValueError(f"Corrupt non-final JSONL row {index + 1}; manual review required") from None
            warning = f"Final JSONL row {index + 1} is corrupt ({len(line)} bytes); " \
                      "excluded from scoring. Original JSONL preserved; run is incomplete."
    return rows, warning


def parse_prediction(raw, fields=FIELDS):
    result = json.loads(raw)
    if not isinstance(result, dict) or set(result) != set(fields):
        raise ValueError("Prediction must contain exactly the required fields")
    if any(not isinstance(result[k], str) or not result[k].strip() for k in fields):
        raise ValueError("All prediction fields must be non-empty strings or 'unknown'")
    if "card_number" in fields and not re.fullmatch(CARD_NUMBER_PATTERN, result["card_number"]):
        raise ValueError("Card number must contain only collector number/set total or unknown")
    if "pokemon_type" in fields and result["pokemon_type"] not in (*TYPE_LABELS, "unknown"):
        raise ValueError("Type must be a supported TCG label or unknown")
    return {k: v.strip() for k, v in result.items()}


def infer(session, base_url, model, image_path, timeout, *, prompt=None,
          parameters=None, extra_images=(), fields=FIELDS):
    content = [{"type": "text", "text": PROMPT if prompt is None else prompt}]
    for path in (image_path, *extra_images):
        url = "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": url}})
    payload = {"model": model, **(PARAMETERS if parameters is None else parameters),
               "messages": [{"role": "user", "content": content}]}
    record = {**dict.fromkeys(fields, "unknown"), "api_error": False, "parse_error": False,
              "image_error": False, "error": "", "http_status": None,
              "raw_model_response": "", "raw_api_response": "", "latency_seconds": None,
              "usage": {}, "timings": {}, "finish_reason": None}
    start = time.perf_counter()
    try:
        response = session.post(base_url + "/chat/completions", json=payload, timeout=(10, timeout))
        record["latency_seconds"] = time.perf_counter() - start
        record["http_status"] = response.status_code
        record["raw_api_response"] = response.text
        response.raise_for_status()
    except requests.RequestException as exc:
        record.update(api_error=True, error=str(exc), latency_seconds=time.perf_counter() - start)
        return record
    try:
        body = response.json()
        choice = body["choices"][0]
        record.update(raw_model_response=choice["message"]["content"],
                      finish_reason=choice.get("finish_reason"), usage=body.get("usage", {}),
                      timings=body.get("timings", {}))
        record.update(parse_prediction(record["raw_model_response"], fields))
        if record["finish_reason"] == "length":
            raise ValueError("Model output reached the token limit")
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        record.update(parse_error=True, error=str(exc))
    return record


def normalize(field, value):
    value = " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())
    if field == "hp":
        value = re.sub(r"\s*hp\s*", "", value)
        return str(int(value)) if value.isdigit() else value
    if field == "card_number":
        return value.replace(" ", "")
    return value


def labeled(value):
    return bool(value and normalize("pokemon_name", value) != "unknown")


def valid_prediction(row):
    return not any(row.get(k) for k in ("api_error", "parse_error", "image_error"))


def score_rows(rows, truth):
    scored = []
    for row in rows:
        item = dict(row)
        for field in FIELDS:
            expected = truth.get(row["filename"], {}).get(field, "")
            item["expected_" + field] = expected
            item[field + "_correct"] = (valid_prediction(row)
                and normalize(field, row[field]) == normalize(field, expected)) if labeled(expected) else None
        scored.append(item)
    return scored


def wilson(successes, count):
    if not count:
        return None
    z = 1.959963984540054
    p = successes / count
    denominator = 1 + z * z / count
    center = (p + z * z / (2 * count)) / denominator
    half = z * math.sqrt(p * (1 - p) / count + z * z / (4 * count * count)) / denominator
    return [max(0, center - half), min(1, center + half)]


def summarize(rows, resolutions):
    result = []
    for label in resolutions:
        group = [r for r in rows if r["resolution"] == label]
        valid = [r for r in group if valid_prediction(r)]
        latency = [r["latency_seconds"] for r in group
                   if r.get("http_status") == 200 and r.get("latency_seconds") is not None]
        item = {"resolution": label, "rows": len(group), "valid_responses": len(valid),
                "api_errors": sum(bool(r.get("api_error")) for r in group),
                "parse_errors": sum(bool(r.get("parse_error")) for r in group),
                "image_errors": sum(bool(r.get("image_error")) for r in group),
                "capped_images": sum(bool(r.get("capped_by_original")) for r in group),
                "average_latency_seconds": sum(latency) / len(latency) if latency else None,
                "latency_samples": len(latency),
                "unknown_response_rate": sum(any(normalize(f, r[f]) == "unknown" for f in FIELDS)
                                             for r in valid) / len(valid) if valid else None,
                "unknown_field_rate": sum(normalize(f, r[f]) == "unknown" for r in valid for f in FIELDS)
                                      / (len(valid) * len(FIELDS)) if valid else None}
        for field in FIELDS:
            values = [r[field + "_correct"] for r in group if r[field + "_correct"] is not None]
            item[field + "_labeled"] = len(values)
            item[field + "_correct"] = sum(values)
            item[field + "_accuracy"] = sum(values) / len(values) if values else None
            item[field + "_ci95"] = wilson(sum(values), len(values))
        for suffix in ("accuracy", "labeled", "correct", "ci95"):
            item["tcg_type_" + suffix] = item["pokemon_type_" + suffix]
        result.append(item)
    return result


def paired_comparison(rows, lower, higher, field="pokemon_name"):
    left = {r["filename"]: r for r in rows if r["resolution"] == lower}
    right = {r["filename"]: r for r in rows if r["resolution"] == higher}
    pairs = [(left[n], right[n]) for n in sorted(left.keys() & right.keys())
             if left[n].get(field + "_correct") is not None
             and right[n].get(field + "_correct") is not None
             and left[n].get("pixels") != right[n].get("pixels")]
    improved = sum(not a[field + "_correct"] and b[field + "_correct"] for a, b in pairs)
    regressed = sum(a[field + "_correct"] and not b[field + "_correct"] for a, b in pairs)
    discordant = improved + regressed
    # Exact McNemar test: log probabilities prevent huge intermediate integers.
    pvalue = min(1., 2 * sum(math.exp(math.lgamma(discordant + 1) - math.lgamma(k + 1)
                 - math.lgamma(discordant - k + 1) - discordant * math.log(2))
                 for k in range(min(improved, regressed) + 1))) if discordant else 1.
    return {"lower": lower, "higher": higher, "field": field, "pairs": len(pairs),
            "improved": improved, "regressed": regressed,
            "accuracy_delta": (improved - regressed) / len(pairs) if pairs else None,
            "mcnemar_exact_p": pvalue if pairs else None}


def analyze(rows, summary, threshold):
    by_label = {s["resolution"]: s for s in summary}
    answers = []
    small = by_label.get("0.3MP")
    if not small or small["pokemon_name_accuracy"] is None:
        answers.append("0.3MP 이름 인식: 정답이 없어 판단할 수 없습니다.")
    else:
        accuracy, n = small["pokemon_name_accuracy"], small["pokemon_name_labeled"]
        lower = small["pokemon_name_ci95"][0]
        qualified = lower >= threshold and n >= 30 and not small["capped_images"]
        answers.append(f"0.3MP 이름 인식: {accuracy:.1%} (n={n}, 95% 하한 {lower:.1%}). "
                       + (f"설정한 목표 {threshold:.0%}를 신뢰구간 하한에서도 충족합니다."
                          if qualified else "충분하다고 확정할 근거가 부족합니다."))
    comparisons = [paired_comparison(rows, "2MP", "5MP", field) for field in FIELDS]
    pair = comparisons[0]
    if not pair["pairs"]:
        answers.append("2MP 대 5MP: 서로 다른 실제 픽셀 크기의 정답 쌍이 없어 판단할 수 없습니다.")
    else:
        significant = pair["mcnemar_exact_p"] < .05 and abs(pair["accuracy_delta"]) >= .05
        answers.append(f"2MP 대 5MP 이름 정확도 차이: {100*pair['accuracy_delta']:+.1f}%p "
                       f"(서로 다른 크기 {pair['pairs']}쌍, exact McNemar p={pair['mcnemar_exact_p']:.4f}). "
                       + ("5%p 이상 차이와 p<0.05 기준을 충족합니다." if significant
                          else "5%p 이상 차이와 p<0.05를 함께 충족하지 않습니다. 동등함을 뜻하지 않습니다."))
    high_pairs = [paired_comparison(rows, "5MP", high, field)
                  for high in ("8MP", "12MP", "Original") for field in FIELDS]
    comparisons.extend(high_pairs)
    usable = [p for p in high_pairs if p["pairs"] >= 30]
    gains = [p for p in usable if p["accuracy_delta"] >= .05 and p["mcnemar_exact_p"] < .05]
    answers.append("5MP 이상 포화: " + ("추가 해상도에서 유의한 개선이 관측돼 포화라고 보기 어렵습니다."
                   if gains else "작은 표본, 중복 크기 및 서버 Vision 전처리 영향을 확인해야 합니다. "
                   "유의한 개선이 없다는 사실만으로 포화를 확정하지 않습니다."))
    candidates = [s for s in summary if s["resolution"] != "Original"
                  and s["pokemon_name_labeled"] >= 30 and not s["capped_images"]
                  and s["pokemon_name_ci95"][0] >= threshold]
    answers.append("최소 카메라 해상도: " + (f"이 데이터의 이름 인식 목표에서 {candidates[0]['resolution']}가 "
                   "가장 낮은 통과 조건입니다. HP/카드 번호와 실제 카메라 촬영으로 추가 확인하세요."
                   if candidates else "아직 추천을 확정할 수 없습니다. 각 조건 30장 이상의 정답과 "
                   f"이름 정확도 95% 하한 ≥ {threshold:.0%}가 기본 판단 기준입니다."))
    return {"name_target": threshold, "minimum_labeled_images": 30,
            "practical_difference": .05, "answers": answers, "paired_comparisons": comparisons}


def make_plots(run_dir, summary):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    labels = [s["resolution"] for s in summary]
    x = list(range(len(labels)))
    fig, ax = plt.subplots(figsize=(10, 5))
    any_labels = False
    field_labels = {"pokemon_name": "Pokemon Name", "pokemon_type": "TCG Type", "hp": "HP", "card_number": "Card Number"}
    for field in FIELDS:
        points = [(i, s[field + "_accuracy"], s[field + "_ci95"]) for i, s in enumerate(summary)
                  if s[field + "_accuracy"] is not None]
        if points:
            any_labels = True
            ax.errorbar([p[0] for p in points], [100*p[1] for p in points],
                        yerr=[[100*(p[1]-p[2][0]) for p in points],
                              [100*(p[2][1]-p[1]) for p in points]],
                        marker="o", capsize=3, label=field_labels[field])
    if not any_labels:
        ax.text(.5, .5, "No ground truth: accuracy unavailable", ha="center", transform=ax.transAxes)
    else:
        ax.legend()
    ax.set(xticks=x, xticklabels=labels, ylim=(-3, 103), ylabel="Accuracy (%) with 95% Wilson CI",
           title="Pokemon card recognition by submitted image resolution")
    ax.grid(axis="y", alpha=.25)
    fig.tight_layout()
    for ext in ("png", "svg"):
        fig.savefig(run_dir / ("accuracy." + ext), dpi=160)
    plt.close(fig)
    fig, (lat, unk) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    lat.bar(x, [s["average_latency_seconds"] if s["average_latency_seconds"] is not None
                else float("nan") for s in summary])
    unk.bar(x, [100*s["unknown_response_rate"] if s["unknown_response_rate"] is not None
                else float("nan") for s in summary])
    lat.set(ylabel="Average HTTP latency (s)", title="HTTP 200 only; unknown rate uses valid JSON responses")
    unk.set(xticks=x, xticklabels=labels, ylabel="Any unknown field (%)", ylim=(0, 100))
    fig.tight_layout()
    for ext in ("png", "svg"):
        fig.savefig(run_dir / ("latency_unknown." + ext), dpi=160)
    plt.close(fig)


def markdown_cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def generate_report(run_dir, truth_path, threshold=.95):
    metadata = json.loads((run_dir / "metadata.json").read_text())
    rows, warning = load_saved_results(run_dir / "results.jsonl")
    if warning:
        metadata['recovery_warning'] = warning
        if metadata.get('status') in {'running', 'completed'}:
            metadata['status'] = 'incomplete_corrupt_tail'
        write_json(run_dir / 'metadata.json', metadata)
        print('WARNING: ' + warning, file=sys.stderr)
    truth = read_truth(truth_path)
    write_json(run_dir / "ground_truth.snapshot.json", truth)
    scored = score_rows(rows, truth)
    # Preserve raw JSONL paths while exposing valid local paths after workspace moves.
    for row in scored:
        recorded = row.get("image_path")
        if recorded and not Path(recorded).exists():
            relocated = run_dir / "images" / row["resolution"] / (row["filename"] + ".png")
            if relocated.exists() and row.get("image_sha256") == sha256(relocated):
                row["image_path_recorded"] = recorded
                row["image_path"] = str(relocated)
    summary = summarize(scored, metadata["resolutions"])
    analysis = analyze(scored, summary, threshold)
    write_json(run_dir / "results.json", scored)
    write_json(run_dir / "summary.json", {"resolutions": summary, "analysis": analysis})
    columns = ("filename", "resolution", "width", "height", "pixels", "actual_mp",
               "capped_by_original", *FIELDS, "latency_seconds", "api_error", "parse_error",
               "image_error", "http_status", "error", "raw_model_response", "raw_api_response",
               "image_path", "image_path_recorded", "source_sha256", "image_sha256", "finish_reason", "usage", "timings",
               "focus_regions", "focus_latency_seconds", "parent_latency_seconds", "additional_input_pixels",
               "parent_raw_model_response", "parent_raw_api_response",
               *("expected_" + f for f in FIELDS), *(f + "_correct" for f in FIELDS))
    write_csv(run_dir / "results.csv", scored, columns)
    summary_columns = [k for k in summary[0] if not k.endswith("_ci95")] if summary else ["resolution"]
    write_csv(run_dir / "summary.csv", summary, summary_columns)
    failures = [r for r in scored if not valid_prediction(r)
                or any(r[f + "_correct"] is False or normalize(f, r[f]) == "unknown" for f in FIELDS)]
    write_csv(run_dir / "failures.csv", failures, columns)
    write_json(run_dir / "failures.json", failures)
    if metadata.get("evaluation_mode") == "guided_roi_with_reference":
        labels = [{"filename": row["filename"], "resolution": row["resolution"],
            "field": region["field"], "label": truth.get(row["filename"], {}).get(region["field"], ""),
            "label_source": "Human source-card ground truth; verify crop visibility before training",
            "label_role": "development_evaluation", **region}
            for row in scored for region in row.get("focus_regions", [])]
        write_json(run_dir / "crop_labels.json", labels)
        write_csv(run_dir / "crop_labels.csv", labels, ("filename", "resolution", "field", "label",
            "label_source", "label_role", "image_path", "image_sha256", "box", "width", "height",
            "normalized_rectangle", "source_image_sha256", "upscaled"))
    def pct(value):
        return "N/A" if value is None else f"{value:.1%}"
    lines = ["# 포켓몬 카드 해상도 벤치마크", "", f"Run: `{run_dir.name}`; 상태: {metadata.get('status')}",
             "", metadata.get('recovery_warning', ''),
             "", "전체 사진, EXIF 회전, Lanczos, 업스케일 없음. 실제 픽셀 크기는 results.csv 참고.",
             "", f"Prompt version: {metadata.get('prompt_version', 'legacy-v1')} (실행 당시 metadata.json 보존)",
             "", "평가 범위: " + metadata.get("label_scope", "해상도별 전체 이미지 평가"),
             "", "지연 범위: " + metadata.get("latency_scope", "단일 전체 이미지 HTTP 요청"),
             "", ("타입/번호는 Crop+공식 범례로 재인식했습니다. 이름/HP는 parent run 응답을 재사용했습니다. "
                   "focus_regions에 좌표·실제 Crop 크기·해시가 있고, 원문 모델 응답은 새 ROI 요청의 응답입니다. "
                   "parent_raw_*에는 이전 전체 이미지 응답을 보존합니다. 카드 자동 검출/회전 보정은 수행하지 않습니다."
                   if metadata.get("evaluation_mode") == "guided_roi_with_reference" else ""),
             "", "|조건|응답/계획|Name Accuracy (n)|TCG Type Accuracy (n)|HP Accuracy (n)|Card Number Accuracy (n)|평균 초|Unknown|크기 제한|",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for s in summary:
        values = [f"{pct(s[f+'_accuracy'])} ({s[f+'_labeled']})" for f in FIELDS]
        latency = "N/A" if s["average_latency_seconds"] is None else f"{s['average_latency_seconds']:.3f}"
        planned = (len(metadata["inputs"]) + len(metadata["input_errors"]))
        lines.append(f"|{s['resolution']}|{s['rows']}/{planned}|{'|'.join(values)}|{latency}|"
                     f"{pct(s['unknown_response_rate'])}|{s['capped_images']}|")
    lines += ["", "정확도 분모는 해당 항목에 정답이 있는 완료 행입니다. API/파싱/이미지 오류는 오답입니다.",
              "빈 정답과 `unknown` 정답은 평가 제외; 미완료 요청은 분모 제외하며 위 표에 완료/계획을 표시합니다.",
              "Unknown은 유효 JSON 응답 중 하나 이상의 필드가 unknown인 비율이며 오류로 만든 placeholder는 제외합니다.",
              "평균 지연은 HTTP 200 요청의 업로드·대기·Vision 전처리·생성 시간을 포함하며 유효 JSON 여부와 독립적입니다.",
              "", "## 결과에 따른 판단", "", *["- " + a for a in analysis["answers"]],
              "", "판단 기준은 보수적인 운영 기준이며 카메라 성능 보증이 아닙니다. 신뢰구간은 독립 사진 가정입니다.",
              "같은 카드의 반복 사진은 독립 표본이 아니므로 카드 종류·조명·거리·각도별 별도 확인이 필요합니다.",
              "고해상도 원본이 작으면 여러 조건이 동일해지고 서버가 내부적으로 이미지를 축소할 수도 있습니다.",
              "실제 센서, 렌즈, 초점, 움직임 및 카드의 프레임 점유율은 스마트폰 축소 실험으로 검증되지 않습니다.",
              "", "![Accuracy](accuracy.png)", "", "![Latency and unknown](latency_unknown.png)",
              "", "## 실패 / unknown 상세", "", "전체 원문은 results.json/CSV, 실패 목록은 failures.csv/JSON 참고.",
              "정답이 없는 일반 응답은 성공/실패로 단정하지 않습니다.", "",
              "TCG Type은 카드 HP 옆 아이콘의 종류이며 도감 타입과 별개입니다. 프롬프트만으로 모델의 판단 근거를 증명하지는 못합니다.",
              "", "|파일|조건|Name 예측 → 정답|TCG Type 예측 → 정답|HP 예측 → 정답|번호 예측 → 정답|오류|", "|---|---|---|---|---|---|---|"]
    for r in failures:
        details = [f"{r[f]} → {r['expected_'+f] or '(미입력)'}" for f in FIELDS]
        lines.append("|" + "|".join(markdown_cell(v) for v in
                     (r["filename"], r["resolution"], *details, r.get("error", ""))) + "|")
    (run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    make_plots(run_dir, summary)
    return summary


def new_directory(parent, label):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = parent / (stamp + ("-" + label if label else ""))
    path.mkdir(parents=True, exist_ok=False)
    return path


def roi_box(size, rectangle):
    """Convert a normalized guided-frame rectangle to pixels, never enlarging it."""
    if len(rectangle) != 4 or any(not math.isfinite(v) for v in rectangle):
        raise ValueError("ROI must contain four finite coordinates")
    left, top, right, bottom = rectangle
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        raise ValueError("ROI must lie inside the image and have positive area")
    width, height = size
    return (math.floor(left * width), math.floor(top * height),
            math.ceil(right * width), math.ceil(bottom * height))


def crop_regions(image_path, destination, type_roi=TYPE_ROI, number_roi=NUMBER_ROI):
    """Crop AFTER resolution downsampling; coordinates contain no card labels."""
    original_hash = sha256(image_path)
    regions = []
    with Image.open(image_path) as image:
        for field, rectangle in zip(FOCUS_FIELDS, (type_roi, number_roi)):
            box = roi_box(image.size, rectangle)
            path = destination / (field + ".png")
            path.parent.mkdir(parents=True, exist_ok=True)
            image.crop(box).save(path, format="PNG")
            regions.append({"field": field, "normalized_rectangle": list(rectangle),
                "box": list(box), "width": box[2] - box[0], "height": box[3] - box[1],
                "image_path": str(path), "image_sha256": sha256(path),
                "source_image_sha256": original_hash, "upscaled": False})
    if sha256(image_path) != original_hash:
        raise RuntimeError("Source image changed while cropping")
    return regions


def refine_benchmark(args):
    """Re-read two ROIs with an independent symbol guide; retain prior name/HP."""
    parent = args.parent_run.expanduser().resolve()
    metadata = json.loads((parent / "metadata.json").read_text())
    rows = json.loads((parent / "results.json").read_text())
    if metadata.get("status") != "completed" or metadata.get("input_errors"):
        raise ValueError("Refinement requires a complete parent without input errors")
    if metadata["model"] != args.model:
        raise ValueError("Refinement must use the same existing model as its parent")
    expected = {(entry["filename"], resolution) for entry in metadata["inputs"]
                for resolution in metadata["resolutions"]}
    actual = [(row["filename"], row["resolution"]) for row in rows]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError("Parent coverage is incomplete or duplicated")
    if any(not valid_prediction(row) for row in rows):
        raise ValueError("Refinement requires valid parent responses")
    reference = args.type_reference.expanduser().resolve()
    with Image.open(reference) as image:
        if image.format != "PNG":
            raise ValueError("Type reference must be a labeled PNG image")
        reference_pixels = image.width * image.height
    reference_hash = sha256(reference)
    truth_path = args.truth or default_truth_path(args.root)
    if read_truth(truth_path) != json.loads((parent / "ground_truth.snapshot.json").read_text()):
        raise ValueError("Parent and refinement must use identical human labels")
    # Verify submitted images before any request; never locate ROIs from ground truth.
    for row in rows:
        if sha256(Path(row["image_path"])) != row["image_sha256"]:
            raise ValueError("Parent submitted image hash mismatch")
    check_memory(args.min_available_gib, args.min_free_gib)
    with requests.Session() as session:
        session.trust_env = False
        server = inspect_server(session, args.base_url, args.model)
        run_dir = new_directory(args.root / "runs", args.label)
        metadata.update(created_utc=datetime.now(timezone.utc).isoformat(), status="running",
            finished_utc=None, parent_run=str(parent), server=server, base_url=args.base_url,
            prompt=FOCUS_PROMPT, prompt_version=FOCUS_VERSION, parameters=FOCUS_PARAMETERS,
            parent_prompt_sha256=hashlib.sha256(metadata["prompt"].encode()).hexdigest(),
            evaluation_mode="guided_roi_with_reference", reference_sha256=reference_hash,
            reference_path=str(reference), reference_pixels=reference_pixels,
            roi_policy={"type": list(args.type_roi), "number": list(args.number_roi),
                "scope": "Shared coordinates for upright, tightly framed cards; no automatic detection"},
            preprocessing=metadata["preprocessing"] + "; crop AFTER resizing; no upscale; guided frame; type reference",
            latency_scope="Sum of saved parent full-photo HTTP and new ROI HTTP; not live pipeline wall-clock",
            label_scope="Development set: prompt/ROI adjusted on these four cards; not a holdout",
            request_gap_seconds=args.gap, idle_guard=not args.allow_busy,
            script_sha256=sha256(Path(__file__)),
            memory_admission={"min_available_gib": args.min_available_gib,
                "min_free_gib": args.min_free_gib, "max_full_psi_avg10": .1})
        # Make the exact immutable reference part of this run's local evidence.
        (run_dir / "type-reference.png").write_bytes(reference.read_bytes())
        write_json(run_dir / "metadata.json", metadata)
        write_csv(run_dir / "input_errors.csv", [], ("filename", "error"))
        print(f"Run directory: {run_dir}", flush=True)
        try:
            with (run_dir / "results.jsonl").open("a", encoding="utf-8", buffering=1) as out:
                for saved in rows:
                    regions = crop_regions(Path(saved["image_path"]),
                        run_dir / "crops" / saved["resolution"] / saved["filename"],
                        args.type_roi, args.number_roi)
                    if sha256(reference) != reference_hash:
                        raise RuntimeError("Type reference changed during refinement")
                    if not args.allow_busy:
                        wait_for_idle(session, args.base_url, args.idle_timeout)
                    memory = check_memory(args.min_available_gib, args.min_free_gib)
                    focused = infer(session, args.base_url, args.model, regions[0]["image_path"],
                        args.timeout, prompt=FOCUS_PROMPT, parameters=FOCUS_PARAMETERS,
                        extra_images=(regions[1]["image_path"], run_dir / "type-reference.png"),
                        fields=FOCUS_FIELDS)
                    row = {**saved, **focused, "focus_regions": regions, "memory_before": memory,
                        "parent_raw_model_response": saved["raw_model_response"],
                        "parent_raw_api_response": saved["raw_api_response"],
                        "parent_latency_seconds": saved["latency_seconds"],
                        "focus_latency_seconds": focused["latency_seconds"],
                        "latency_seconds": saved["latency_seconds"] + focused["latency_seconds"],
                        "additional_input_pixels": reference_pixels + sum(r["width"] * r["height"] for r in regions)}
                    if focused["parse_error"] or focused["api_error"]:
                        row.update(dict.fromkeys(FOCUS_FIELDS, "unknown"))
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    out.flush()
                    os.fsync(out.fileno())
                    print(f"{row['filename']} {row['resolution']} type={row['pokemon_type']} "
                          f"number={row['card_number']} focus={row['focus_latency_seconds']:.3f}s", flush=True)
                    if focused["api_error"]:
                        raise RuntimeError("Focused API failed; stopped without retry")
                    time.sleep(args.gap)
            metadata["status"] = "completed"
        except (RuntimeError, ValueError, requests.RequestException, KeyboardInterrupt) as exc:
            metadata.update(status="interrupted", stop_reason=str(exc) or "KeyboardInterrupt")
            raise
        finally:
            metadata["finished_utc"] = datetime.now(timezone.utc).isoformat()
            write_json(run_dir / "metadata.json", metadata)
            generate_report(run_dir, truth_path, args.name_target)
        return run_dir


def run_benchmark(args):
    root = args.root
    truth_path = initialize(root, getattr(args, "truth", None))
    check_memory(args.min_available_gib, args.min_free_gib)
    with requests.Session() as session:
        # Loopback requests must not inherit proxy routing.
        session.trust_env = False
        server = inspect_server(session, args.base_url, args.model)
        run_dir = new_directory(root / "runs", args.label)
        entries, errors = prepare_images(root / "input", run_dir / "images", args.resolutions, args.limit)
        from PIL import __version__ as pillow_version
        metadata = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
                    "status": "running", "base_url": args.base_url, "model": args.model,
                    "server": server, "prompt": PROMPT, "prompt_version": PROMPT_VERSION, "parameters": PARAMETERS,
                    "resolutions": args.resolutions, "inputs": entries, "input_errors": errors,
                    "preprocessing": "EXIF transpose; full RGB image; Lanczos; PNG; no upscale",
                    "python": sys.version, "platform": platform.platform(),
                    "script_sha256": sha256(Path(__file__)),
                    "pillow_version": pillow_version, "requests_version": requests.__version__,
                    "request_gap_seconds": args.gap, "idle_guard": not args.allow_busy,
                    "order_seed": args.order_seed, "name_target": args.name_target}
        metadata['memory_admission'] = {'min_available_gib': args.min_available_gib,
                                        'min_free_gib': args.min_free_gib, 'max_full_psi_avg10': .1}
        write_json(run_dir / "metadata.json", metadata)
        write_csv(run_dir / "input_errors.csv", errors, ("filename", "error"))
        jsonl = run_dir / "results.jsonl"
        jsonl.touch()
        print(f"Run directory: {run_dir}", flush=True)
        if not entries and not errors:
            metadata["status"] = "no_images"
            write_json(run_dir / "metadata.json", metadata)
            generate_report(run_dir, truth_path, args.name_target)
            print("No input photos. No Vision evaluation requests sent.", flush=True)
            return run_dir
        rng = random.Random(args.order_seed)
        try:
            with jsonl.open("a", encoding="utf-8", buffering=1) as out:
                for error in errors:
                    for label in args.resolutions:
                        row = {"filename": error["filename"], "resolution": label,
                               **dict.fromkeys(FIELDS, "unknown"), "image_error": True,
                               "api_error": False, "parse_error": False, "error": error["error"],
                               "latency_seconds": None, "raw_model_response": "", "raw_api_response": ""}
                        out.write(json.dumps(row, ensure_ascii=False) + "\n")
                        out.flush()
                        os.fsync(out.fileno())
                for entry in entries:
                    variants = entry["variants"][:]
                    rng.shuffle(variants)
                    for variant in variants:
                        if not args.allow_busy:
                            wait_for_idle(session, args.base_url, args.idle_timeout)
                        memory_before = check_memory(args.min_available_gib, args.min_free_gib)
                        prediction = infer(session, args.base_url, args.model,
                                           variant["image_path"], args.timeout)
                        row = {"filename": entry["filename"], "source_sha256": entry["source_sha256"],
                               **variant, **prediction, 'memory_before': memory_before}
                        out.write(json.dumps(row, ensure_ascii=False) + "\n")
                        out.flush()
                        os.fsync(out.fileno())
                        print(f"{entry['filename']} {variant['resolution']} {variant['width']}x{variant['height']} "
                              f"{prediction['pokemon_name']} {prediction['latency_seconds']:.3f}s "
                              f"{prediction['error']}", flush=True)
                        # A read timeout may leave server work active. Stop rather than retry or overlap.
                        if prediction["api_error"]:
                            raise RuntimeError("API failed; stopped without retries. Inspect raw response before rerunning.")
                        time.sleep(args.gap)
            metadata["status"] = "completed_with_input_errors" if errors else "completed"
        except (RuntimeError, ValueError, requests.RequestException, KeyboardInterrupt) as exc:
            metadata.update(status="interrupted", stop_reason=str(exc) or "KeyboardInterrupt")
            raise
        finally:
            metadata["finished_utc"] = datetime.now(timezone.utc).isoformat()
            write_json(run_dir / "metadata.json", metadata)
            generate_report(run_dir, truth_path, args.name_target)
        return run_dir


def watch_inputs(args):
    """Foreground opt-in watcher: settle file sizes, then run a sequential snapshot."""
    initialize(args.root)
    previous = None
    stable_since = time.monotonic()
    completed = None
    print("Watching input/. Ctrl-C stops watching. Existing server settings are unchanged.", flush=True)
    while True:
        signature = tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns)
                          for p in discover(args.root / "input"))
        if signature != previous:
            previous, stable_since = signature, time.monotonic()
        elif signature and signature != completed and time.monotonic() - stable_since >= args.settle:
            run_benchmark(args)
            completed = signature
        time.sleep(args.poll)


def compare_runs(before, after, output):
    metas = [json.loads((p / "metadata.json").read_text()) for p in (before, after)]
    reasons = []
    for key in ("prompt", "parameters", "resolutions", "preprocessing"):
        if metas[0].get(key) != metas[1].get(key):
            reasons.append(f"Different {key}")
    def fingerprints(meta):
        return {(i["filename"], v["resolution"]): (i["source_sha256"], v["image_sha256"])
                for i in meta["inputs"] for v in i["variants"]}
    if fingerprints(metas[0]) != fingerprints(metas[1]):
        reasons.append("Different input or submitted image hashes")
    if any(m.get("status") != "completed" for m in metas):
        reasons.append("At least one run is incomplete or has input errors")
    truths = [json.loads((p / "ground_truth.snapshot.json").read_text()) for p in (before, after)]
    if truths[0] != truths[1]:
        reasons.append("Different ground truth snapshots; regenerate both reports with the same CSV")
    output.mkdir(parents=True, exist_ok=True)
    if reasons:
        write_json(output / "comparison.json", {"comparable": False, "reasons": reasons})
        raise ValueError("Cannot make a controlled comparison: " + "; ".join(reasons))
    summaries = [json.loads((p / "summary.json").read_text())["resolutions"] for p in (before, after)]
    values = []
    for a, b in zip(*summaries):
        row = {"resolution": a["resolution"]}
        for metric in (*(f + "_accuracy" for f in FIELDS), "average_latency_seconds", "unknown_response_rate"):
            row[metric + "_before"], row[metric + "_after"] = a[metric], b[metric]
            row[metric + "_delta"] = b[metric] - a[metric] if a[metric] is not None and b[metric] is not None else None
        values.append(row)
    write_json(output / "comparison.json", {"comparable": True, "before": str(before),
               "after": str(after), "models": [m["model"] for m in metas], "metrics": values})
    write_csv(output / "comparison.csv", values, list(values[0]))
    lines = ["# Fine-tuning 전후 비교", "", f"Before: {before}", f"After: {after}", "",
             "입력 해시, 프롬프트, 추론 설정, 정답이 동일함을 검사했습니다. 모델/서버 교체는 외부에서 수행합니다.",
             "이름 정확도만 아래에 표시하며 전체 필드 및 지연 차이는 comparison.csv/JSON 참고.", "",
             "|조건|Before 이름 정확도|After 이름 정확도|차이 (%p)|", "|---|---:|---:|---:|"]
    for r in values:
        metric = "pokemon_name_accuracy"
        vals = ["N/A" if r[metric+s] is None else f"{100*r[metric+s]:.2f}" for s in ("_before", "_after", "_delta")]
        lines.append(f"|{r['resolution']}|{'|'.join(vals)}|")
    (output / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=default_root())
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Create folders and add missing ground truth rows; no inference")
    prepare = sub.add_parser("prepare", help="Resize every input without any API calls")
    prepare.add_argument("--limit", type=int)
    run = sub.add_parser("run", help="Discover inputs and evaluate all resolutions sequentially")
    run.add_argument("--base-url", default=DEFAULT_URL)
    run.add_argument("--model", default=DEFAULT_MODEL)
    run.add_argument("--label", default="baseline")
    run.add_argument("--truth", type=Path, help="Human labels CSV; default prefers pokebot_ground_truth.csv")
    run.add_argument("--limit", type=int, help="Maximum number of photos (all seven sizes per photo)")
    run.add_argument("--resolutions", nargs="+", choices=RESOLUTIONS, default=list(RESOLUTIONS))
    run.add_argument("--timeout", type=float, default=300)
    run.add_argument("--gap", type=float, default=2)
    run.add_argument("--idle-timeout", type=float, default=120)
    run.add_argument("--allow-busy", action="store_true", help="Explicitly skip read-only /slots idle guard")
    run.add_argument("--order-seed", type=int, default=42)
    run.add_argument("--name-target", type=float, default=.95)
    run.add_argument("--min-available-gib", type=float, default=40,
                     help="Refuse inference below this MemAvailable floor (default: 40 GiB)")
    run.add_argument("--min-free-gib", type=float, default=24,
                     help="Refuse inference below this MemFree floor (default: 24 GiB)")
    watch = sub.add_parser("watch", parents=[run], add_help=False,
                           help="Foreground opt-in polling; evaluate when input files settle")
    watch.add_argument("--poll", type=float, default=5)
    watch.add_argument("--settle", type=float, default=10)
    refine = sub.add_parser("refine", parents=[run], add_help=False,
        help="Re-read type/number ROIs with an independent reference; reuse name/HP")
    refine.add_argument("parent_run", type=Path)
    refine.add_argument("--type-reference", type=Path, required=True)
    refine.add_argument("--guided-card", action="store_true",
        help="Acknowledge upright, tightly framed input requirement")
    refine.add_argument("--type-roi", nargs=4, type=float, default=TYPE_ROI)
    refine.add_argument("--number-roi", nargs=4, type=float, default=NUMBER_ROI)
    report = sub.add_parser("report", help="Re-score saved outputs with current labels; no inference")
    report.add_argument("run_dir", type=Path)
    report.add_argument("--truth", type=Path)
    report.add_argument("--name-target", type=float, default=.95)
    compare = sub.add_parser("compare", help="Validate and compare frozen before/after runs")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    compare.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.root = args.root.expanduser().resolve()
    if hasattr(args, "name_target") and not 0 < args.name_target <= 1:
        parser.error("--name-target must be in (0, 1]")
    if getattr(args, "limit", None) is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if args.command in {"run", "watch", "refine"}:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", args.label):
            parser.error("--label must use letters, digits, dots, underscores or hyphens")
        if args.timeout <= 0 or args.gap < 0 or args.idle_timeout < 0:
            parser.error("Timeout must be positive and gap/idle timeout nonnegative")
        if args.min_available_gib < 0 or args.min_free_gib < 0:
            parser.error('Memory floors must be nonnegative')
        if len(set(args.resolutions)) != len(args.resolutions):
            parser.error("Duplicate resolutions are not allowed")
        args.base_url = args.base_url.rstrip("/")
        if args.command == "watch" and (args.poll <= 0 or args.settle < 0):
            parser.error("--poll must be positive and --settle nonnegative")
        if args.command == "refine":
            if not args.guided_card:
                parser.error("refine requires --guided-card: ROIs do not automatically detect a card")
            try:
                roi_box((1, 1), args.type_roi)
                roi_box((1, 1), args.number_roi)
            except ValueError as exc:
                parser.error(str(exc))
            if args.limit is not None or args.resolutions != list(RESOLUTIONS):
                parser.error("refine uses the parent's exact coverage; limit/resolutions cannot override it")
    try:
        with workspace_lock(args.root):
            if args.command == "init":
                print(initialize(args.root))
            elif args.command == "prepare":
                initialize(args.root)
                output = new_directory(args.root / "images", "prepared")
                entries, errors = prepare_images(args.root / "input", output, RESOLUTIONS, args.limit)
                write_json(output / "manifest.json", {"inputs": entries, "input_errors": errors})
                print(output)
            elif args.command == "run":
                print(run_benchmark(args))
            elif args.command == "watch":
                watch_inputs(args)
            elif args.command == "refine":
                print(refine_benchmark(args))
            elif args.command == "report":
                generate_report(args.run_dir.resolve(), args.truth or default_truth_path(args.root), args.name_target)
                print(args.run_dir / "report.md")
            elif args.command == "compare":
                compare_runs(args.before.resolve(), args.after.resolve(), args.output.resolve())
                print(args.output)
        return 0
    except (OSError, ValueError, RuntimeError, requests.RequestException, KeyboardInterrupt) as exc:
        print(f"ERROR: {exc or 'Interrupted'}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
