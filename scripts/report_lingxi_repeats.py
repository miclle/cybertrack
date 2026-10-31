#!/usr/bin/env python3
"""Summarize independent ct46 platform runs without sending messages or rewriting captures."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from evaluate_voice import evaluate

ROOT = Path(__file__).resolve().parents[1]
CORPORA = {
    'voice': 'voice-cases.json', 'compose': 'compose-cases.json', 'status': 'status-cases.json',
    'holdout': 'holdout-cases-20261031.json', 'transfer': 'ct46-transfer-cases.json',
}


def summarize(directory, replay):
    rows = []
    run_ids = set()
    pinned = None
    for round_number in (1, 2, 3):
        for suite, filename in CORPORA.items():
            path = directory / f'{round_number}-{suite}.json'
            data = path.read_bytes() if path.is_file() else gzip.decompress(path.with_suffix('.json.gz').read_bytes())
            trace = json.loads(data)
            corpus_data = (ROOT / 'docs/validation' / filename).read_bytes()
            corpus = json.loads(corpus_data)
            ids = [c['id'] for c in corpus['cases']]
            results = trace['results']
            fingerprint = tuple(trace[k] for k in ('model','role_sha256','tool_schema_sha256','capture_source_sha256'))
            if pinned is None:
                pinned = fingerprint
            if (trace['run_id'] in run_ids or fingerprint != pinned or trace['fixture_version'] != 'ct46'
                    or trace['corpus_sha256'] != hashlib.sha256(corpus_data).hexdigest()
                    or trace['input_mode'] != ('context_prefixed' if suite in ('voice','compose') else 'raw_text_diagnostic')):
                raise ValueError(f'{path.name}: incompatible or duplicate run')
            run_ids.add(trace['run_id'])
            received = [r['id'] for r in results]
            if received != ids[:len(received)]:
                raise ValueError(f'{path.name}: unexpected case order or duplicates')
            row = dict(round=round_number, suite=suite, run_id=trace['run_id'], sha256=hashlib.sha256(data).hexdigest(),
                       expected=len(ids), completed=sum(r['completed'] for r in results), missing=ids[len(received):],
                       incomplete=[r['id'] for r in results if not r['completed']])
            if suite in ('voice', 'compose'):
                score = evaluate(corpus, trace)
                row.update(exact=score['correct'], forbidden=score['forbidden_call_cases'],
                           mismatches=[r['id'] for r in score['results'] if not r['tool_calls_match']])
            if suite == 'voice':
                silent = {c['id'] for c in corpus['cases'] if '成功静默' in c['response_expectation']}
                row.update(cloud_silence_required=len(silent), cloud_silence_observed=sum(
                    r['id'] in silent and r['completed'] and not any(r['replies'])
                    and not r['received_audio_bytes_discarded'] for r in results))
            if suite == 'transfer':
                row['first_remote_packet_policy'] = {
                    r['id']: subprocess.check_output([str(replay)], input=json.dumps(r), text=True).strip()
                    for r in results
                }
            rows.append(row)
    return dict(scope='Isolated platform text with synthetic device receipts. Playback policy replay is host-only.',
                model=pinned[0], role_sha256=pinned[1], tool_schema_sha256=pinned[2],
                capture_source_sha256=pinned[3], runs=rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--replay', type=Path, default=ROOT/'build/lingxi-schema-export/replay-feedback')
    args = parser.parse_args()
    print(json.dumps(summarize(args.directory,args.replay), ensure_ascii=False, indent=2))
