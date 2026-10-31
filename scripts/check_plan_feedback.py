#!/usr/bin/env python3
"""Replay the retained STT/audio events and mismatches through playback policy only."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT/'docs/validation/evidence/ct62-stt-host/full20.json.gz'
BASELINE = ROOT/'docs/validation/evidence/ct62-stt-host/playback-review.json'


def check(executable):
    trace=json.loads(gzip.decompress(CAPTURE.read_bytes()))
    baseline=json.loads(BASELINE.read_bytes())
    old={row['id']:row for row in baseline['results']}
    targets={'V029','V031','V033','V035','V037'}
    def packets(row):
        if not row['received_audio_bytes_discarded']:return dict(suppressed=0,audible=0)
        return json.loads(subprocess.check_output([str(executable),'--packets'],input=json.dumps(row),text=True,timeout=10))
    results=[];negative=[]
    for row in trace['results']:
        count=packets(row)
        expected={key:old[row['id']][key] for key in ('suppressed','audible')}
        if row['id'] in targets:
            expected=dict(suppressed=sum(expected.values()),audible=0)
        assert count==expected,(row['id'],count,expected)
        results.append(dict(id=row['id'],completed=row['completed'],**count))
        if row['id'] not in targets:continue
        for mutation in ('wrong_request','rejected_receipt','missing_fault','negation','early_speech','new_input'):
            changed=copy.deepcopy(row)
            if mutation=='wrong_request':
                args=changed['calls'][0]['arguments']
                key='steps_json' if 'steps_json' in args else 'speed_percent' if 'speed_percent' in args else 'water_duration_ms'
                args[key]='[]' if key=='steps_json' else 90 if key=='speed_percent' else 1
            if mutation=='rejected_receipt':changed['simulated_receipts'][0]['result']='voice_input_failed'
            if mutation=='missing_fault':del changed['simulated_receipts'][0]['fault']
            if mutation=='negation':
                for event in changed['timeline']:
                    if event['event']=='stt':event['text']='不要'+event['text']
            if mutation=='early_speech':
                onset=next(event for event in changed['timeline'] if event['event']=='tts_start')
                changed['timeline'].remove(onset)
                index=next(i for i,event in enumerate(changed['timeline']) if event['event']=='tool_call')
                changed['timeline'].insert(index,onset)
            if mutation=='new_input':
                index=next(i for i,event in enumerate(changed['timeline']) if event['event']=='tool_reply_sent')
                changed['timeline'].insert(index,dict(event='stt',text='现在状态怎么样？'))
            got=packets(changed)
            assert got==dict(suppressed=0,audible=sum(count.values())),(row['id'],mutation,got)
            negative.append(dict(id=row['id'],mutation=mutation,all_audio_preserved=True))
    return dict(scope='Offline playback policy replay plus synthetic mismatches; no new platform sessions, audio decoding or board IO',
                capture_gzip_sha256=hashlib.sha256(CAPTURE.read_bytes()).hexdigest(),baseline_sha256=hashlib.sha256(BASELINE.read_bytes()).hexdigest(),
                source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                    ('firmware/esp32-audio/voice_feedback.h','firmware/esp32-audio/spoken_playback.h','scripts/replay_lingxi_feedback.cc')},
                executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                suppressed=sum(row['suppressed'] for row in results),audible=sum(row['audible'] for row in results),
                results=results,synthetic_mismatches=negative)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable',type=Path,required=True)
    print(json.dumps(check(parser.parse_args().executable),ensure_ascii=False,indent=2))
