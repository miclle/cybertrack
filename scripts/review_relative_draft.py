#!/usr/bin/env python3
"""Review targeted synthetic speech, observed STT, calls and actual host states."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from capture_lingxi import firmware_profile, firmware_replay
from evaluate_voice import canonical
from review_spoken_cases import normalized

ROOT=Path(__file__).resolve().parents[1]


def review(directory,executable,classifier,capture_executable=None,capture_classifier=None):
    corpus_path=ROOT/'docs/validation/relative-draft-cases.json'
    cases=json.loads(corpus_path.read_bytes())['cases']
    assert len(cases)==10 and len({c['id'] for c in cases})==10
    binary=hashlib.sha256(executable.read_bytes()).hexdigest()
    capture_binary=hashlib.sha256((capture_executable or executable).read_bytes()).hexdigest()
    cached={}
    def category(text):
        if text not in cached:
            value=json.loads(subprocess.check_output([str(classifier)],input=text,text=True,timeout=10))
            assert type(value) is bool
            if capture_classifier:
                captured=json.loads(subprocess.check_output([str(capture_classifier)],input=text,text=True,timeout=10))
                assert captured is value, 'classifier differs on retained observed STT'
            cached[text]=value
        return cached[text]
    summaries=[];identity=None
    for repeat in (1,2):
        path=directory/f'platform-{repeat}.json.gz'
        raw=gzip.decompress(path.read_bytes()) if path.exists() else (directory/f'platform-{repeat}.json').read_bytes()
        trace=json.loads(raw)
        assert trace['input_mode']=='synthetic_opus' and trace['host_input_mode']=='platform_stt_events'
        assert trace['fixture_version']=='firmware_host' and trace['host_replay_sha256']==capture_binary
        assert trace['corpus_sha256']==hashlib.sha256(corpus_path.read_bytes()).hexdigest()
        keys=('role_sha256','tool_schema_sha256','capture_source_sha256','synthesis_source_sha256','model')
        observed={key:trace[key] for key in keys}
        if identity is None:identity=observed
        assert observed==identity
        assert [r['id'] for r in trace['results']]==[c['id'] for c in cases]
        for row,case in zip(trace['results'],cases):
            assert type(row['completed']) is bool and row['input_text']==case['text'] and row['context']==case['context']
            assert row['host_input_mode']=='platform_stt_events' and row['initial_profile']==firmware_profile(case['context'])
            uplink=row['uplink']
            assert [uplink[k] for k in ('codec','sample_rate_hz','channels','frame_ms')]==['opus',16000,1,60]
            assert uplink['frames']>0 and uplink['encoded_bytes']>0 and len(uplink['payload_sha256'])==64
            history=row['host_calls'];rpc=[];calls=[];seen_text=None;call_results=[]
            stt=[item['text'] for item in row['timeline'] if item['event']=='stt']
            assert [item['input_text'] for item in history if 'input_text' in item]==stt
            for i,item in enumerate(history):
                if 'input_text' in item:
                    seen_text=item['input_text'];continue
                assert 'name' in item
                calls.append({key:item[key] for key in ('name','arguments')})
                wire=firmware_replay(executable,row['initial_profile'],history[:i+1],await_stt=True)[-2]
                rpc.append(wire)
                result=json.loads(wire['result']['content'][0]['text']) if 'result' in wire else dict(result='rpc_error')
                call_results.append(dict(name=item['name'],recognized_text=seen_text,
                    classified_unquantified=category(seen_text) if seen_text is not None else None,
                    result=result['result'],clarification_facts=result.get('clarification_facts')))
            assert calls==row['calls'] and rpc==row.get('host_rpc_replies',[])
            if stt:assert row['echoed_text']==stt[-1]
            final=firmware_replay(executable,row['initial_profile'],[*history,dict(inspect_ms=row['host_inspect_ms'])],await_stt=True)[-1]
            assert final==row['host_final_state']
            expected_calls=[dict(input_text=case['text'],elapsed_ms=0)]+[
                dict(call,elapsed_ms=i+1,rpc_id=i+1) for i,call in enumerate(case['expected_calls'])]
            wanted=firmware_replay(executable,row['initial_profile'],expected_calls,await_stt=True)[-1]
            state_keys=('logical_outputs','sequence_active','starts_this_boot')
            same=all(final[k]==wanted[k] for k in state_keys) and all(
                final['show_draft'][k]==wanted['show_draft'][k] for k in ('active','revision','steps'))
            try:strict=row['completed'] and canonical(row['calls'])==canonical(case['expected_calls'])
            except (ValueError,TypeError):strict=False
            unsafe=[r for r in call_results if r['classified_unquantified'] and
                    r['name'].replace('self_tank_','self.tank.',1) not in ('self.tank.stop','self.tank.get_status') and
                    r['result'] in ('accepted','draft_saved','draft_cancelled')]
            summaries.append(dict(repeat=repeat,id=row['id'],completed=row['completed'],completion=row['completion'],
                transcript=row.get('echoed_text'),literal_transcript_match=normalized(row.get('echoed_text',''))==normalized(case['text']),
                final_text_classified_unquantified=category(stt[-1]) if stt else None,
                tool_calls_match=strict,expected_state_matches=same,needs_clarification=case['needs_clarification'],
                calls=row['calls'],call_results=call_results,unquantified_mutation_accepted=unsafe,
                final_revision=final['show_draft']['revision'],starts=final['starts_this_boot'],reply=''.join(row['replies'])))
    return dict(scope='Twenty targeted synthesized-voice sessions with real ASR/STT and actual host control; not the fixed 20 human cases or speaker/board acceptance',
        host_sha256=binary,capture_host_sha256=capture_binary,
        classifier_sha256=hashlib.sha256(classifier.read_bytes()).hexdigest(),
        capture_classifier_sha256=hashlib.sha256((capture_classifier or classifier).read_bytes()).hexdigest(),identity=identity,
        total=20,completed=sum(r['completed'] for r in summaries),literal_transcript_matches=sum(r['literal_transcript_match'] for r in summaries),
        tool_matches=sum(r['tool_calls_match'] for r in summaries),state_matches=sum(r['expected_state_matches'] for r in summaries),
        relative_states_preserved=sum(r['needs_clarification'] and r['expected_state_matches'] for r in summaries),relative_total=6,
        clarification_rejections=sum(c['result']=='draft_duration_unspecified' for r in summaries for c in r['call_results']),
        unquantified_mutations_accepted=sum(len(r['unquantified_mutation_accepted']) for r in summaries),
        incomplete=[dict(repeat=r['repeat'],id=r['id']) for r in summaries if not r['completed']],
        replies_and_final_states_reproduced=True,results=summaries)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True);p.add_argument('--executable',type=Path,required=True)
    p.add_argument('--classifier',type=Path,required=True)
    p.add_argument('--capture-executable',type=Path)
    p.add_argument('--capture-classifier',type=Path)
    a=p.parse_args()
    if bool(a.capture_executable)!=bool(a.capture_classifier):p.error('both captured executables are required together')
    print(json.dumps(review(a.directory,a.executable,a.classifier,a.capture_executable,a.capture_classifier),ensure_ascii=False,indent=2))
