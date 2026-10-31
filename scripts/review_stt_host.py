#!/usr/bin/env python3
"""Replay observed STT/tool events through a pinned host, without a platform or device."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from capture_lingxi import firmware_profile, firmware_replay


def review(trace, executable):
    if (trace.get('fixture_version') != 'firmware_host' or trace.get('input_mode') != 'synthetic_opus'
            or trace.get('host_input_mode') != 'platform_stt_events'):
        raise ValueError('requires synthesized speech and actual STT-gated host capture')
    if hashlib.sha256(executable.read_bytes()).hexdigest() != trace['host_replay_sha256']:
        raise ValueError('host binary differs from capture')
    if not isinstance(trace.get('results'),list) or not trace['results']:
        raise ValueError('capture has no cases')
    results=[]
    seen=set()
    for row in trace['results']:
        if row['id'] in seen or row.get('host_input_mode') != 'platform_stt_events' or type(row['completed']) is not bool:
            raise ValueError('duplicate case or simulated initial input')
        seen.add(row['id'])
        profile=firmware_profile(row['context'])
        if row['initial_profile'] != profile: raise ValueError('initial profile differs from context')
        timeline=row['timeline']
        boundaries=[i for i,event in enumerate(timeline) if event['event']=='input_sent']
        if len(boundaries)!=1: raise ValueError('requires one input boundary')
        sent=timeline[boundaries[0]]['ms']
        events=[event for event in timeline[boundaries[0]+1:] if event['event'] in ('stt','tool_call')]
        calls=row['host_calls']
        if len(events)!=len(calls): raise ValueError('STT/tool event count differs from replay input')
        requests=iter(row['calls']);text_seen=False;early=[];stt=[];previous=0
        for event,call in zip(events,calls):
            elapsed=event['ms']-sent
            if type(elapsed) is not int or elapsed<previous or call['elapsed_ms']!=elapsed:
                raise ValueError('event timing differs from replay input')
            previous=elapsed
            if event['event']=='stt':
                if set(call)!={'input_text','elapsed_ms'} or call['input_text']!=event['text']:
                    raise ValueError('transcription differs from replay input')
                stt.append(dict(text=call['input_text'],elapsed_ms=elapsed))
                text_seen=text_seen or bool(call['input_text'].strip(' \t\r\n'))
            else:
                request=next(requests,None)
                if request is None or event['name']!=call['name'] or request!={k:call[k] for k in ('name','arguments')}:
                    raise ValueError('tool request differs from replay input')
                if not text_seen:early.append(call['name'])
        if next(requests,None) is not None: raise ValueError('missing tool event')
        if type(row['host_inspect_ms']) is not int or row['host_inspect_ms']<previous:
            raise ValueError('final inspection precedes an event')
        # Recheck every prefix because each result was returned to the live model.
        replies=[]
        for i,call in enumerate(calls):
            if 'name' in call:
                replies.append(firmware_replay(executable,profile,calls[:i+1],await_stt=True)[-2])
        final=firmware_replay(executable,profile,[*calls,dict(inspect_ms=row['host_inspect_ms'])],await_stt=True)[-1]
        if replies!=row.get('host_rpc_replies',[]) or final!=row['host_final_state']:
            raise ValueError('captured MCP reply or final state differs from closed-host replay')
        results.append(dict(id=row['id'],completed=row['completed'],stt=stt,tools_before_nonempty_stt=early,
                            tool_count=len(row['calls']),rpc_error_count=sum('error' in r for r in replies),
                            starts_this_boot=final['starts_this_boot'],final_outputs=final['logical_outputs']))
    return dict(scope='Offline replay of captured STT/tool event order and host state; no new model run or board IO',
                run_id=trace['run_id'],host_replay_sha256=trace['host_replay_sha256'],
                cases=len(results),completed=sum(row['completed'] is True for row in results),
                cases_with_tools_before_stt=[row['id'] for row in results if row['tools_before_nonempty_stt']],
                replies_and_final_states_match=True,results=results)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--executable',type=Path,required=True)
    args=parser.parse_args()
    raw=args.capture.read_bytes()
    if args.capture.suffix=='.gz':raw=gzip.decompress(raw)
    print(json.dumps(review(json.loads(raw),args.executable),ensure_ascii=False,indent=2))
