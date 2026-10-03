# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Read selected GGUF metadata without mapping weights or retaining tokenizer arrays."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
from typing import BinaryIO


SCALARS = {0: 'B', 1: 'b', 2: 'H', 3: 'h', 4: 'I', 5: 'i', 6: 'f',
           7: '?', 10: 'Q', 11: 'q', 12: 'd'}
HEADER_LIMIT = 64 * 1024**2
STRING_LIMIT = 16 * 1024**2
ARRAY_LIMIT = 1_000_000


class HeaderReader:
    def __init__(self, source: BinaryIO):
        self.source = source
        position = source.tell()
        source.seek(0, 2)
        self.size = source.tell()
        source.seek(position)

    def check(self, count: int) -> None:
        if count < 0 or self.source.tell() + count > min(self.size, HEADER_LIMIT):
            raise ValueError('GGUF metadata is truncated or exceeds the 64 MiB header limit')

    def read(self, count: int) -> bytes:
        self.check(count)
        data = self.source.read(count)
        if len(data) != count:
            raise ValueError('truncated GGUF metadata')
        return data

    def scalar(self, kind: int):
        if kind not in SCALARS:
            raise ValueError(f'unsupported GGUF scalar type: {kind}')
        fmt = '<' + SCALARS[kind]
        return struct.unpack(fmt, self.read(struct.calcsize(fmt)))[0]

    def skip(self, count: int) -> None:
        self.check(count)
        self.source.seek(count, 1)

    def string(self, retain: bool):
        count = self.scalar(10)
        if count > STRING_LIMIT:
            raise ValueError('GGUF string exceeds 16 MiB limit')
        if retain:
            return self.read(count).decode('utf-8')
        self.skip(count)
        return None

    def value(self, kind: int, retain: bool):
        if kind in SCALARS:
            if retain:
                return self.scalar(kind)
            self.skip(struct.calcsize('<' + SCALARS[kind]))
            return None
        if kind == 8:
            return self.string(retain)
        if kind != 9:
            raise ValueError(f'unsupported GGUF value type: {kind}')
        element = self.scalar(4)
        count = self.scalar(10)
        if count > ARRAY_LIMIT or element == 9 or element not in (*SCALARS, 8):
            raise ValueError('unsupported or oversized GGUF array')
        if retain and count <= 128:
            return [self.value(element, True) for _ in range(count)]
        if element in SCALARS:
            self.skip(count * struct.calcsize('<' + SCALARS[element]))
        else:
            for _ in range(count):
                self.string(False)
        return {'array_type': element, 'count': count, 'contents_retained': False} if retain else None


def read_metadata(source: BinaryIO, include_tensors: bool = False) -> dict:
    reader = HeaderReader(source)
    if reader.read(4) != b'GGUF':
        raise ValueError('expected a little-endian GGUF file')
    version = reader.scalar(4)
    if version not in (2, 3):
        raise ValueError(f'unsupported GGUF version: {version}')
    tensors, fields = reader.scalar(10), reader.scalar(10)
    if fields > 10_000:
        raise ValueError('GGUF metadata field count exceeds 10,000')
    metadata = {}
    for _ in range(fields):
        name = reader.string(True)
        kind = reader.scalar(4)
        retain = name.startswith(('general.', 'qwen', 'split.'))
        value = reader.value(kind, retain)
        if retain:
            metadata[name] = value
    result = {'version': version, 'tensor_count': tensors, 'field_count': fields,
              'metadata_end_offset': source.tell(), 'metadata': metadata,
              'tensor_payload_read': False}
    if not include_tensors:
        return result
    if tensors > 10_000:
        raise ValueError('tensor descriptor count exceeds 10,000')
    types = {}
    total_elements = 0
    selected = []
    for _ in range(tensors):
        name = reader.string(True)
        dimensions = reader.scalar(4)
        if not 1 <= dimensions <= 4:
            raise ValueError('invalid tensor dimension count')
        shape = [reader.scalar(10) for _ in range(dimensions)]
        kind, offset = reader.scalar(4), reader.scalar(10)
        elements = 1
        for value in shape:
            if value == 0 or value > 2**40:
                raise ValueError('invalid tensor dimension')
            elements *= value
        total_elements += elements
        types[kind] = types.get(kind, 0) + 1
        if name == 'per_layer_token_embd.weight':
            selected.append({'name': name, 'shape': shape, 'ggml_type': kind,
                             'elements': elements, 'data_offset': offset})
    result.update(tensor_types=types, tensor_elements=total_elements,
                  selected_tensors=selected, descriptors_end_offset=source.tell())
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tensor-summary', action='store_true')
    parser.add_argument('path', type=Path, nargs='+')
    args = parser.parse_args()
    results = []
    for path in args.path:
        with path.open('rb') as source:
            result = read_metadata(source, args.tensor_summary)
        result['file'] = path.name
        results.append(result)
    print(json.dumps(results[0] if len(results) == 1 else results, indent=2))


if __name__ == '__main__':
    main()
