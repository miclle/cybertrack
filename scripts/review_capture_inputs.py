#!/usr/bin/env python3
"""Summarize the declared two-run simulated-input control diagnostic."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from capture_lingxi import firmware_replay
from review_firmware_capture import review, require

ROOT=Path(__file__).resolve().parents[1]


def summarize(directory, executable):
    plan=json.loads((directory/'plan.json').read_bytes())
    corpus=ROOT/'docs/validation/capture-input-cases.json'
    cases=json.loads(corpus.read_bytes())['cases']
    require(plan['repeats']==2 and [c['id'] for c in cases]==plan['cases'], 'declared cases/repeats differ')
    require(hashlib.sha256(corpus.read_bytes()).hexdigest()==plan['corpus_sha256'], 'declared corpus differs')
    require(hashlib.sha256(executable.read_bytes()).hexdigest()==plan['host_sha256'], 'declared host differs')
    results=[];identity=None
    for repeat in (1,2):
        path=directory/f'platform-{repeat}.json.gz'
        raw=gzip.decompress(path.read_bytes()) if path.exists() else (directory/f'platform-{repeat}.json').read_bytes()
        trace=json.loads(raw)
        require(trace['host_input_mode']=='simulated_recognized_text', 'wrong input provenance')
        require(trace['capture_source_sha256']==plan['capture_source_sha256'] and trace['role_sha256']==plan['role_sha256'], 'capture or role changed')
        current={k:trace[k] for k in ('model','role_sha256','tool_schema_sha256','capture_source_sha256')}
        if identity is None:identity=current
        require(current==identity, 'run inputs differ')
        checked=review(trace,executable,corpus)
        require([r['id'] for r in checked['results']]==plan['cases'], 'missing or reordered cases')
        for row,record,case in zip(trace['results'],checked['results'],cases):
            expected=[dict(input_text=case['text'],elapsed_ms=0)]+[
                dict(c,elapsed_ms=i+1,rpc_id=i+1) for i,c in enumerate(case['expected_calls'])]
            # Use the actual observation time so expired positive actions are
            # compared with an expired reference, not an immediate snapshot.
            wanted=firmware_replay(executable,row['initial_profile'],
                [*expected,dict(inspect_ms=row['host_inspect_ms'])],await_stt=True)[-1]
            actual=row['host_final_state']
            same=all(actual[k]==wanted[k] for k in ('logical_outputs','sequence_active','starts_this_boot')) and all(
                actual['show_draft'][k]==wanted['show_draft'][k] for k in ('revision','active','steps'))
            results.append(dict(repeat=repeat,**record,expected_final_state_matches=same))
    return dict(scope='Twenty-four actual platform text sessions with simulated recognized originals and actual host; not ASR/human/board acceptance',
        identity=identity,total=len(results),completed=sum(r['completed'] for r in results),
        strict_tool_matches=sum(r['strict_tool_match'] for r in results),state_matches=sum(r['expected_final_state_matches'] for r in results),
        clarification_rejections=sum(r['results'].count('action_unspecified')+r['results'].count('draft_duration_unspecified') for r in results),
        all_input_and_rpc_states_reproduced=True,results=results)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True);p.add_argument('--executable',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=summarize(a.directory,a.executable)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='results'},ensure_ascii=False))
