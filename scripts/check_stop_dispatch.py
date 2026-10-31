#!/usr/bin/env python3
"""Check synchronous stop receipts through actual MCP dispatch, without board IO."""
import argparse
import hashlib
import json
from pathlib import Path

from capture_lingxi import firmware_replay


def check(executable):
    def call(name, args=None, ms=0, rpc=1, **extra):
        return dict(name='self.tank.'+name, arguments=args or {}, elapsed_ms=ms, rpc_id=rpc, **extra)

    def receipt(wire):
        if 'error' in wire:
            return dict(result='rpc_error', message=wire['error']['message'])
        return json.loads(wire['result']['content'][0]['text'])

    stop = call('stop', defer=True)
    move = dict(direction='forward', duration_ms=30000)
    results = []

    def run(name, profile, commands, verify, await_stt=False):
        wires = firmware_replay(executable, profile, commands, await_stt=await_stt)
        receipts = [receipt(wire) for wire in wires[:-1]]
        passed = bool(verify(receipts, wires[-1]))
        results.append(dict(name=name, passed=passed, profile=profile, await_stt=await_stt,
                            commands=commands, receipts=receipts, final_state=wires[-1]))

    off = lambda state: not any(state['logical_outputs'].values()) and not state['sequence_active']
    run('active_sequence_then_new_input', 'corpus_sequence', [
        stop, dict(input_text='现在的状态', elapsed_ms=10), dict(flush=True, elapsed_ms=20), dict(inspect_ms=60000)],
        lambda r, s: len(r)==1 and r[0]['result']=='ok' and r[0]['operation']=='stop'
        and r[0]['uptime_ms']==1000 and off(r[0]) and off(s) and s['starts_this_boot']==1)

    run('later_input_action_survives_completed_stop', 'corpus_idle', [
        stop, dict(input_text='前进三十秒', elapsed_ms=10), call('move', move, 300, 2),
        dict(flush=True, elapsed_ms=310)],
        lambda r, s: len(r)==2 and r[0]['operation']=='stop' and r[0]['result']=='ok' and off(r[0])
        and r[1]['operation']=='move' and r[1]['result']=='accepted' and s['move_direction']=='forward'
        and s['starts_this_boot']==1 and s['recent_command']['operation']=='move')

    run('no_second_stop_callback', 'corpus_idle', [
        stop, call('move', move, 300, 2), dict(flush=True, elapsed_ms=310)],
        lambda r, s: len(r)==2 and r[0]['operation']=='stop' and r[0]['result']=='ok'
        and r[1]['result']=='accepted' and s['move_direction']=='forward' and s['starts_this_boot']==1)

    run('pending_action_cancelled_before_stop_receipt', 'corpus_idle', [
        call('move', move, defer=True), call('stop', ms=10, rpc=2, defer=True),
        dict(flush=True, elapsed_ms=20), dict(inspect_ms=60000)],
        lambda r, s: len(r)==2 and r[0]['operation']=='stop' and r[0]['result']=='ok'
        and r[0]['uptime_ms']==1010 and off(r[0]) and r[1]['result']!='accepted'
        and off(s) and s['starts_this_boot']==0)

    for suffix, args in [('extra', dict(extra=True)), ('injected_turn', dict(_ct_turn=0))]:
        run('invalid_stop_'+suffix, 'corpus_forward70', [call('stop', args, defer=True), dict(flush=True, elapsed_ms=10)],
            lambda r, s: len(r)==1 and r[0]['result']=='rpc_error'
            and s['move_direction']=='forward' and s['move_speed_percent']==70 and s['starts_this_boot']==1)

    run('stop_without_recognized_input', 'corpus_sequence', [stop, dict(inspect_ms=60000)],
        lambda r, s: len(r)==1 and r[0]['result']=='ok' and r[0]['uptime_ms']==1000
        and off(r[0]) and off(s), await_stt=True)

    run('old_reads_and_actions_stay_isolated', 'corpus_idle', [
        call('get_status', defer=True), call('move', move, 1, 2, defer=True),
        dict(input_text='喷水', elapsed_ms=10), dict(flush=True, elapsed_ms=20),
        call('water', dict(duration_ms=1000), 30, 3)],
        lambda r, s: len(r)==3 and r[0]['result']==r[1]['result']=='voice_input_changed'
        and r[2]['result']=='accepted' and s['starts_this_boot']==1
        and s['logical_outputs']['water'] and s['move_direction']=='none')

    return dict(scope='Actual host MCP dispatch and callbacks; deferred scheduling, text, time and IO simulated; no model or physical acceptance',
                executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                scenarios=len(results), passed=all(row['passed'] for row in results),
                failed=[row['name'] for row in results if not row['passed']], results=results)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    report=check(args.executable)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({key:value for key,value in report.items() if key!='results'}, ensure_ascii=False))
    raise SystemExit(0 if report['passed'] else 1)
