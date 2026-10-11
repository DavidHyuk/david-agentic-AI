#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Download and label eleven independent official TCG symbol references.

Use the fixed fourth page of the official SWSH11 rulebook. No evaluation-card
images, model downloads, training, inference or ground-truth edits occur here.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

from PIL import Image, ImageDraw, ImageFont

SOURCE_URL = "https://assets.pokemon.com/assets/cms2/pdf/trading-card-game/rulebook/swsh11_rulebook_en.pdf"
ICON_CENTERS = {
    "Grass": (293 / 1280, 550 / 1600), "Fire": (646 / 1280, 550 / 1600),
    "Water": (1000 / 1280, 550 / 1600), "Lightning": (293 / 1280, 770 / 1600),
    "Psychic": (646 / 1280, 770 / 1600), "Fighting": (1000 / 1280, 770 / 1600),
    "Darkness": (293 / 1280, 991 / 1600), "Metal": (646 / 1280, 991 / 1600),
    "Fairy": (1000 / 1280, 991 / 1600), "Dragon": (293 / 1280, 1212 / 1600),
    "Colorless": (646 / 1280, 1212 / 1600)}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def icon_box(size, center):
    """Coordinates are tied to this official page layout, not target-card labels."""
    width, height = size
    cx, cy = center
    return (round((cx - 23 / 1280) * width), round((cy - 23 / 1600) * height),
            round((cx + 23 / 1280) * width), round((cy + 23 / 1600) * height))


def build_reference(page_path, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype("DejaVuSans.ttf", 20)
    legend = Image.new("RGB", (600, 405), "white")
    draw = ImageDraw.Draw(legend)
    labels = []
    with Image.open(page_path) as page:
        for index, (label, center) in enumerate(ICON_CENTERS.items()):
            box = icon_box(page.size, center)
            if not (0 <= box[0] < box[2] <= page.width and 0 <= box[1] < box[3] <= page.height):
                raise ValueError("Reference icon lies outside the rendered page")
            icon = page.crop(box).convert("RGB")
            path = output / "icons" / (label + ".png")
            path.parent.mkdir(exist_ok=True)
            icon.save(path)
            # Rendering at 3200px produces 92px icons. Downscale only, never invent detail.
            icon.thumbnail((92, 92), Image.Resampling.LANCZOS)
            x, y = (index % 4) * 150, (index // 4) * 135
            legend.paste(icon, (x + (150 - icon.width) // 2, y + 4))
            draw.text((x + 75, y + 105), label, fill="black", font=font, anchor="mm")
            labels.append({"pokemon_type": label, "image_path": str(path.resolve()),
                "image_sha256": digest(path), "source_url": SOURCE_URL, "page_number": 4,
                "source_box": list(box), "label_source": "Official adjacent printed type label"})
    legend_path = output / "tcg-type-reference.png"
    legend.save(legend_path)
    with (output / "type_labels.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(labels[0]))
        writer.writeheader()
        writer.writerows(labels)
    provenance = {"source_url": SOURCE_URL, "page_number": 4,
        "rendered_page_sha256": digest(page_path), "legend_sha256": digest(legend_path),
        "labels": labels, "scope": "11 independent official symbol examples, not evaluation-card ground truth",
        "limitations": "One icon per type; fixed SWSH11 page layout; no training or held-out accuracy claim"}
    (output / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
    return legend_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
        default=Path(__file__).resolve().parent.parent / "pokemon-card-benchmark" / "references")
    parser.add_argument("--pdf", type=Path, help="Optional local official SWSH11 PDF for offline use")
    args = parser.parse_args(argv)
    args.output = args.output.expanduser().resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    pdf = args.pdf.expanduser().resolve() if args.pdf else args.output / "pokemon-tcg-rulebook-swsh11-en.pdf"
    if not pdf.exists():
        if args.pdf:
            parser.error("The specified offline PDF does not exist")
        with urllib.request.urlopen(SOURCE_URL, timeout=30) as response:
            content = response.read()
        if not content.startswith(b"%PDF"):
            raise ValueError("Official source did not return a PDF")
        pdf.write_bytes(content)
    prefix = args.output / "energy-types-page"
    subprocess.run(["pdftoppm", "-f", "4", "-singlefile", "-scale-to", "3200", "-png",
                    str(pdf), str(prefix)], check=True, timeout=60)
    path = build_reference(prefix.with_suffix(".png"), args.output)
    provenance_path = args.output / "provenance.json"
    provenance = json.loads(provenance_path.read_text())
    provenance.update(pdf_sha256=digest(pdf), renderer="pdftoppm page 4, scale-to 3200")
    provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
