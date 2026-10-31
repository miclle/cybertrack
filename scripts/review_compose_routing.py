#!/usr/bin/env python3
"""Recompute the two-case compose description experiment without a model or device."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import statistics

from evaluate_voice import canonical

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/validation/evidence/compose-routing'


def read_capture(folder, run):
    path = folder / run['capture']
    if path.resolve().parent != folder.resolve():
        raise ValueError('capture must be in the experiment directory')
    raw = path.read_bytes()
    raw = gzip.decompress(raw) if path.suffix == '.gz' else raw
    if hashlib.sha256(raw).hexdigest() != run['capture_json_sha256']:
        raise ValueError('capture differs from experiment manifest')
    return json.loads(raw)


def review(folder=EVIDENCE):
    experiment = json.loads((folder / 'experiment.json').read_bytes())
    corpus_raw = (ROOT / 'docs/validation/compose-cases.json').read_bytes()
    corpus_hash = hashlib.sha256(corpus_raw).hexdigest()
    cases = {c['id']: c for c in json.loads(corpus_raw)['cases']}
    expected = {(group, cid, round_no) for group in ('baseline', 'route')
                for cid in ('C005', 'C008') for round_no in range(1, 4)}
    seen, rows, shared = set(), [], None
    schemas = {}
    for group in ('baseline', 'route'):
        spec = experiment['schemas'][group]
        raw = (folder / spec['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != spec['sha256']:
            raise ValueError('schema differs from experiment manifest')
        schemas[group] = {t['name']: t for t in json.loads(raw)['tools']}
    if set(schemas['baseline']) != set(schemas['route']) or len(schemas['baseline']) != 12:
        raise ValueError('experiment must retain the twelve tool names')
    changed = []
    for name, tool in schemas['baseline'].items():
        other = schemas['route'][name]
        if tool != other:
            if {k: v for k, v in tool.items() if k != 'description'} != {k: v for k, v in other.items() if k != 'description'}:
                raise ValueError('experiment changed more than descriptions')
            changed.append(name)
    if set(changed) != {'self.tank.get_status', 'self.tank.compose'}:
        raise ValueError('unexpected description changes')
    initial_steps = [dict(direction='left', move_ms=880, water_ms=0, bubbles_ms=0, ignition_ms=0, speed_percent=100),
                     dict(direction='none', move_ms=0, water_ms=0, bubbles_ms=1000, ignition_ms=0, speed_percent=100)]
    for run in experiment['runs']:
        key = run['group'], run['case_id'], run['round']
        if key not in expected or key in seen:
            raise ValueError('duplicate or unknown experiment session')
        seen.add(key)
        trace = read_capture(folder, run)
        if len(trace['results']) != 1 or trace['corpus_sha256'] != corpus_hash:
            raise ValueError('unexpected capture corpus or result count')
        row = trace['results'][0]
        cid = run['case_id']
        identity = tuple(trace[k] for k in ('model', 'role_sha256', 'host_replay_sha256', 'input_mode', 'capture_source_sha256'))
        if shared is None:
            shared = identity
        if (shared != identity or trace['kind'] != 'captured_tool_calls' or trace['fixture_version'] != 'firmware_host'
                or trace['input_mode'] != 'raw_text_diagnostic' or trace['host_replay_sha256'] != experiment['host_sha256']
                or trace['tool_schema_sha256'] != experiment['schemas'][run['group']]['sha256']
                or row['id'] != cid or row['input_text'] != cases[cid]['text'] or row['context'] != cases[cid]['context']
                or row['initial_profile'] != 'corpus_draft7' or type(row['completed']) is not bool):
            raise ValueError('incompatible experiment capture')
        state = row['host_final_state']
        draft = state['show_draft']
        preserved = draft['active'] and draft['revision'] == 7 and draft['source'] == 'voice' and draft['steps'] == initial_steps
        rows.append(dict(group=run['group'], case_id=cid, round=run['round'], capture=run['capture'], run_id=trace['run_id'],
                         completed=row['completed'], completion=row['completion'], elapsed_ms=row['host_inspect_ms'],
                         tool_calls_match=row['completed'] and canonical(row['calls']) == canonical(cases[cid]['expected_calls']),
                         draft_preserved=preserved, final_draft=draft, starts=state['starts_this_boot'], logical_outputs=state['logical_outputs'],
                         calls=row['calls'], replies=row['replies'], reply_characters=sum(len(s) for s in row['replies'])))
    if seen != expected:
        raise ValueError('experiment requires all twelve original sessions')
    groups = {}
    for group in ('baseline', 'route'):
        subset = [r for r in rows if r['group'] == group]
        groups[group] = dict(sessions=len(subset), completed=sum(r['completed'] for r in subset),
                             tool_calls_match=sum(r['tool_calls_match'] for r in subset),
                             incomplete=[r['capture'] for r in subset if not r['completed']],
                             unexpected_draft_changes=[r['capture'] for r in subset if not r['draft_preserved']],
                             sessions_with_starts=sum(r['starts'] != 0 for r in subset),
                             sessions_with_active_outputs=sum(any(r['logical_outputs'].values()) for r in subset),
                             median_elapsed_ms=statistics.median(r['elapsed_ms'] for r in subset),
                             median_reply_characters=statistics.median(r['reply_characters'] for r in subset))
    return dict(scope='Two-case raw-text description-only diagnostic; all original sessions retained. Not a full fixed-suite score, speech or physical acceptance.',
                decision='not_adopted', reason='Variant changed a draft without an explicit new duration; process narration also remains.',
                groups=groups, rows=rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=EVIDENCE)
    print(json.dumps(review(parser.parse_args().evidence), ensure_ascii=False, indent=2))
