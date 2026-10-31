#!/usr/bin/env python3
"""Exercise stop-v1 against a prepared firmware's control code, without board IO."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from analyze_stop_trials import CASES

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / 'firmware/esp32-audio/tests/stop_matrix.cc'
OFFSETS = (5, 55, 100, 150, 195)
LANES = ('move', 'water', 'bubbles')


def samples(binary, event, source, phase, offset):
    output = subprocess.check_output([binary, event, source, phase, str(offset)], text=True)
    return [line.split() for line in output.splitlines()]


def exercise(binary, case, offset):
    sequence = case.event in ('cancel', 'source_disconnect')
    source = next(iter(case.sources.values())) if sequence else next(iter(case.sources))
    trigger = offset + (1000 if case.phase == 'waiting' else 0)
    reconnect = trigger + 2500
    # With no release packet, the last heartbeat was at t=0 and the web lease is 2 s.
    cutoff = 2000 if case.event == 'web_network_loss' else trigger
    initial_starts = len(case.sources)
    rows = samples(binary, case.event, source, case.phase, offset)
    for tick, row in enumerate(rows):
        now, move, water, bubbles, active, result, starts, owner, ignition, wifi, voice = row
        now = int(now)
        if now != tick * 5 or int(starts) != initial_starts or ignition != '0':
            raise ValueError(f'{case.id} at {now}: unexpected start, channel or sample gap')
        for channel, actual in zip(LANES, (move, water, bubbles)):
            limit = cutoff if channel not in case.keep else {'move': 6000, 'bubbles': 5000}[channel]
            if sequence:
                limit = min(limit, 1000)
            expected = case.sources.get(channel, 'none') if now < limit else 'none'
            if actual != expected:
                raise ValueError(f'{case.id} at {now}: {channel} owned by {actual}, expected {expected}')
        if sequence:
            expected_result = 'cancelled' if now >= trigger else 'waiting' if now >= 1000 else 'running'
            if bool(int(active)) != (now < trigger) or result != expected_result:
                raise ValueError(f'{case.id} at {now}: unexpected plan state {active}/{result}')
        if now >= reconnect and (int(owner) == 0 or (wifi, voice) != ('1', '1')):
            raise ValueError(f'{case.id} at {now}: connections did not recover')
    if not rows or int(rows[-1][0]) != reconnect + 6000:
        raise ValueError(f'{case.id}: missing recovery window')


def run(source):
    board = source / 'main/boards/bread-compact-wifi'
    version = re.search(r'set\(PROJECT_VER "([^"]+)"\)', (source/'CMakeLists.txt').read_text()).group(1)
    flags = ['-fsanitize=address,undefined', '-Wall', '-Wextra', '-Werror', '-I', str(board)]
    with tempfile.TemporaryDirectory() as temp:
        obj, binary = Path(temp)/'water.o', Path(temp)/'stop-matrix'
        subprocess.run(['cc', '-std=c11', *flags, '-c', board/'water_policy.c', '-o', obj], check=True)
        subprocess.run(['c++', '-std=c++17', *flags, HARNESS, obj, '-o', binary], check=True)
        for source_kind in ('web', 'voice'):
            control = samples(binary, 'sequence_control', source_kind, 'active', 100)
            if control[1200//5][3] != source_kind or control[-1][5:7] != ['completed', '3']:
                raise ValueError(f'{source_kind} no-stop control did not run the second step')
        blackout = samples(binary, 'sequence_web_blackout', 'web', 'waiting', 100)
        # Sender disappears at 1100 ms in the inter-step wait, last heartbeat 1000 ms.
        for tick, row in enumerate(blackout):
            now = tick * 5
            expected = 'running' if now < 1000 or 1200 <= now < 3000 else 'waiting' if now < 1200 else 'cancelled'
            if (row[5] != expected or row[3] != ('web' if expected == 'running' else 'none')
                    or int(row[6]) != (2 if now < 1200 else 3)):
                raise ValueError(f'web blackout at {now}: unexpected step or output')
        for case in CASES:
            for offset in OFFSETS:
                exercise(binary, case, offset)
    inputs = ['control_sessions.h', 'action_guard.h', 'action_plan.h', 'show_draft.h',
              'water_guard.h', 'water_policy.c', 'water_policy.h']
    return {'matrix': 'stop-v1', 'source_version': version, 'evidence_kind': 'host_control_replay',
            'passed_cases': [c.id for c in CASES], 'trigger_offsets_ms': OFFSETS, 'tick_ms': 5,
            'reconnected_at_ms_after_trigger': 2500, 'observed_ms_after_reconnect': 6000,
            'second_step_without_stop': ['web', 'voice'], 'physical_trials_added': 0,
            'web_blackout_during_wait_ms': {'last_heartbeat': 1000, 'network_lost': 1100,
                                             'second_step_started': 1200, 'session_expired_and_stopped': 3000},
            'prepared_source_sha256': {name: hashlib.sha256((board/name).read_bytes()).hexdigest() for name in inputs}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='prepared Xiaozhi source tree')
    args = parser.parse_args()
    print(json.dumps(run(args.source.resolve()), indent=2))
