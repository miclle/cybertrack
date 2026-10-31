#!/usr/bin/env python3
"""Separate full-corpus speech, tool selection and actual host control evidence."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from capture_lingxi import firmware_replay
from evaluate_voice import evaluate
from review_firmware_capture import require, review
from review_spoken_cases import normalized

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def recognized(row, replay=False):
    if replay:
        texts=row['stt_texts']
    else:
        require(not any(e['event']=='simulated_input' for e in row['timeline']), 'simulated input cannot be ASR')
        texts=[e['text'] for e in row['timeline'] if e['event']=='stt']
    require(isinstance(texts,list) and all(isinstance(t,str) for t in texts), 'invalid STT text list')
    require(row.get('echoed_text','') == (texts[-1] if texts else ''), 'echo differs from actual STT')
    return texts


def score_speech(corpus, trace):
    """Score received STT separately; a matching tool does not prove transcription."""
    require(trace['input_mode']=='synthetic_opus' and trace['host_input_mode']=='platform_stt_events', 'not actual synthetic-speech STT')
    tools=evaluate(corpus,trace)
    expected={c['id']:c for c in corpus['cases']}
    rows=[]
    for row in trace['results']:
        require(row['input_text']==expected[row['id']]['text'],'original utterance differs')
        up=row['uplink']
        require([up[k] for k in ('codec','sample_rate_hz','channels','frame_ms')]==['opus',16000,1,60]
                and type(up['frames']) is int and up['frames']>0 and type(up['encoded_bytes']) is int and up['encoded_bytes']>0
                and isinstance(up['payload_sha256'],str) and len(up['payload_sha256'])==64,'invalid synthesis provenance')
        stt=recognized(row,trace.get('score_replay') is True)
        match=bool(stt) and normalized(stt[-1])==normalized(row['input_text'])
        rows.append(dict(id=row['id'],recognized=stt,transcript_matches=match))
    return dict(scope='Full original corpus through synthesized speech and actual STT; not human microphone or spoken acceptance',
                tools=tools,transcription=dict(criterion='Literal after NFKC/whitespace/listed punctuation normalization; numeral spelling differences alone do not prove an ASR error',
                    total=len(expected),observed=len(rows),matches=sum(r['transcript_matches'] for r in rows),
                    missing_stt=[r['id'] for r in rows if not r['recognized']],
                    mismatches=[r['id'] for r in rows if not r['transcript_matches']],results=rows))


def score_replay(trace):
    """Export scoring fields, not simulated receipts, raw events or audio."""
    data={k:trace[k] for k in ('kind','run_id','model','role_sha256','corpus_sha256','host_replay_sha256',
        'tool_schema_sha256','capture_source_sha256','synthesis_source_sha256','input_mode','host_input_mode','step_argument_format')}
    data['score_replay']=True
    data['results']=[{k:r[k] for k in ('id','input_text','calls','completed','uplink')} |
                     dict(echoed_text=r.get('echoed_text',''),stt_texts=recognized(r)) for r in trace['results']]
    return data


def reference_state(executable,row,case):
    """At exact matches, retain actual RPC timing; mismatches remain diagnostic."""
    tool_times=[c['elapsed_ms'] for c in row['host_calls'] if 'name' in c]
    input_times=[c['elapsed_ms'] for c in row['host_calls'] if 'input_text' in c]
    start=input_times[0] if input_times else 0
    history=[dict(input_text=case['text'],elapsed_ms=start)]
    previous=start
    for i,call in enumerate(case['expected_calls']):
        at=max(previous+1,tool_times[i] if i<len(tool_times) else previous+1)
        history.append(dict(call,elapsed_ms=at,rpc_id=i+1));previous=at
    at=max(previous,row['host_inspect_ms'])
    return firmware_replay(executable,row['initial_profile'],[*history,dict(inspect_ms=at)],await_stt=True)[-1]


def summarize(directory,executable):
    plan=json.loads((directory/'plan.json').read_bytes());require(plan['repeats']==1,'unexpected repeats')
    require(digest(executable)==plan['host_sha256'],'capture host differs')
    groups={}
    for suite,count in (('voice',80),('compose',8)):
        path=directory/f'full-{suite}.json.gz'
        raw=gzip.decompress(path.read_bytes()) if path.exists() else (directory/f'full-{suite}.json').read_bytes()
        trace=json.loads(raw);corpus_path=ROOT/f'docs/validation/{suite}-cases.json';corpus=json.loads(corpus_path.read_bytes())
        require(digest(corpus_path)==plan['corpus_sha256'][suite] and trace['corpus_sha256']==plan['corpus_sha256'][suite],'corpus differs')
        for key in ('role_sha256','capture_source_sha256','synthesis_source_sha256'):
            require(trace[key]==plan[key],'captured identity differs: '+key)
        require(trace['tool_schema_sha256']==plan['tools_sha256'] and trace['model']==plan['model'],'schema/model label differs')
        require([r['id'] for r in trace['results']]==[c['id'] for c in corpus['cases']] and len(trace['results'])==count,'missing/reordered cases')
        scored=score_speech(corpus,trace)
        checked=review(trace,executable,corpus_path)
        control=[]
        for row,case in zip(trace['results'],corpus['cases']):
            actual=row['host_final_state'];wanted=reference_state(executable,row,case)
            keys=('logical_outputs','sequence_active','sequence_result','starts_this_boot','move_direction','move_speed_percent')
            same=all(actual[k]==wanted[k] for k in keys) and all(actual['show_draft'][k]==wanted['show_draft'][k] for k in ('active','revision','steps'))
            control.append(dict(id=row['id'],selected_control_state_matches=same,starts=actual['starts_this_boot'],
                draft_revision=actual['show_draft']['revision']))
        groups[suite]=dict(score=scored,replay=checked,control=dict(scope='Selected output/draft/start/sequence fields at observed RPC times by index; mismatched calls need manual diagnosis',
            matches=sum(r['selected_control_state_matches'] for r in control),total=count,results=control))
    return dict(scope='88 original fixed cases through synthetic Mandarin/actual STT and ct71 MCP, all attempts retained; no human/speaker/board acceptance',
        host_sha256=digest(executable),groups=groups,all_input_rpc_replies_and_final_states_reproduced=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--executable',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    report=summarize(a.directory,a.executable);a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='groups'},ensure_ascii=False))
