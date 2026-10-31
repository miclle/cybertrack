#!/usr/bin/env python3
"""Verify host capture input provenance and reproduce RPCs; never contact a device."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from capture_lingxi import firmware_profile, firmware_replay
from evaluate_voice import canonical


def require(condition, message):
    if not condition:
        raise ValueError(message)


def review(trace, executable, corpus_path):
    corpus_raw = corpus_path.read_bytes()
    require(trace['corpus_sha256'] == hashlib.sha256(corpus_raw).hexdigest(), 'corpus hash differs')
    cases = {c['id']:c for c in json.loads(corpus_raw)['cases']}
    binary = hashlib.sha256(executable.read_bytes()).hexdigest()
    require(trace['fixture_version'] == 'firmware_host' and trace['host_replay_sha256'] == binary,
            'actual host identity differs')
    mode = trace['host_input_mode']
    require(trace.get('step_argument_format') in (None,'legacy_string','native_array'), 'unknown declared step schema')
    require(mode in ('simulated_initial_input','simulated_recognized_text','platform_stt_events'), 'unknown input provenance')
    require(trace['input_mode'] == ('synthetic_opus' if mode == 'platform_stt_events' else 'raw_text_diagnostic'),
            'transport and host input provenance differ')
    require(bool(trace['results']), 'no captured cases')
    seen = set(); results = []
    for row in trace['results']:
        cid = row['id']
        require(cid in cases and cid not in seen, 'unknown or repeated case')
        seen.add(cid); case = cases[cid]
        require(row['input_text'] == case['text'] and row['context'] == case['context'], 'case input differs')
        require(row['initial_profile'] == firmware_profile(case['context']) and row['host_input_mode'] == mode,
                'host profile/input provenance differs')
        require(type(row['completed']) is bool, 'invalid completion flag')
        timeline = row['timeline']
        times = [e['ms'] for e in timeline]
        require(all(type(t) is int and t >= 0 for t in times) and times == sorted(times), 'invalid event clock')
        boundaries = [i for i,e in enumerate(timeline) if e['event']=='input_sent']
        require(len(boundaries)==1, 'missing or duplicate input boundary')
        start = boundaries[0]; offset = timeline[start]['ms']; history = row['host_calls']; expected = []
        tools = []; tool_index = 0; input_count = 0; early = False
        for event in timeline[start+1:]:
            kind = event['event']
            relevant = kind == ('stt' if mode=='platform_stt_events' else 'simulated_input' if mode=='simulated_recognized_text' else '')
            if relevant:
                require(isinstance(event['text'],str), 'invalid recognized text')
                if mode == 'simulated_recognized_text':
                    require(event['text'] == case['text'], 'simulated recognition is not the original utterance')
                expected.append(dict(input_text=event['text'],elapsed_ms=event['ms']-offset));input_count += 1
            elif kind == 'tool_call':
                require(tool_index < len(row['calls']) and len(expected)<len(history), 'tool event missing from history')
                call = row['calls'][tool_index]; saved = history[len(expected)]
                require(event['name'] == call['name'] and type(saved.get('rpc_id')) is int, 'tool or RPC identity differs')
                expected.append(dict(call,rpc_id=saved['rpc_id'],elapsed_ms=event['ms']-offset))
                tools.append(call);tool_index += 1
                if mode != 'simulated_initial_input' and input_count == 0:early = True
        require(tools == row['calls'] and expected == history, 'received input/tool order or timing differs')
        require(mode != 'simulated_recognized_text' or input_count == 1, 'simulated recognition must occur exactly once')
        require(not any(e['event']=='simulated_input' for e in timeline) or mode=='simulated_recognized_text',
                'simulated input mislabeled as another mode')
        await_input = mode != 'simulated_initial_input'
        replies = [firmware_replay(executable,row['initial_profile'],history[:i+1],await_stt=await_input)[-2]
                   for i,call in enumerate(history) if 'name' in call]
        require(replies == row.get('host_rpc_replies',[]), 'captured RPC reply differs')
        final = firmware_replay(executable,row['initial_profile'],[*history,dict(inspect_ms=row['host_inspect_ms'])],await_stt=await_input)[-1]
        require(final == row['host_final_state'], 'captured final state differs')
        try: strict = row['completed'] and canonical(row['calls'],step_format=trace.get('step_argument_format')) == canonical(case['expected_calls'])
        except (ValueError,TypeError): strict = False
        values = [json.loads(w['result']['content'][0]['text']) if 'result' in w else dict(result='rpc_error') for w in replies]
        results.append(dict(id=cid,completed=row['completed'],strict_tool_match=strict,input_events=input_count,
            tools_before_input=early,results=[v['result'] for v in values],starts=final['starts_this_boot'],
            draft_revision=final['show_draft']['revision'],reply=''.join(row['replies'])))
    return dict(scope='Input provenance and complete host reply/state reproduction; semantic errors retained, no human/physical acceptance',
        host_input_mode=mode,host_sha256=binary,corpus_sha256=trace['corpus_sha256'],
        cases=len(results),completed=sum(r['completed'] for r in results),strict_tool_matches=sum(r['strict_tool_match'] for r in results),
        tools_before_input=[r['id'] for r in results if r['tools_before_input']],
        replies_and_final_states_reproduced=True,results=results)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('trace',type=Path);p.add_argument('--corpus',type=Path,required=True)
    p.add_argument('--executable',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();raw=a.trace.read_bytes();trace=json.loads(gzip.decompress(raw) if a.trace.suffix=='.gz' else raw)
    report=review(trace,a.executable,a.corpus)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False))
