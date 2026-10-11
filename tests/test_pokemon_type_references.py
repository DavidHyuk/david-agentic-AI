# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Verify independent reference crops and their explicit provenance/labels."""
import csv
import json

from PIL import Image, ImageDraw

import pokemon_type_references as references


def test_reference_icons_keep_source_pixels_and_all_eleven_labels(tmp_path):
    page = Image.new("RGB", (1280, 1600), "white")
    draw = ImageDraw.Draw(page)
    for index, center in enumerate(references.ICON_CENTERS.values()):
        draw.rectangle(references.icon_box(page.size, center), fill=(index * 20, 30, 50))
    path = tmp_path / "official-page.png"
    page.save(path)
    before = path.read_bytes()
    legend = references.build_reference(path, tmp_path / "references")
    assert path.read_bytes() == before
    assert Image.open(legend).size == (600, 405)
    provenance = json.loads((legend.parent / "provenance.json").read_text())
    assert len(provenance["labels"]) == 11
    assert provenance["legend_sha256"] == references.digest(legend)
    for record in provenance["labels"]:
        assert Image.open(record["image_path"]).tobytes() == page.crop(record["source_box"]).tobytes()
        assert record["source_url"] == references.SOURCE_URL and record["page_number"] == 4
    with (legend.parent / "type_labels.csv").open(encoding="utf-8-sig") as stream:
        assert {r["pokemon_type"] for r in csv.DictReader(stream)} == set(references.ICON_CENTERS)
