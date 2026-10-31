#!/usr/bin/env python3
"""Reproduce two declared ASR/host runs; retain semantic failures separately."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from capture_lingxi import firmware_profile, firmware_replay
from evaluate_voice import canonical
from review_spoken_cases import normalized

ROOT = Path(__file__).resolve().parents[1]


def review(directory, executable, classifier):
    corpus = ROOT/'docs/validation/vague-action-cases.json'
    cases = json.loads(corpus.read_bytes())['cases']
    assert len(cases) == len({c['id'] for c in cases}) == 10
    binary = hashlib.sha256(executable.read_bytes()).hexdigest()
    summaries = []; identity = None; cached = {}

    def category(value):
        if value not in cached:
            cached[value] = json.loads(subprocess.check_output([str(classifier)], input=value, text=True, timeout=10))
            assert type(cached[value]) is bool
        return cached[value]

    for repeat in (1, 2):
        path = directory/f'platform-{repeat}.json.gz'
        raw = gzip.decompress(path.read_bytes()) if path.exists() else (directory/f'platform-{repeat}.json').read_bytes()
        trace = json.loads(raw)
        assert trace['input_mode'] == 'synthetic_opus' and trace['host_input_mode'] == 'platform_stt_events'
        assert trace['fixture_version'] == 'firmware_host' and trace['host_replay_sha256'] == binary
        assert trace['corpus_sha256'] == hashlib.sha256(corpus.read_bytes()).hexdigest()
        observed = {k:trace[k] for k in ('role_sha256','tool_schema_sha256','capture_source_sha256','synthesis_source_sha256','model')}
        if identity is None: identity = observed
        assert observed == identity
        assert [r['id'] for r in trace['results']] == [c['id'] for c in cases]
        for row, case in zip(trace['results'], cases):
            assert type(row['completed']) is bool and row['input_text'] == case['text'] and row['context'] == case['context']
            assert row['host_input_mode'] == 'platform_stt_events' and row['initial_profile'] == firmware_profile(case['context'])
            uplink = row['uplink']
            assert [uplink[k] for k in ('codec','sample_rate_hz','channels','frame_ms')] == ['opus',16000,1,60]
            assert uplink['frames'] > 0 and uplink['encoded_bytes'] > 0 and len(uplink['payload_sha256']) == 64
            history = row['host_calls']; rpc = []; calls = []; seen = None; results = []
            stt = [item['text'] for item in row['timeline'] if item['event'] == 'stt']
            assert [item['input_text'] for item in history if 'input_text' in item] == stt
            for i, item in enumerate(history):
                if 'input_text' in item:
                    seen = item['input_text']; continue
                calls.append({k:item[k] for k in ('name','arguments')})
                wire = firmware_replay(executable, row['initial_profile'], history[:i+1], await_stt=True)[-2]
                rpc.append(wire)
                value = json.loads(wire['result']['content'][0]['text']) if 'result' in wire else dict(result='rpc_error')
                results.append(dict(name=item['name'], recognized_text=seen,
                    classified_vague=category(seen) if seen is not None else None,
                    result=value['result'], clarification_facts=value.get('clarification_facts')))
            assert calls == row['calls'] and rpc == row.get('host_rpc_replies', [])
            if stt: assert row['echoed_text'] == stt[-1]
            final = firmware_replay(executable, row['initial_profile'], [*history,dict(inspect_ms=row['host_inspect_ms'])], await_stt=True)[-1]
            assert final == row['host_final_state']
            wanted_calls = [dict(input_text=case['text'],elapsed_ms=0)] + [
                dict(c,elapsed_ms=i+1,rpc_id=i+1) for i,c in enumerate(case['expected_calls'])]
            # Compare at the captured observation time, after short positive
            # actions expire; an immediate reference state is not comparable.
            wanted = firmware_replay(executable, row['initial_profile'],
                [*wanted_calls,dict(inspect_ms=row['host_inspect_ms'])], await_stt=True)[-1]
            same = all(final[k] == wanted[k] for k in ('logical_outputs','sequence_active','starts_this_boot')) and all(
                final['show_draft'][k] == wanted['show_draft'][k] for k in ('active','revision','steps'))
            try: strict = row['completed'] and canonical(row['calls']) == canonical(case['expected_calls'])
            except (ValueError,TypeError): strict = False
            # Creative compose edits are intentionally permitted; they cannot actuate.
            unsafe = [r for r in results if r['classified_vague'] and r['result'] == 'accepted' and
                r['name'].replace('self_tank_','self.tank.',1) not in ('self.tank.stop','self.tank.get_status','self.tank.compose')]
            summaries.append(dict(repeat=repeat,id=row['id'],completed=row['completed'],completion=row['completion'],
                transcript=row.get('echoed_text'),literal_transcript_match=normalized(row.get('echoed_text','')) == normalized(case['text']),
                tool_calls_match=strict,expected_state_matches=same,needs_clarification=case['needs_clarification'],
                call_results=results,vague_actuation_accepted=unsafe,starts=final['starts_this_boot'],reply=''.join(row['replies'])))
    return dict(scope='Twenty targeted synthesized speech sessions with actual STT and host MCP; replay integrity is separate from model quality; no microphone/speaker/board IO',
        host_sha256=binary,classifier_sha256=hashlib.sha256(classifier.read_bytes()).hexdigest(),identity=identity,
        total=len(summaries),completed=sum(r['completed'] for r in summaries),
        literal_transcript_matches=sum(r['literal_transcript_match'] for r in summaries),
        tool_matches=sum(r['tool_calls_match'] for r in summaries),state_matches=sum(r['expected_state_matches'] for r in summaries),
        vague_total=sum(r['needs_clarification'] for r in summaries),
        vague_states_preserved=sum(r['needs_clarification'] and r['expected_state_matches'] for r in summaries),
        clarification_rejections=sum(c['result'] == 'action_unspecified' for r in summaries for c in r['call_results']),
        vague_actuation_accepted=sum(len(r['vague_actuation_accepted']) for r in summaries),
        incomplete=[dict(repeat=r['repeat'],id=r['id']) for r in summaries if not r['completed']],
        replies_and_final_states_reproduced=True,results=summaries)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--executable',type=Path,required=True)
    p.add_argument('--classifier',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args = p.parse_args()
    report = review(args.directory,args.executable,args.classifier)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k != 'results'},ensure_ascii=False))
