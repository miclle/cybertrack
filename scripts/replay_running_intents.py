#!/usr/bin/env python3
"""Replay captured ct48 motion and show requests through the host receipt adapter."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from evaluate_voice import canonical

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / 'docs/validation/ct48-running-cases.json'


def replay(trace_file, executable):
    raw = trace_file.read_bytes()
    if trace_file.suffix == '.gz':
        raw = gzip.decompress(raw)
    trace = json.loads(raw)
    corpus = CORPUS.read_bytes()
    cases = json.loads(corpus)['cases']
    if (trace['kind'] != 'captured_tool_calls' or trace['input_mode'] != 'raw_text_diagnostic'
            or trace['corpus_sha256'] != hashlib.sha256(corpus).hexdigest()
            or [r['id'] for r in trace['results']] != [c['id'] for c in cases]):
        raise ValueError('Expected one complete matching running-intent capture')
    reviewed = []
    for case, row in zip(cases,trace['results']):
        expected = case['expected_calls']
        if not row['completed'] or row['input_text'] != case['text']:
            raise ValueError(f"Incomplete or mismatched input at {row['id']}")
        review = dict(id=row['id'], exact_calls=canonical(row['calls'])==canonical(expected))
        run = subprocess.run([str(executable),case['initial_motion']], input=json.dumps(row['calls']),
                             text=True, capture_output=True, timeout=10)
        if run.returncode == 3:
            review.update(replayed=False, reason='invalid, rejected or unsupported RPC')
        else:
            run.check_returncode()
            receipts = [json.loads(line) for line in run.stdout.splitlines()]
            state = receipts[-1]
            if len(receipts) != len(row['calls'])+1:
                raise ValueError('Missing host receipts')
            review.update(replayed=True, outcomes=[r['result'] for r in receipts[:-1]],
                          starts=state['starts_this_boot'], outputs=state['logical_outputs'],
                          direction=state['move_direction'], speed=state['move_speed_percent'],
                          remaining_ms=state['move_remaining_ms'], saved=state['show_draft']['steps'])
            moving = case['initial_motion'] == 'forward70'
            keep_moving = moving and not any(c['name']=='self.tank.stop' for c in expected)
            speed = 70 if keep_moving else 0
            correct = (review['outputs']==dict(left=speed,right=speed,water=False,bubbles=False,ignition=False)
                       and review['starts']==int(moving) and review['speed']==speed
                       and review['direction']==('forward' if keep_moving else 'none')
                       and review['remaining_ms']==(4000 if keep_moving else 0))
            draft_calls = [c for c in expected if c['name']=='self.tank.compose']
            steps = json.loads(draft_calls[0]['arguments']['steps_json']) if draft_calls else []
            correct &= (state['show_draft']['active'] == bool(steps)
                        and review['saved'] == [{**{'speed_percent':100}, **s} for s in steps])
            review['final_state_matches'] = correct
            if moving:
                timeline = row['timeline']
                sent = next(e['ms'] for e in timeline if e['event']=='input_sent')
                times = [e['ms']-sent for e in timeline if e['event']=='tool_call']
                timed = [{**call,'elapsed_ms':ms} for call,ms in zip(row['calls'],times,strict=True)]
                end = next(e['ms']-sent for e in reversed(timeline) if e['event']=='tts_stop')
                timed.append(dict(name='self.tank.get_status',arguments={},elapsed_ms=end))
                output = subprocess.check_output([str(executable),'forward70'],input=json.dumps(timed),
                                                 text=True,timeout=10)
                observations = [json.loads(line) for line in output.splitlines()][:len(timed)]
                review['timed_motion'] = []
                stopped = False
                for call,status in zip(timed,observations,strict=True):
                    stopped |= call['name'].replace('self_tank_','self.tank.',1)=='self.tank.stop'
                    remaining = 0 if stopped else max(0,4000-call['elapsed_ms'])
                    pwm = 70 if remaining else 0
                    valid = (status['move_remaining_ms']==remaining and status['starts_this_boot']==1
                             and status['logical_outputs']==dict(left=pwm,right=pwm,water=False,bubbles=False,ignition=False))
                    review['timed_motion'].append(dict(at_ms=call['elapsed_ms'],remaining_ms=status['move_remaining_ms'],
                                                      matches_deadline=valid))
        reviewed.append(review)
    return dict(run_id=trace['run_id'],raw_sha256=hashlib.sha256(raw).hexdigest(),results=reviewed)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace',type=Path)
    parser.add_argument('--executable',type=Path,default=ROOT/'build/audio-host/receipt_replay')
    args = parser.parse_args()
    print(json.dumps(replay(args.trace,args.executable),ensure_ascii=False,indent=2))
