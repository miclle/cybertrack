#!/usr/bin/env python3
"""Reproduce a declared role-only comparison, retaining errors and all speech."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from capture_lingxi import firmware_profile, firmware_replay
from evaluate_voice import canonical


def read(directory, name):
    path = directory/(name+'.json.gz')
    return json.loads(gzip.decompress(path.read_bytes()) if path.exists() else (directory/(name+'.json')).read_bytes())


def review(directory, executable):
    plan = read(directory,'plan')
    corpus = directory/'cases.json'
    assert hashlib.sha256(corpus.read_bytes()).hexdigest() == plan['corpus_sha256']
    cases = json.loads(corpus.read_bytes())['cases']
    assert [c['id'] for c in cases] == plan['cases'] and len(set(plan['cases'])) == len(cases) == 12
    assert plan['repeats'] == 3
    binary = hashlib.sha256(executable.read_bytes()).hexdigest()
    identity = None; groups = {}
    for group in ('baseline','candidate'):
        role = (directory/f'{group}-role.txt').read_bytes()
        role_hash = hashlib.sha256(role).hexdigest()
        assert role_hash == plan[f'{group}_role_sha256']
        assert len(role.decode().rstrip('\n')) == plan[f'{group}_characters'] <= 6000
        rows = []
        for repeat in range(1,4):
            trace = read(directory,f'{group}-{repeat}')
            assert trace['host_replay_sha256'] == binary and trace['corpus_sha256'] == plan['corpus_sha256']
            assert trace['role_sha256'] == role_hash
            assert trace['input_mode'] == 'raw_text_diagnostic' and trace['fixture_version'] == 'firmware_host'
            assert trace['host_input_mode'] == 'simulated_initial_input'
            observed = {k:trace[k] for k in ('model','capture_source_sha256','tool_schema_sha256')}
            if identity is None: identity = observed
            assert observed == identity
            assert [r['id'] for r in trace['results']] == plan['cases']
            for row,case in zip(trace['results'],cases):
                assert type(row['completed']) is bool and row['input_text'] == case['text'] and row['context'] == case['context']
                assert row['initial_profile'] == firmware_profile(case['context'])
                calls = row['host_calls']
                assert [{k:c[k] for k in ('name','arguments')} for c in calls] == row['calls']
                replies = [firmware_replay(executable,row['initial_profile'],calls[:i+1])[-2] for i in range(len(calls))]
                assert replies == row.get('host_rpc_replies',[])
                final = firmware_replay(executable,row['initial_profile'],[*calls,dict(inspect_ms=row['host_inspect_ms'])])[-1]
                assert final == row['host_final_state']
                try: strict = row['completed'] and canonical(row['calls']) == canonical(case['expected_calls'])
                except (ValueError,TypeError): strict = False
                names = [c['name'].replace('self_tank_','self.tank.',1) for c in row['calls']]
                no_tools = not case['expected_calls']
                forbidden = no_tools and any(n != 'self.tank.get_status' for n in names)
                is_stop = any(c['name'] == 'self.tank.stop' for c in case['expected_calls'])
                false_stop = not is_stop and 'self.tank.stop' in names
                receipt_results = [json.loads(w['result']['content'][0]['text'])['result'] if 'result' in w else 'rpc_error' for w in replies]
                rows.append(dict(repeat=repeat,id=row['id'],text=case['text'],completed=row['completed'],completion=row['completion'],
                    strict_match=strict,forbidden_call=forbidden,false_stop=false_stop,is_stop=is_stop,
                    calls=row['calls'],receipt_results=receipt_results,reply=''.join(row['replies']),
                    final_revision=final['show_draft']['revision'],starts=final['starts_this_boot'],
                    outputs_off=not any(final['logical_outputs'].values())))
        groups[group] = dict(total=len(rows),completed=sum(r['completed'] for r in rows),
            strict_matches=sum(r['strict_match'] for r in rows),forbidden_calls=sum(r['forbidden_call'] for r in rows),
            false_stops=sum(r['false_stop'] for r in rows),stop_total=sum(r['is_stop'] for r in rows),
            stops_matched=sum(r['is_stop'] and r['strict_match'] for r in rows),
            stops_without_tts_text=sum(r['is_stop'] and r['strict_match'] and not r['reply'].strip() for r in rows),
            explicit_edit_cancel_matches=sum(r['id'] in ('C002','C004') and r['strict_match'] for r in rows),
            failed=[dict(repeat=r['repeat'],id=r['id']) for r in rows if not r['strict_match']],results=rows)
    b=groups['baseline'];c=groups['candidate']
    structural = (c['completed']==c['total'] and c['forbidden_calls']==c['false_stops']==0
                  and c['stops_matched']==c['stop_total'] and c['explicit_edit_cancel_matches']==6
                  and c['strict_matches']>b['strict_matches'])
    return dict(scope='Seventy-two role-only raw text sessions; host uses its synthetic placeholder input, not STT. Lexical STT guards and human/physical acceptance are not evaluated.',
        host_sha256=binary,identity=identity,groups=groups,structural_preflight_passed=structural,
        adoption='manual speech review and full original eighty/eight suite still required' if structural else 'preflight insufficient; restore original role',
        replies_and_final_states_reproduced=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--executable',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();report=review(a.directory,a.executable)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='groups'} | {'groups':{k:{a:b for a,b in v.items() if a!='results'} for k,v in report['groups'].items()}},ensure_ascii=False))
