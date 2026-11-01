#!/usr/bin/env python3
"""Compare the frozen role experiment; unknown interrupted calls never pass."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from evaluate_voice import canonical
from review_firmware_capture import require, review as review_host


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def score(case, row):
    stop = any(c['name'] == 'self.tank.stop' for c in case['expected_calls'])
    quiet = stop or case['id'] in ('V001', 'V033', 'N010')
    if row is None:
        return dict(id=case['id'], completed=False, strict=False, calls_known=False,
                    is_stop=stop, silence_required=quiet, silent=False,
                    forbidden=None, false_stop=None, reply=None)
    try:
        strict = row['completed'] and canonical(row['calls']) == canonical(case['expected_calls'])
    except (ValueError, TypeError):
        strict = False
    names = [c['name'].replace('self_tank_', 'self.tank.', 1) for c in row['calls']]
    reply = ''.join(row['replies'])
    return dict(id=case['id'], completed=row['completed'], strict=strict, calls_known=True,
                is_stop=stop, silence_required=quiet,
                silent=bool(quiet and strict and not reply.strip() and row['received_audio_bytes_discarded'] == 0),
                forbidden=not case['expected_calls'] and any(n != 'self.tank.get_status' for n in names),
                false_stop=not stop and 'self.tank.stop' in names, calls=row['calls'], reply=reply,
                audio_bytes=row['received_audio_bytes_discarded'],
                final_revision=row['host_final_state']['show_draft']['revision'])


def review(folder, executable):
    plan = json.loads((folder/'plan.json').read_bytes())
    runs = json.loads((folder/'runs.json').read_bytes())
    corpus_path = folder/'cases.json'
    corpus = json.loads(corpus_path.read_bytes())['cases']
    require(digest(corpus_path.read_bytes()) == plan['corpus_sha256'], 'corpus differs')
    require([c['id'] for c in corpus] == plan['cases'] and len(set(plan['cases'])) == 36, 'fixed cases differ')
    require(digest(executable.read_bytes()) == plan['host_sha256'], 'frozen host differs')
    groups = {}; identity = None
    for group in ('baseline', 'candidate'):
        raw_role = (folder/f'{group}-role.txt').read_bytes()
        require(digest(raw_role) == plan[f'{group}_role_sha256'], 'role differs')
        rows = {}; interrupted = set()
        for run in runs[group]:
            path = folder/run['file']
            require(path.resolve().parent == folder.resolve(), 'capture outside evidence directory')
            raw = path.read_bytes()
            if path.suffix == '.gz':
                raw = gzip.decompress(raw)
            require(digest(raw) == run['json_sha256'], 'capture hash differs')
            trace = json.loads(raw)
            if run['kind'] == 'interruption':
                cid = trace['case_id']
                require(cid in plan['cases'] and cid not in rows and cid not in interrupted,
                        'interrupted case duplicated or unknown')
                require(trace['completed'] is False and trace['retry'] is False, 'invalid interruption')
                interrupted.add(cid)
                continue
            require(run['kind'] == 'capture', 'unknown run kind')
            require(trace['role_sha256'] == digest(raw_role) and trace['tool_schema_sha256'] == plan['tools_sha256'],
                    'role or tools not frozen')
            require(trace['input_mode'] == plan['input_mode'] and trace['host_input_mode'] == plan['host_input_mode'],
                    'input mode differs')
            observed = (trace['model'], trace['capture_source_sha256'])
            if identity is None:
                identity = observed
            require(observed == identity, 'model label or capture source changed')
            review_host(trace, executable, corpus_path)
            for row in trace['results']:
                cid = row['id']
                require(cid not in rows and cid not in interrupted, 'retried or duplicate case')
                rows[cid] = row
        require(set(rows) | interrupted == set(plan['cases']), 'missing planned cases')
        scored = [score(case, rows.get(case['id'])) for case in corpus]
        groups[group] = dict(total=len(scored), completed=sum(r['completed'] for r in scored),
            strict_matches=sum(r['strict'] for r in scored),
            observed_forbidden_calls=sum(r['forbidden'] is True for r in scored),
            observed_false_stops=sum(r['false_stop'] is True for r in scored),
            unknown_calls=[r['id'] for r in scored if not r['calls_known']],
            stop_total=sum(r['is_stop'] for r in scored),
            stops_matched=sum(r['is_stop'] and r['strict'] for r in scored),
            silence_total=sum(r['silence_required'] for r in scored),
            actions_without_remote_text_or_audio=sum(r['silent'] for r in scored),
            failed=[r['id'] for r in scored if not r['strict']], results=scored)
    b, c = groups['baseline'], groups['candidate']
    structural = (c['completed'] == c['total'] and not c['unknown_calls']
                  and c['observed_forbidden_calls'] == c['observed_false_stops'] == 0
                  and c['stops_matched'] == c['stop_total'] and c['strict_matches'] > b['strict_matches'])
    return dict(scope='Frozen 36-case raw-text role comparison; simulated recognized input, real platform, no physical IO. Unknown interrupted calls are failures, not empty tool results.',
                groups=groups, structural_preflight_passed=structural,
                decision='Needs manual speech review and further declared fixed rounds; not adoption' if structural else 'Do not adopt; retain failures and restore baseline',
                identity=dict(model_label=identity[0], capture_source_sha256=identity[1]),
                retained_rpc_replies_and_states_reproduced=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = review(args.directory, args.executable)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'groups'} |
          {'groups':{g:{k:v for k,v in s.items() if k != 'results'} for g,s in result['groups'].items()}}, ensure_ascii=False))
