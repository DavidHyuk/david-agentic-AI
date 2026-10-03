# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Verify diagnostic containment and refusal before launching under pressure."""

import argparse
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / 'local-model/eval/guarded_diagnostic.py'
SPEC = importlib.util.spec_from_file_location('guarded_diagnostic', PATH)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


def sample(available=20 * 1024**3, pressure=0, swap=15 * 1024**3):
    return {'MemAvailable': available, 'SwapFree': swap, 'memory_full_avg10': pressure}


@pytest.mark.parametrize('value,reason', [
    (sample(available=11 * 1024**3), 'headroom'),
    (sample(pressure=1.1), 'pressure'),
    (sample(swap=14 * 1024**3), 'swap'),
])
def test_pressure_and_swap_are_distinct_risks(value, reason):
    assert reason in guard.risk_reason(value, 12 * 1024**3, 15 * 1024**3)


def test_command_preserves_literal_arguments_and_kernel_limits():
    args = guard.launch_arguments('test.service', ['python3', '-c', 'print("$(literal)")'], 1024, 90)
    assert args[-3:] == ['python3', '-c', 'print("$(literal)")']
    for value in ['MemoryMax=1024M', 'MemoryHigh=768M', 'MemorySwapMax=0',
                  'RuntimeMaxSec=90', 'KillMode=control-group', 'OOMPolicy=stop',
                  'CUDA_VISIBLE_DEVICES=-1']:
        assert value in args
    assert 'hermes-vllm.service' not in args


def test_pressure_refuses_launch_and_writes_durable_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, 'read_resources', lambda: sample(available=1))
    monkeypatch.setattr(guard, 'command_output', lambda *_: pytest.fail('must not launch'))
    out = tmp_path / 'run'
    args = argparse.Namespace(command=['--', 'python3', '-c', 'pass'], output_dir=out,
                              reserve_gib=12, memory_mib=1024, seconds=90)
    assert guard.run(args) == 2
    record = json.loads((out / 'manifest.json').read_text())
    assert record['status'] == 'refused'
    assert 'headroom' in record['reason']
    assert not (out / 'manifest.json.tmp').exists()


def test_missing_kernel_visibility_refuses_before_launch(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, 'read_resources', sample)
    calls = []

    def reject(args):
        calls.append(args)
        raise RuntimeError('kernel journal denied')

    monkeypatch.setattr(guard, 'command_output', reject)
    args = argparse.Namespace(command=['python3', '-c', 'pass'], output_dir=tmp_path / 'run',
                              reserve_gib=12, memory_mib=1024, seconds=90)
    assert guard.run(args) == 2
    assert len(calls) == 1 and calls[0][0] == 'journalctl'
    assert json.loads((args.output_dir / 'manifest.json').read_text())['status'] == 'stopped'


def test_user_interrupt_stops_only_own_unit(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, 'read_resources', sample)
    monkeypatch.setattr(guard, 'command_output', lambda *_: '')
    properties = {'MemoryMax': str(1024**3), 'MemorySwapMax': '0', 'ActiveState': 'active'}
    monkeypatch.setattr(guard, 'unit_properties', lambda *_: properties)
    monkeypatch.setattr(guard.time, 'sleep', lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return argparse.Namespace(stdout='', stderr='')

    monkeypatch.setattr(guard.subprocess, 'run', run)
    args = argparse.Namespace(command=['python3', '-c', 'pass'], output_dir=tmp_path / 'run',
                              reserve_gib=12, memory_mib=1024, seconds=90)
    assert guard.run(args) == 2
    stops = [x for x in calls if x[:3] == ['systemctl', '--user', 'stop']]
    assert len(stops) == 1 and stops[0][-1].startswith('hermes-cpu-diagnostic-')
    assert json.loads((args.output_dir / 'manifest.json').read_text())['reason'] == 'user interrupted supervisor'


def test_finished_command_retains_peak_and_is_cleaned_up(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, 'read_resources', sample)
    monkeypatch.setattr(guard, 'command_output', lambda *_: '')
    properties = {'MemoryMax': str(1024**3), 'MemorySwapMax': '0', 'ActiveState': 'active',
                  'SubState': 'exited', 'Result': 'success', 'ExecMainStatus': '0', 'MemoryPeak': '123456'}
    monkeypatch.setattr(guard, 'unit_properties', lambda *_: properties)
    calls = []
    monkeypatch.setattr(guard.subprocess, 'run', lambda argv, **_: (calls.append(argv) or argparse.Namespace(stdout='', stderr='')))
    args = argparse.Namespace(command=['python3', '-c', 'pass'], output_dir=tmp_path / 'run',
                              reserve_gib=12, memory_mib=1024, seconds=90)
    assert guard.run(args) == 0
    assert json.loads((args.output_dir / 'manifest.json').read_text())['final']['MemoryPeak'] == '123456'
    assert any(x[:3] == ['systemctl', '--user', 'stop'] for x in calls)
