#!/usr/bin/env python3
"""Review declared synthesized speech and negative-input control evidence separately."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from capture_lingxi import firmware_replay
from review_firmware_capture import review, require
from review_spoken_cases import normalized

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(directory, executable, classifier):
    plan=json.loads((directory/'plan.json').read_bytes())
    corpus=ROOT/'docs/validation/negative-input-cases.json'
    cases=json.loads(corpus.read_bytes())['cases']
    require(plan['repeats']==2 and [c['id'] for c in cases]==plan['cases'], 'case plan differs')
    require(digest(corpus)==plan['corpus_sha256'] and digest(executable)==plan['host_sha256'], 'corpus or host differs')
    require(digest(classifier)==plan['classifier_sha256'], 'classifier differs')
    results=[];identity=None;cached={}
    for repeat in (1,2):
        path=directory/f'platform-{repeat}.json.gz'
        raw=gzip.decompress(path.read_bytes()) if path.exists() else (directory/f'platform-{repeat}.json').read_bytes()
        trace=json.loads(raw)
        require(trace['input_mode']=='synthetic_opus' and trace['host_input_mode']=='platform_stt_events','not real STT input')
        require(trace['role_sha256']==plan['role_sha256'] and trace['capture_source_sha256']==plan['capture_source_sha256']
                and trace['synthesis_source_sha256']==plan['synthesis_source_sha256'],'role or capture sources differ')
        current={k:trace[k] for k in ('model','role_sha256','tool_schema_sha256','capture_source_sha256','synthesis_source_sha256')}
        if identity is None:identity=current
        require(current==identity,'run identities differ')
        require([r['id'] for r in trace['results']]==plan['cases'],'missing/reordered cases')
        checked=review(trace,executable,corpus)
        for case,row,record in zip(cases,trace['results'],checked['results']):
            uplink=row['uplink']
            require([uplink[k] for k in ('codec','sample_rate_hz','channels','frame_ms')]==['opus',16000,1,60]
                    and uplink['frames']>0 and uplink['encoded_bytes']>0 and len(uplink['payload_sha256'])==64,'uplink differs')
            recognized=[e['text'] for e in row['timeline'] if e['event']=='stt']
            categories=[]
            for text in recognized:
                if text not in cached:
                    cached[text]=json.loads(subprocess.check_output([str(classifier)],input=text,text=True,timeout=10))
                require(type(cached[text]) is int and cached[text] in (0,1,2),'unknown classifier value')
                categories.append(cached[text])
            wanted_calls=[dict(input_text=case['text'],elapsed_ms=0)]+[
                dict(c,elapsed_ms=i+1,rpc_id=i+1) for i,c in enumerate(case['expected_calls'])]
            wanted=firmware_replay(executable,row['initial_profile'],[*wanted_calls,dict(inspect_ms=row['host_inspect_ms'])],await_stt=True)[-1]
            final=row['host_final_state']
            same=all(final[k]==wanted[k] for k in ('logical_outputs','sequence_active','sequence_result','starts_this_boot')) and all(
                final['show_draft'][k]==wanted['show_draft'][k] for k in ('active','revision','steps'))
            stop_case=any(c['name']=='self.tank.stop' for c in case['expected_calls'])
            stopped_refused=any(c['name'].replace('self_tank_','self.tank.',1)=='self.tank.stop' and result=='input_negated'
                for c,result in zip(row['calls'],record['results']))
            results.append(dict(repeat=repeat,**record,recognized=recognized,categories=categories,
                transcript_matches=bool(recognized) and normalized(recognized[-1])==normalized(case['text']),
                negative_case=case['negative_guard_expected'],expected_control_state_matches=same,
                expected_stop_case=stop_case,expected_stop_refused=stop_case and stopped_refused,
                input_negated_rejections=record['results'].count('input_negated')))
    return dict(scope='24 targeted synthesized Mandarin sessions, actual STT and actual MCP; no human/speaker/board acceptance or replacement fixed-suite score',
        identity=identity,host_sha256=digest(executable),classifier_sha256=digest(classifier),
        total=len(results),completed=sum(r['completed'] for r in results),transcript_matches=sum(r['transcript_matches'] for r in results),
        strict_tool_matches=sum(r['strict_tool_match'] for r in results),control_state_matches=sum(r['expected_control_state_matches'] for r in results),
        input_negated_rejections=sum(r['input_negated_rejections'] for r in results),
        expected_stop_refusals=sum(r['expected_stop_refused'] for r in results),
        all_captured_inputs_rpc_replies_and_final_states_reproduced=True,results=results)


def compare_final(directory, executable):
    """Compare a changed candidate with captured behavior; never relabel its host."""
    cases=[]
    for repeat in (1,2):
        path=directory/f'platform-{repeat}.json.gz'
        raw=gzip.decompress(path.read_bytes()) if path.exists() else (directory/f'platform-{repeat}.json').read_bytes()
        trace=json.loads(raw)
        for row in trace['results']:
            history=row['host_calls']
            replies=[firmware_replay(executable,row['initial_profile'],history[:i+1],await_stt=True)[-2]
                     for i,call in enumerate(history) if 'name' in call]
            final=firmware_replay(executable,row['initial_profile'],[*history,dict(inspect_ms=row['host_inspect_ms'])],await_stt=True)[-1]
            require(replies==row.get('host_rpc_replies',[]) and final==row['host_final_state'],'final candidate differs: '+row['id'])
            cases.append(dict(repeat=repeat,id=row['id'],all_replies_and_final_state_identical=True))
    require(len(cases)==24,'final comparison case count differs')
    return dict(scope='Offline compatibility of the final candidate with all 24 captured input/RPC histories; not a new platform run',
                captured_host_sha256=trace['host_replay_sha256'],final_host_sha256=digest(executable),cases=24,results=cases)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True);p.add_argument('--executable',type=Path,required=True)
    p.add_argument('--classifier',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--final-executable',type=Path);a=p.parse_args()
    report=summarize(a.directory,a.executable,a.classifier)
    if a.final_executable:report['final_candidate_replay']=compare_final(a.directory,a.final_executable)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False))
