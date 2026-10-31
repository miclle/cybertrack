#!/usr/bin/env python3
"""Replay all retained ct71 STT packets through the effect confirmation policy."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/validation/evidence/ct71-full-stt'


def check(executable):
    baseline = json.loads((EVIDENCE / 'playback-baseline.json').read_bytes())
    old = {(row['suite'], row['id']): row for row in baseline['results']}
    targets = {'V025', 'V026', 'V027'}
    results, negative = [], []

    def packets(row):
        if not row['received_audio_bytes_discarded']:
            return dict(suppressed=0, audible=0)
        return json.loads(subprocess.check_output([str(executable), '--packets'],
            input=json.dumps(row), text=True, timeout=10))

    for suite, filename in [('voice', 'full-voice.json.gz'), ('compose', 'full-compose.json.gz')]:
        trace = json.loads(gzip.decompress((EVIDENCE / filename).read_bytes()))
        for row in trace['results']:
            count = packets(row)
            expected = {key: old[suite, row['id']][key] for key in ('suppressed', 'audible')}
            if suite == 'voice' and row['id'] in targets:
                expected = dict(suppressed=sum(expected.values()), audible=0)
            assert count == expected, (suite, row['id'], count, expected)
            results.append(dict(suite=suite, id=row['id'], completed=row['completed'], **count))
            if suite != 'voice' or row['id'] not in {'V017','V018','V019','V021','V022','V023',*targets}:
                continue
            assert len(row['calls']) == len(row['simulated_receipts']) == 1
            field = row['calls'][0]['name'].split('.')[-1] + '_last_duration_ms'
            for mutation in ('wrong_request', 'rejected_receipt', 'missing_fault', 'missing_channel_duration',
                             'wrong_channel_duration', 'negation', 'early_speech', 'new_input', 'extra_tool'):
                changed = copy.deepcopy(row)
                if mutation == 'wrong_request': changed['calls'][0]['arguments']['duration_ms'] += 1
                if mutation == 'rejected_receipt': changed['simulated_receipts'][0]['result'] = 'rejected'
                if mutation == 'missing_fault': del changed['simulated_receipts'][0]['fault']
                if mutation == 'missing_channel_duration': del changed['simulated_receipts'][0][field]
                if mutation == 'wrong_channel_duration': changed['simulated_receipts'][0][field] += 1
                if mutation == 'negation':
                    for event in changed['timeline']:
                        if event['event'] == 'stt': event['text'] = '不要' + event['text']
                if mutation == 'early_speech':
                    onset = next(event for event in changed['timeline'] if event['event'] == 'tts_start')
                    changed['timeline'].remove(onset)
                    index = next(i for i,event in enumerate(changed['timeline']) if event['event'] == 'tool_call')
                    changed['timeline'].insert(index, onset)
                if mutation in ('new_input', 'extra_tool'):
                    index = next(i for i,event in enumerate(changed['timeline']) if event['event'] == 'tool_reply_sent')
                    if mutation == 'new_input':
                        changed['timeline'].insert(index, dict(event='stt', text='现在什么状态？'))
                    else:
                        changed['calls'].append(dict(name='self.tank.get_status', arguments={}))
                        changed['timeline'].insert(index, dict(event='tool_call'))
                got = packets(changed)
                assert got == dict(suppressed=0, audible=sum(count.values())), (row['id'], mutation, got)
                negative.append(dict(id=row['id'], mutation=mutation, all_audio_preserved=True))
    assert len(results) == 88 and len(negative) == 81
    names = ['firmware/esp32-audio/voice_feedback.h', 'firmware/esp32-audio/spoken_playback.h','firmware/esp32-audio/spoken_effects.h','firmware/esp32-audio/spoken_duration.h',
             'scripts/replay_lingxi_feedback.cc', 'scripts/check_effect_alias_feedback.py']
    return dict(scope='Offline playback only; original 88 captures unchanged; mismatches synthetic; no new model calls or device audio',
                executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                source_sha256={name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names},
                evidence_sha256={name: hashlib.sha256((EVIDENCE/name).read_bytes()).hexdigest() for name in
                    ('full-voice.json.gz', 'full-compose.json.gz', 'playback-baseline.json')},
                suppressed=sum(row['suppressed'] for row in results),
                allowed=sum(row['audible'] for row in results), results=results, synthetic_mismatches=negative)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    payload = json.dumps(check(args.executable.resolve()), ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload)
    else:
        print(payload, end='')
