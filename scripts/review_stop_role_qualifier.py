#!/usr/bin/env python3
"""Review a bounded role-only comparison with retained actual MCP host replies."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from capture_lingxi import firmware_profile, firmware_replay
from evaluate_voice import canonical

ROOT = Path(__file__).resolve().parents[1]
SELECTED = {'voice': ['V045', 'V049', 'V051', 'V053', 'V058'], 'compose': ['C004', 'C008']}


def read(directory, name):
    path = directory/(name+'.json.gz')
    return json.loads(gzip.decompress(path.read_bytes()) if path.exists() else (directory/(name+'.json')).read_bytes())


def review(directory, executable):
    identity = read(directory, 'baseline-voice')
    binary = hashlib.sha256(executable.read_bytes()).hexdigest()
    role_hashes = {group: hashlib.sha256((directory/name).read_bytes()).hexdigest()
                   for group, name in [('baseline', 'baseline-role.txt'), ('candidate', 'proposed-role.txt')]}
    before = (directory/'baseline-role.txt').read_text()
    after = (directory/'proposed-role.txt').read_text()
    anchor = '全部逻辑输出关闭、无异常且序列和狂暴模式均未运行，才可说'
    assert before.count(anchor) == 1 and after == before.replace(anchor, '状态查询时，'+anchor)
    assert len(after.rstrip('\n')) <= 6000
    groups = {}
    for group in ('baseline', 'candidate'):
        rows = []
        for suite, ids in SELECTED.items():
            corpus_path = ROOT/f'docs/validation/{suite}-cases.json'
            expected = {case['id']: case for case in json.loads(corpus_path.read_bytes())['cases']}
            trace = read(directory, f'{group}-{suite}')
            assert trace['host_replay_sha256'] == binary
            assert trace['corpus_sha256'] == hashlib.sha256(corpus_path.read_bytes()).hexdigest()
            assert trace['role_sha256'] == role_hashes[group]
            for key in ('model', 'capture_source_sha256', 'tool_schema_sha256'):
                assert trace[key] == identity[key]
            assert trace['input_mode'] == 'raw_text_diagnostic' and trace['fixture_version'] == 'firmware_host'
            assert [row['id'] for row in trace['results']] == ids
            for row in trace['results']:
                case = expected[row['id']]
                assert type(row['completed']) is bool
                assert row['input_text'] == case['text'] and row['context'] == case['context']
                assert row['initial_profile'] == firmware_profile(case['context'])
                calls = row['host_calls']
                assert [{key:call[key] for key in ('name', 'arguments')} for call in calls] == row['calls']
                replies = [firmware_replay(executable, row['initial_profile'], calls[:i+1])[-2] for i in range(len(calls))]
                assert replies == row.get('host_rpc_replies', [])
                final = firmware_replay(executable, row['initial_profile'], [*calls, dict(inspect_ms=row['host_inspect_ms'])])[-1]
                assert final == row['host_final_state']
                initial = firmware_replay(executable, row['initial_profile'], [])[-1]
                rows.append(dict(id=row['id'], completed=row['completed'], calls=row['calls'],
                                 strict_match=row['completed'] and canonical(row['calls']) == canonical(case['expected_calls']),
                                 reply=''.join(row['replies']), reply_characters=len(''.join(row['replies'])),
                                 final_revision=final['show_draft']['revision'], starts=final['starts_this_boot'],
                                 draft_unchanged=final['show_draft']['revision']==initial['show_draft']['revision']
                                     and final['show_draft']['steps']==initial['show_draft']['steps'],
                                 outputs_off=not any(final['logical_outputs'].values())))
        groups[group] = dict(strict_matches=sum(row['strict_match'] for row in rows), total=7,
                             stop_reply_characters=sum(row['reply_characters'] for row in rows if row['id'] in SELECTED['voice'][:3]),
                             rows=rows)
    candidate = {row['id']: row for row in groups['candidate']['rows']}
    ambiguous = candidate['C008']
    checks = dict(all_completed=all(row['completed'] for row in candidate.values()),
                  required_calls_match=all(candidate[cid]['strict_match'] for cid in ['V045','V049','V051','V053','V058','C004']),
                  cancel_draft_cleared=candidate['C004']['final_revision']==0 and candidate['C004']['starts']==0,
                  ambiguous_edit_preserved=ambiguous['draft_unchanged'] and ambiguous['starts']==0 and ambiguous['outputs_off']
                      and all(call['name'].replace('self_tank_', 'self.tank.', 1)=='self.tank.get_status' for call in ambiguous['calls']),
                  stop_text_reduced=groups['candidate']['stop_reply_characters'] < groups['baseline']['stop_reply_characters'])
    return dict(scope='Offline review of fourteen platform text sessions, not full-suite, speaker or board acceptance',
                host_sha256=binary, role_hashes=role_hashes, groups=groups, checks=checks,
                preflight_checks_met=all(checks.values()), replies_and_final_states_match=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--executable', type=Path, required=True)
    args=parser.parse_args()
    print(json.dumps(review(args.directory,args.executable), ensure_ascii=False, indent=2))
