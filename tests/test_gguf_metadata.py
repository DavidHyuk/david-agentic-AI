# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Ensure bounded GGUF inspection skips large tokenizer arrays and all tensor data."""

import importlib.util
import io
from pathlib import Path
import struct

import pytest

PATH = Path(__file__).resolve().parents[1] / 'local-model/eval/gguf_metadata.py'
SPEC = importlib.util.spec_from_file_location('gguf_metadata', PATH)
metadata = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(metadata)


def string(text):
    value = text.encode()
    return struct.pack('<Q', len(value)) + value


def header(fields):
    return b'GGUF' + struct.pack('<IQQ', 3, 100, len(fields)) + b''.join(fields)


def field(key, kind, value):
    return string(key) + struct.pack('<I', kind) + value


def test_skips_vocab_and_stops_before_tensor_data():
    body = header([
        field('general.architecture', 8, string('qwen35moe')),
        field('tokenizer.ggml.tokens', 9, struct.pack('<IQ', 8, 1000) + string('token') * 1000),
        field('qwen35moe.block_count', 4, struct.pack('<I', 40)),
    ])
    source = io.BytesIO(body + b'not metadata or tensor bytes')
    result = metadata.read_metadata(source)
    assert result['metadata'] == {'general.architecture': 'qwen35moe', 'qwen35moe.block_count': 40}
    assert result['metadata_end_offset'] == len(body)
    assert source.read() == b'not metadata or tensor bytes'
    assert result['tensor_payload_read'] is False


def test_large_selected_array_keeps_only_description():
    source = io.BytesIO(header([field('qwen.values', 9, struct.pack('<IQ', 4, 200) + struct.pack('<I', 7) * 200)]))
    assert metadata.read_metadata(source)['metadata']['qwen.values'] == {
        'array_type': 4, 'count': 200, 'contents_retained': False}


def test_tensor_descriptors_do_not_read_large_weight_table():
    body = b'GGUF' + struct.pack('<IQQ', 3, 1, 0)
    body += string('per_layer_token_embd.weight') + struct.pack('<IQQIQ', 2, 160, 320001446, 6, 0)
    source = io.BytesIO(body + b'weights are never read')
    result = metadata.read_metadata(source, include_tensors=True)
    assert result['tensor_elements'] == 160 * 320001446
    assert result['selected_tensors'][0]['ggml_type'] == 6
    assert source.read() == b'weights are never read'
    assert result['tensor_payload_read'] is False


def test_oversized_tensor_descriptor_count_is_rejected():
    source = io.BytesIO(b'GGUF' + struct.pack('<IQQ', 3, 10001, 0))
    with pytest.raises(ValueError, match='descriptor'):
        metadata.read_metadata(source, include_tensors=True)


@pytest.mark.parametrize('body', [
    b'nope' + b'\0' * 20,
    b'GGUF' + struct.pack('<IQQ', 3, 0, 10_001),
    header([field('general.name', 8, struct.pack('<Q', metadata.STRING_LIMIT + 1))]),
    header([field('tokenizer.tokens', 9, struct.pack('<IQ', 8, metadata.ARRAY_LIMIT + 1))]),
    header([field('general.name', 8, struct.pack('<Q', 10) + b'a')]),
    header([field('general.bad', 99, b'')]),
])
def test_invalid_sizes_and_truncation_fail_before_large_allocation(body):
    with pytest.raises(ValueError):
        metadata.read_metadata(io.BytesIO(body))
