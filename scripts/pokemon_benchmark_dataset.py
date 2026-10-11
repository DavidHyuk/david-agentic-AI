#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Build a private 30-card dataset from four photos and 26 labeled public scans.

The community PokemonTCG metadata is not a camera dataset. Download only card
assets and metadata; never change existing photos, labels or serving settings.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image, ImageOps

TYPES = ('Grass', 'Fire', 'Water', 'Lightning', 'Psychic', 'Fighting',
         'Darkness', 'Metal', 'Dragon', 'Colorless', 'Fairy')
# Human geometry annotations after EXIF transpose, not inferred from card labels.
PHOTO_POLYGONS = {
    '20261009_215106.jpg': [(29/300,37/400),(265/300,32/400),(263/300,357/400),(28/300,364/400)],
    '20261009_215130.jpg': [(9/300,25/400),(281/300,30/400),(284/300,389/400),(12/300,390/400)],
    '20261009_215145.jpg': [(19/300,24/400),(279/300,19/400),(280/300,377/400),(16/300,375/400)],
    '20261009_215215.jpg': [(17/300,20/400),(285/300,20/400),(283/300,387/400),(18/300,388/400)],
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def select_cards(catalogs, count=26):
    """Stratify deterministically across eleven single TCG types and unique names."""
    pools = {t: [] for t in TYPES}
    for set_id, cards in catalogs.items():
        for card in cards:
            types = card.get('types', [])
            if (card.get('supertype') == 'Pokémon' and len(types) == 1
                    and types[0] in pools and str(card.get('hp', '')).isdigit()
                    and str(card.get('number', '')).isdigit()):
                pools[types[0]].append((set_id, card))
    chosen, names = [], set()
    while len(chosen) < count:
        progress = False
        for type_name in TYPES:
            while pools[type_name] and pools[type_name][0][1]['name'] in names:
                pools[type_name].pop(0)
            if pools[type_name] and len(chosen) < count:
                set_id, card = pools[type_name].pop(0)
                chosen.append((set_id, card)); names.add(card['name']); progress = True
        if not progress:
            raise ValueError('Not enough unique single-type Pokemon cards')
    if count >= len(TYPES) and {c['types'][0] for _, c in chosen} != set(TYPES):
        raise ValueError('Missing type coverage in public selection')
    return chosen


def printed_number(set_id, card, set_info):
    """SWSH1 prints three digits; selected SM12 numbers use unpadded digits."""
    number = str(card['number'])
    if set_id == 'swsh1':
        number = number.zfill(3)
    elif set_id != 'sm12':
        raise ValueError('Unreviewed set numbering convention')
    total = str(set_info['printedTotal'])
    return number + '/' + total


def fetch(session, url, path):
    """Cache exact downloaded bytes without replacing previous source evidence."""
    if not path.exists():
        response = session.get(url, timeout=(10, 45))
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_bytes(response.content)
        temporary.replace(path)
    return path.read_bytes()


def build_dataset(root, output):
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / 'manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        for card in manifest['cards']:
            if sha256(card['image_path']) != card['source_sha256']:
                raise ValueError('Existing dataset source changed')
        return manifest_path
    with (root / 'pokebot_ground_truth.csv').open(encoding='utf-8-sig', newline='') as f:
        truth = {r['filename']: r for r in csv.DictReader(f)}
    cards = []
    for filename, polygon in PHOTO_POLYGONS.items():
        source = root / 'input' / filename
        label = truth[filename]
        with Image.open(source) as image:
            size = ImageOps.exif_transpose(image).size
        cards.append({'filename': filename, 'image_path': str(source.resolve()),
            'source_sha256': sha256(source), 'source_group': 'smartphone_ko',
            'language': 'ko', 'card_polygon': polygon, 'original_size': list(size),
            'ground_truth': {k: label[k] for k in ('pokemon_name','pokemon_type','hp','card_number')},
            'label_source': 'Human pokebot_ground_truth.csv',
            'geometry_source': 'Human quadrilateral annotation of EXIF-transposed photo'})
    with requests.Session() as session:
        session.headers['User-Agent'] = 'david-pokemon-card-benchmark/1.0'
        commit_path = output / 'sources' / 'commit.json'
        commit = json.loads(fetch(session,
            'https://api.github.com/repos/PokemonTCG/pokemon-tcg-data/commits/master', commit_path))['sha']
        prefix = 'https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/' + commit
        catalogs = {set_id: json.loads(fetch(session, prefix + '/cards/en/' + set_id + '.json',
            output / 'sources' / (set_id + '.json'))) for set_id in ('swsh1', 'sm12')}
        sets = {s['id']: s for s in json.loads(fetch(session, prefix + '/sets/en.json',
            output / 'sources' / 'sets.json'))}
        for set_id, card in select_cards(catalogs):
            filename = 'public-' + card['id'] + '.png'
            source = output / 'images' / filename
            fetch(session, card['images']['large'], source)
            with Image.open(source) as image:
                image.verify()
            with Image.open(source) as image:
                size = list(image.size)
            cards.append({'filename': filename, 'image_path': str(source.resolve()),
                'source_sha256': sha256(source), 'source_group': 'public_scan_en',
                'language': 'en', 'card_polygon': [[0,0],[1,0],[1,1],[0,1]],
                'original_size': size, 'card_id': card['id'],
                'ground_truth': {'pokemon_name': card['name'], 'pokemon_type': card['types'][0],
                    'hp': card['hp'], 'card_number': printed_number(set_id, card, sets[set_id])},
                'image_url': card['images']['large'],
                'label_source': prefix + '/cards/en/' + set_id + '.json',
                'number_convention': 'swsh1: 3 digits; sm12: printed number, no padding',
                'geometry_source': 'Full digital card image rectangle'})
            print('Downloaded', card['id'], card['name'], size, flush=True)
    manifest = {'schema_version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'dataset': '4 Korean smartphone photos + 26 English digital card scans',
        'source_repository': 'https://github.com/PokemonTCG/pokemon-tcg-data',
        'source_commit': commit, 'cards': cards,
        'limitations': ['Community metadata, not NVIDIA/M5Stack camera ground truth',
            'Public digital scans and Korean smartphone photos must be reported separately',
            'No upscale: native scans may cap the requested 2MP frame size',
            'Card corners are human annotations, not automatic card detection',
            'Downloaded card artwork retains its owners\u2019 copyright; private evaluation only']}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    with (output / 'ground_truth.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=('filename','pokemon_name','pokemon_type','hp','card_number'))
        writer.writeheader()
        writer.writerows({'filename': c['filename'], **c['ground_truth']} for c in cards)
    return manifest_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.home()/'workspace/David-Agent/pokemon-card-benchmark')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    print(build_dataset(root, (args.output or root/'datasets/tcg30').expanduser().resolve()))


if __name__ == '__main__':
    main()
