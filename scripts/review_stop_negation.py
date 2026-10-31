#!/usr/bin/env python3
"""Review the bounded stop-description contrast, retaining queries and failures."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from capture_lingxi import firmware_profile, firmware_replay
from evaluate_voice import canonical, evaluate

ROOT=Path(__file__).resolve().parents[1]


def read(root,name):
    path=root/(name+'.json.gz')
    if path.exists():return json.loads(gzip.decompress(path.read_bytes()))
    return json.loads((root/(name+'.json')).read_bytes())


def summarize_case(row,case,final):
    if type(row['completed']) is not bool:raise ValueError('completion must be boolean')
    try:matched=row['completed'] and canonical(row['calls'])==canonical(case['expected_calls'])
    except (ValueError,TypeError):matched=False
    allowed={call['name'] for call in case['expected_calls']}|{'self.tank.get_status'}
    unexpected=[call['name'] for call in row['calls'] if call['name'].replace('self_tank_','self.tank.',1) not in allowed]
    revision=case.get('expected_draft_revision',7)
    return dict(id=row['id'],completed=row['completed'],strict_tool_match=matched,unexpected_control_calls=unexpected,
                draft_revision=final['show_draft']['revision'],draft_matches=final['show_draft']['revision']==revision,
                starts=final['starts_this_boot'],calls=row['calls'],reply_characters=len(''.join(row['replies'])))


def contrast_can_proceed(results,expected):
    return all(row['completed'] and not row['unexpected_control_calls'] and row['draft_matches'] and
               (row['strict_tool_match'] or not expected[row['id']]['expected_calls']) for row in results)


def review_fixed(directory, executable):
    """Replay all retained candidate calls, not only matched or safe examples."""
    identity = read(directory, 'diagnostic-C006-1')
    binary = hashlib.sha256(executable.read_bytes()).hexdigest()
    schema = hashlib.sha256((directory/'candidate-tools.json').read_bytes()).hexdigest()
    assert read(directory, 'candidate-tools')['tools'] == read(directory, 'diagnostic-tools')['tools']
    results = {}
    for suite, count in (('voice', 80), ('compose', 8)):
        corpus_path = ROOT/f'docs/validation/{suite}-cases.json'
        corpus = json.loads(corpus_path.read_bytes())
        expected = {case['id']: case for case in corpus['cases']}
        trace = read(directory, 'full-'+suite)
        assert trace['role_sha256'] == identity['role_sha256']
        assert trace['model'] == identity['model'] and trace['capture_source_sha256'] == identity['capture_source_sha256']
        assert trace['host_replay_sha256'] == binary and trace['tool_schema_sha256'] == schema
        assert trace['input_mode'] == 'raw_text_diagnostic' and trace['fixture_version'] == 'firmware_host'
        assert trace['corpus_sha256'] == hashlib.sha256(corpus_path.read_bytes()).hexdigest()
        assert len(trace['results']) == count and {row['id'] for row in trace['results']} == set(expected)
        rows = []
        for row in trace['results']:
            case = expected[row['id']]
            assert row['input_text'] == case['text'] and row['context'] == case['context']
            assert row['initial_profile'] == firmware_profile(case['context'])
            calls = row['host_calls']
            assert [{key: call[key] for key in ('name', 'arguments')} for call in calls] == row['calls']
            replies = [firmware_replay(executable, row['initial_profile'], calls[:i+1])[-2] for i in range(len(calls))]
            assert replies == row.get('host_rpc_replies', [])
            final = firmware_replay(executable, row['initial_profile'], [*calls, dict(inspect_ms=row['host_inspect_ms'])])[-1]
            assert final == row['host_final_state']
            result = dict(id=row['id'], completed=row['completed'], calls=row['calls'],
                          final_revision=final['show_draft']['revision'], starts=final['starts_this_boot'],
                          logical_outputs=final['logical_outputs'], reply_characters=len(''.join(row['replies'])))
            if case['category'] == 'stop':
                later = firmware_replay(executable, row['initial_profile'], [*calls, dict(inspect_ms=max(60000, row['host_inspect_ms']))])[-1]
                assert not later['sequence_active'] and not any(later['logical_outputs'].values())
                result['outputs_off_at_60s'] = True
            rows.append(result)
        score = evaluate(corpus, trace)
        results[suite] = dict(correct=score['correct'], total=count, forbidden_call_cases=score['forbidden_call_cases'],
                              incomplete=score['incomplete'], failed_stop_cases=score['failed_stop_cases'],
                              results=rows, replies_and_final_states_match=True)
    return dict(scope='Offline replay of all 88 real-platform text sessions through frozen ct65 host; no device IO',
                host_sha256=binary, **results)


def review(directory,executable):
    base=read(directory,'baseline-tools');diagnostic=read(directory,'diagnostic-tools')
    assert len(base['tools'])==len(diagnostic['tools'])==12
    for before,after in zip(base['tools'],diagnostic['tools']):
        if before['name']=='self.tank.stop':
            assert before['description']!=after['description']
            assert {k:v for k,v in before.items() if k!='description'}=={k:v for k,v in after.items() if k!='description'}
        else:assert before==after
    identity=read(directory,'baseline-C006-1')
    role=identity['role_sha256']
    binary=hashlib.sha256(executable.read_bytes()).hexdigest()
    def case_result(trace,row,case):
        assert trace['role_sha256']==role and trace['host_replay_sha256']==binary
        assert trace['model']==identity['model'] and trace['capture_source_sha256']==identity['capture_source_sha256']
        assert trace['input_mode']=='raw_text_diagnostic' and trace['fixture_version']=='firmware_host'
        assert row['id']==case['id'] and row['input_text']==case['text'] and row['context']==case['context']
        assert row['initial_profile']==firmware_profile(case['context'])
        assert len(row['host_calls'])==len(row['calls'])
        replies=[]
        for i,call in enumerate(row['host_calls']):
            assert {key:call[key] for key in ('name','arguments')}==row['calls'][i]
            replies.append(firmware_replay(executable,row['initial_profile'],row['host_calls'][:i+1])[-2])
        assert replies==row.get('host_rpc_replies',[])
        final=firmware_replay(executable,row['initial_profile'],[*row['host_calls'],dict(inspect_ms=row['host_inspect_ms'])])[-1]
        assert final==row['host_final_state']
        return summarize_case(row,case,final)
    compose_path=ROOT/'docs/validation/compose-cases.json'
    c006=next(case for case in json.loads(compose_path.read_bytes())['cases'] if case['id']=='C006')
    pilot=[]
    for group in ('baseline','diagnostic'):
        for repeat in range(1,4):
            trace=read(directory,f'{group}-C006-{repeat}')
            schema_path=directory/(group+'-tools.json')
            assert trace['tool_schema_sha256']==hashlib.sha256(schema_path.read_bytes()).hexdigest()
            assert trace['corpus_sha256']==hashlib.sha256(compose_path.read_bytes()).hexdigest()
            assert len(trace['results'])==1
            pilot.append(dict(group=group,repeat=repeat,**case_result(trace,trace['results'][0],c006)))
    corpus_path=ROOT/'docs/validation/stop-negation-cases.json'
    corpus=json.loads(corpus_path.read_bytes());expected={case['id']:case for case in corpus['cases']}
    trace=read(directory,'contrast12')
    assert trace['corpus_sha256']==hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    assert trace['tool_schema_sha256']==hashlib.sha256((directory/'diagnostic-tools.json').read_bytes()).hexdigest()
    assert len(trace['results'])==len(expected)==12 and {row['id'] for row in trace['results']}==set(expected)
    contrast=[case_result(trace,row,expected[row['id']]) for row in trace['results']]
    safe=contrast_can_proceed(contrast,expected)
    pilot_safe=all(row['strict_tool_match'] and row['draft_matches'] for row in pilot if row['group']=='diagnostic')
    return dict(scope='Offline replay of real-platform raw-text traces; no new model run, ASR, speaker or board acceptance',
                role_sha256=role,host_sha256=binary,pilot=pilot,contrast=contrast,
                contrast_strict_matches=sum(row['strict_tool_match'] for row in contrast),contrast_total=12,
                can_proceed_to_fixed_suite=bool(safe and pilot_safe),
                strict_mismatch_ids=[row['id'] for row in contrast if not row['strict_tool_match']],
                replies_and_final_states_match=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--executable',type=Path,required=True)
    parser.add_argument('--candidate-executable',type=Path)
    args=parser.parse_args()
    result = review(args.directory,args.executable)
    if args.candidate_executable:
        result['fixed_suites'] = review_fixed(args.directory,args.candidate_executable)
    print(json.dumps(result,ensure_ascii=False,indent=2))
