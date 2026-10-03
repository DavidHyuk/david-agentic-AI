# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Run a CPU-only diagnostic in a bounded systemd cgroup with durable telemetry."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid


KERNEL_FAILURE = re.compile(r"NVRM:.*(?:Xid|NV_ERR_NO_MEMORY)|oom-kill|Out of memory:|Kernel panic|GPU has fallen", re.I)


def read_resources() -> dict:
    values = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith(('MemAvailable:', 'SwapFree:')):
            values[line.split(':')[0]] = int(line.split()[1]) * 1024
    pressure = Path('/proc/pressure/memory').read_text()
    values['memory_full_avg10'] = float(re.search(r'^full avg10=([\d.]+)', pressure, re.M)[1])
    values['utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
    return values


def risk_reason(sample: dict, reserve_bytes: int, initial_swap_free: int) -> str | None:
    if sample['MemAvailable'] < reserve_bytes:
        return 'available memory below reserved headroom'
    if sample['memory_full_avg10'] > 1:
        return 'memory pressure full avg10 exceeds 1'
    if initial_swap_free - sample['SwapFree'] > 256 * 1024**2:
        return 'new swap consumption exceeds 256 MiB'
    return None


def launch_arguments(unit: str, command: list[str], memory_mib: int, seconds: int) -> list[str]:
    return [
        'systemd-run', '--user', '--unit', unit,
        '--property', 'MemoryAccounting=yes',
        '--property', f'MemoryHigh={memory_mib * 3 // 4}M',
        '--property', f'MemoryMax={memory_mib}M',
        '--property', 'MemorySwapMax=0',
        '--property', 'CPUQuota=100%',
        '--property', 'IOWeight=10',
        '--property', 'Nice=10',
        '--property', 'OOMPolicy=stop',
        '--property', 'KillMode=control-group',
        '--property', 'RemainAfterExit=yes',
        '--property', 'TimeoutStopSec=5',
        '--property', f'RuntimeMaxSec={seconds}',
        '--property', f'WorkingDirectory={Path.cwd()}',
        '--setenv', 'CUDA_VISIBLE_DEVICES=-1',
        '--setenv', 'OMP_NUM_THREADS=1',
        '--setenv', 'OPENBLAS_NUM_THREADS=1',
        '--', *command,
    ]


def command_output(args: list[str]) -> str:
    result = subprocess.run(args, text=True, capture_output=True, timeout=10)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f'command failed: {args[0]}')
    return result.stdout


def unit_properties(unit: str) -> dict:
    body = command_output(['systemctl', '--user', 'show', unit,
                           '-p', 'ActiveState', '-p', 'SubState', '-p', 'Result', '-p', 'ExecMainStatus',
                           '-p', 'MemoryCurrent', '-p', 'MemoryPeak', '-p', 'MemoryMax',
                           '-p', 'MemoryHigh', '-p', 'MemorySwapMax', '-p', 'ControlGroup'])
    return dict(line.split('=', 1) for line in body.splitlines() if '=' in line)


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as handle:
        json.dump(value, handle, indent=2)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def run(args: argparse.Namespace) -> int:
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        raise ValueError('provide a CPU-only diagnostic command after --')
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    unit = f'hermes-cpu-diagnostic-{uuid.uuid4().hex[:12]}.service'
    start = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    initial = read_resources()
    reserve = args.reserve_gib * 1024**3
    manifest = {'unit': unit, 'command': command, 'initial': initial,
                'memory_mib': args.memory_mib, 'runtime_seconds': args.seconds,
                'reserve_gib': args.reserve_gib, 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                'status': 'preflight'}
    write_json(output / 'manifest.json', manifest)
    reason = risk_reason(initial, reserve, initial['SwapFree'])
    if reason:
        manifest.update(status='refused', reason=reason)
        write_json(output / 'manifest.json', manifest)
        print(reason, flush=True)
        return 2
    launched = False
    final = {}
    try:
        # Require readable kernel logs before launching; missing evidence fails closed.
        command_output(['journalctl', '-k', '--since', start, '-n', '100', '--no-pager'])
        argv = launch_arguments(unit, command, args.memory_mib, args.seconds)
        manifest['launch_argv'] = argv
        write_json(output / 'manifest.json', manifest)
        command_output(argv)
        launched = True
        final = unit_properties(unit)
        if int(final['MemoryMax']) != args.memory_mib * 1024**2 or int(final['MemorySwapMax']) != 0:
            raise RuntimeError('systemd memory bounds were not applied')
        manifest.update(status='running', applied_limits=final)
        write_json(output / 'manifest.json', manifest)
        deadline = time.monotonic() + args.seconds + 10
        kernel_at = 0.0
        while True:
            sample = read_resources()
            final = unit_properties(unit)
            sample['unit'] = final
            with (output / 'telemetry.jsonl').open('a') as handle:
                handle.write(json.dumps(sample) + '\n')
                handle.flush()
                os.fsync(handle.fileno())
            reason = risk_reason(sample, reserve, initial['SwapFree'])
            if time.monotonic() - kernel_at >= 5:
                kernel_at = time.monotonic()
                kernel = command_output(['journalctl', '-k', '--since', start, '-n', '100', '--no-pager'])
                if KERNEL_FAILURE.search(kernel):
                    (output / 'kernel-risk.log').write_text(kernel)
                    reason = 'new GPU/kernel failure'
            if reason:
                raise RuntimeError(reason)
            if final['ActiveState'] in ('inactive', 'failed') or final.get('SubState') == 'exited':
                break
            if time.monotonic() > deadline:
                raise RuntimeError('supervisor deadline exceeded')
            time.sleep(1)
        manifest.update(status='completed' if final.get('Result') == 'success' else 'failed', final=final)
    except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
        manifest.update(status='stopped', reason=str(exc), final=final)
    except KeyboardInterrupt:
        manifest.update(status='stopped', reason='user interrupted supervisor', final=final)
    finally:
        if launched:
            subprocess.run(['systemctl', '--user', 'stop', unit], capture_output=True, timeout=10)
            logs = subprocess.run(['journalctl', '--user', '-u', unit, '--no-pager'], capture_output=True, text=True, timeout=10)
            (output / 'child.log').write_text(logs.stdout + logs.stderr)
        write_json(output / 'manifest.json', manifest)
    print(json.dumps(manifest), flush=True)
    return 0 if manifest['status'] == 'completed' and final.get('ExecMainStatus') == '0' else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--memory-mib', type=int, default=1024)
    parser.add_argument('--seconds', type=int, default=90)
    parser.add_argument('--reserve-gib', type=int, default=12)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.memory_mib < 64 or args.seconds < 1 or args.reserve_gib < 1:
        parser.error('memory >=64 MiB, seconds >=1 and reserve >=1 GiB are required')
    return run(args)


if __name__ == '__main__':
    raise SystemExit(main())
