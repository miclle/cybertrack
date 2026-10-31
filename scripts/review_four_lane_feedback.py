#!/usr/bin/env python3
"""Compare playback policies against retained targeted actual-STT/RPC events."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from review_firmware_capture import review, require
from review_full_speech import recognized
from review_spoken_cases import normalized

ROOT=Path(__file__).resolve().parents[1]


def check(directory,host,old_playback,new_playback):
    plan=json.loads((directory/'plan.json').read_bytes())
    file=directory/'capture.json'
    trace=json.loads(file.read_bytes() if file.exists() else gzip.decompress((directory/'capture.json.gz').read_bytes()))
    corpus_path=ROOT/'docs/validation/four-lane-feedback-cases.json'
    corpus=json.loads(corpus_path.read_bytes())
    require(hashlib.sha256(corpus_path.read_bytes()).hexdigest()==plan['corpus_sha256'],'corpus differs')
    require(hashlib.sha256(host.read_bytes()).hexdigest()==plan['host_sha256'],'host differs')
    for key in ('role_sha256','capture_source_sha256','corpus_sha256'):
        require(trace[key]==plan[key],'captured identity differs: '+key)
    require(trace['tool_schema_sha256']==plan['tools_sha256'],'tools differ')
    require([r['id'] for r in trace['results']]==plan['ids'],'missing, reordered or repeated cases')
    control=review(trace,host,corpus_path)
    strict={r['id']:r['strict_tool_match'] for r in control['results']}

    def packets(executable,row):
        if not row['received_audio_bytes_discarded']:return dict(suppressed=0,audible=0)
        return json.loads(subprocess.check_output([str(executable),'--packets'],input=json.dumps(row),text=True,timeout=10))

    rows=[];mismatches=[];violations=[]
    for row,case in zip(trace['results'],corpus['cases']):
        require(row['id']==case['id'],'case ordering differs')
        stt=recognized(row)
        before=packets(old_playback,row);after=packets(new_playback,row)
        require(sum(before.values())==sum(after.values()),'packet count differs')
        if (case['category']!='success' or not strict[row['id']]) and before!=after:
            violations.append(dict(id=row['id'],reason='changed playback on protected or mismatched input'))
        rows.append(dict(id=row['id'],category=case['category'],completed=row['completed'],strict_tool_match=strict[row['id']],
            stt=stt,literal_transcript_match=bool(stt) and normalized(stt[-1])==normalized(case['text']),
            before=before,after=after,additional_suppressed=after['suppressed']-before['suppressed']))
        if case['category']!='success' or not strict[row['id']] or not after['suppressed']:continue
        require(len(row['calls'])==len(row['simulated_receipts'])==1,'mutation requires one admitted call')
        original=row['calls'][0];args=original['arguments']
        if 'steps_json' in args:
            first=json.loads(args['steps_json'])[0]
            lane=next(name for name in ('ignition','water','bubbles','move') if first[name+'_ms'])
        else:lane='move' if 'move_duration_ms' in args else original['name'].split('.')[-1]
        field=lane+'_last_duration_ms'
        for mutation in ('wrong_request','wrong_duration','missing_duration','wrong_source','missing_fault',
                         'rejected_receipt','negation','early_speech','new_input','extra_tool'):
            changed=copy.deepcopy(row)
            if mutation=='wrong_request':
                args=changed['calls'][0]['arguments']
                if 'steps_json' in args:
                    steps=json.loads(args['steps_json']);steps[0][lane+'_ms']+=1;args['steps_json']=json.dumps(steps)
                else:args['move_duration_ms' if lane=='move' and 'move_duration_ms' in args else 'duration_ms']+=1
            if mutation=='wrong_duration':changed['simulated_receipts'][0][field]+=1
            if mutation=='missing_duration':del changed['simulated_receipts'][0][field]
            if mutation=='wrong_source':changed['simulated_receipts'][0][lane+'_source']='web'
            if mutation=='missing_fault':del changed['simulated_receipts'][0]['fault']
            if mutation=='rejected_receipt':changed['simulated_receipts'][0]['result']='rejected'
            if mutation=='negation':
                for event in changed['timeline']:
                    if event['event']=='stt':event['text']='不要'+event['text']
            if mutation=='early_speech':
                onset=next(e for e in changed['timeline'] if e['event']=='tts_start');changed['timeline'].remove(onset)
                index=next(i for i,e in enumerate(changed['timeline']) if e['event']=='tool_call')
                changed['timeline'].insert(index,onset)
            if mutation in ('new_input','extra_tool'):
                index=next(i for i,e in enumerate(changed['timeline']) if e['event']=='tool_reply_sent')
                if mutation=='new_input':changed['timeline'].insert(index,dict(event='stt',text='现在什么状态？'))
                else:
                    changed['calls'].append(dict(name='self.tank.get_status',arguments={}))
                    changed['timeline'].insert(index,dict(event='tool_call'))
            count=packets(new_playback,changed)
            preserved=count==dict(suppressed=0,audible=sum(after.values()))
            mismatches.append(dict(id=row['id'],mutation=mutation,all_audio_preserved=preserved))
            if not preserved:violations.append(dict(id=row['id'],reason=mutation))
    sources=['firmware/esp32-audio/voice_feedback.h','firmware/esp32-audio/spoken_playback.h',
             'firmware/esp32-audio/spoken_effects.h','firmware/esp32-audio/spoken_duration.h',
             'scripts/replay_lingxi_feedback.cc','scripts/review_four_lane_feedback.py']
    return dict(scope='Targeted synthetic speech with actual STT/MCP; offline policy comparison and synthetic mismatches; no board/speaker IO',
        plan_sha256=hashlib.sha256((directory/'plan.json').read_bytes()).hexdigest(),
        source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},
        playback_sha256=dict(before=hashlib.sha256(old_playback.read_bytes()).hexdigest(),after=hashlib.sha256(new_playback.read_bytes()).hexdigest()),
        host_review=control,cases=len(rows),completed=sum(r['completed'] for r in rows),strict_tool_matches=sum(r['strict_tool_match'] for r in rows),
        literal_transcript_matches=sum(r['literal_transcript_match'] for r in rows),
        additional_suppressed=sum(r['additional_suppressed'] for r in rows),results=rows,synthetic_mismatches=mismatches,
        playback_gate_passed=not violations,playback_gate_violations=violations,
        original_model_scores_changed=False,physical_acceptance=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--host',type=Path,required=True)
    parser.add_argument('--before',type=Path,required=True)
    parser.add_argument('--after',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=check(args.directory,args.host.resolve(),args.before.resolve(),args.after.resolve())
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    raise SystemExit(0 if report['playback_gate_passed'] else 1)
