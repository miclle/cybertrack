#!/usr/bin/env python3
"""Review the unadopted MCP projection using its frozen experimental host."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from capture_lingxi import firmware_replay
from evaluate_voice import evaluate

ROOT=Path(__file__).resolve().parents[1]
CAPTURE=ROOT/'docs/validation/evidence/ct62-stt-host/full20.json.gz'
PLAYBACK=ROOT/'docs/validation/evidence/ct63-plan-feedback/playback-review.json'
EVIDENCE=ROOT/'docs/validation/evidence/compact-model-receipts'


def check(executable, playback):
    experiment=json.loads((EVIDENCE/'experiment.json').read_bytes())
    for name,identity in experiment['files'].items():
        path=EVIDENCE/name
        if path.resolve().parent!=EVIDENCE.resolve():raise ValueError('invalid experimental evidence path')
        raw=path.read_bytes()
        if len(raw)!=identity['bytes'] or hashlib.sha256(raw).hexdigest()!=identity['sha256']:
            raise ValueError('experimental evidence differs from manifest: '+name)
    manifest=json.loads((EVIDENCE/'host-manifest.json').read_bytes())
    if hashlib.sha256(executable.read_bytes()).hexdigest()!=manifest['executable_sha256']:
        raise ValueError('requires the frozen unadopted experimental host')
    trace=json.loads(gzip.decompress(CAPTURE.read_bytes()))
    expected={row['id']:row for row in json.loads(PLAYBACK.read_bytes())['results']}
    results=[];before=after=changed=0
    for row in trace['results']:
        calls=row['host_calls'];replies=[]
        for i,call in enumerate(calls):
            if 'name' in call:replies.append(firmware_replay(executable,row['initial_profile'],calls[:i+1],await_stt=True)[-2])
        original=row.get('host_rpc_replies',[])
        assert len(original)==len(replies)
        full_bytes=compact_bytes=0;changes=0;receipts=[]
        for old,new in zip(original,replies):
            if 'error' in old:
                assert old==new;continue
            assert 'result' in new
            a=old['result']['content'][0]['text'];b=new['result']['content'][0]['text']
            full=json.loads(a);compact=json.loads(b)
            assert compact and all(key in full and full[key]==value for key,value in compact.items())
            if full!=compact:
                assert full['result'] in ('accepted','ok','draft_saved','draft_cancelled')
                assert full['operation']!='get_status'
                changes+=1
            full_bytes+=len(a.encode());compact_bytes+=len(b.encode());receipts.append(compact)
        final=firmware_replay(executable,row['initial_profile'],[*calls,dict(inspect_ms=row['host_inspect_ms'])],await_stt=True)[-1]
        assert final==row['host_final_state']
        projected=copy.deepcopy(row);projected['simulated_receipts']=receipts
        packets=dict(suppressed=0,audible=0)
        if row['received_audio_bytes_discarded']:
            packets=json.loads(subprocess.check_output([str(playback),'--packets'],input=json.dumps(projected),text=True,timeout=10))
        assert packets=={key:expected[row['id']][key] for key in ('suppressed','audible')}
        results.append(dict(id=row['id'],receipts_changed=changes,full_bytes=full_bytes,model_bytes=compact_bytes,
                            all_retained_values_equal=True,final_state_equal=True,**packets))
        before+=full_bytes;after+=compact_bytes;changed+=changes
    assert len(results)==20 and changed==14 and after<before
    projection=dict(scope='Offline replay with actual MCP dispatcher and control guard; projection and playback only; model did not consume these projected replies; no new platform session or board IO',
                capture_gzip_sha256=hashlib.sha256(CAPTURE.read_bytes()).hexdigest(),
                host_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),playback_sha256=hashlib.sha256(playback.read_bytes()).hexdigest(),
                cases=len(results),changed_receipts=changed,full_bytes=before,model_bytes=after,
                suppressed=sum(row['suppressed'] for row in results),audible=sum(row['audible'] for row in results),results=results)
    trace=json.loads(gzip.decompress((EVIDENCE/'full-compose.json.gz').read_bytes()))
    corpus=json.loads((ROOT/'docs/validation/compose-cases.json').read_bytes())
    assert hashlib.sha256((ROOT/'docs/validation/compose-cases.json').read_bytes()).hexdigest()==trace['corpus_sha256']
    assert trace['host_replay_sha256']==manifest['executable_sha256']
    recorded=json.loads((EVIDENCE/'full-suite-scores.json').read_bytes())['compose'];score=evaluate(corpus,trace)
    for key in ('correct','scored','total','incomplete','forbidden_call_cases','invalid_tool_argument_cases','tool_call_target_met'):
        assert score[key]==recorded[key]
    platform=[]
    for row in trace['results']:
        replies=[]
        for i,call in enumerate(row['host_calls']):
            if 'name' in call:replies.append(firmware_replay(executable,row['initial_profile'],row['host_calls'][:i+1])[-2])
        assert replies==row.get('host_rpc_replies',[])
        final=firmware_replay(executable,row['initial_profile'],[*row['host_calls'],dict(inspect_ms=row['host_inspect_ms'])])[-1]
        assert final==row['host_final_state']
        platform.append(dict(id=row['id'],completed=row['completed'],reply_characters=len(''.join(row['replies'])),
                             calls=row['calls'],final_revision=final['show_draft']['revision'],starts=final['starts_this_boot']))
    assert len(platform)==8
    return dict(decision='not_adopted',projection=projection,
                platform=dict(scope='Offline verification of eight retained real-platform text sessions; not a new run or voice acceptance',
                              correct=score['correct'],total=score['total'],forbidden_call_cases=score['forbidden_call_cases'],
                              incomplete=score['incomplete'],replies_and_final_states_match=True,results=platform))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable',type=Path,required=True)
    parser.add_argument('--playback',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(check(args.executable,args.playback),ensure_ascii=False,indent=2))
