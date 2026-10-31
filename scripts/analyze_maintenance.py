#!/usr/bin/env python3
"""Summarize comparable maintenance observations; never generate field measurements."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
from statistics import median

TASKS = ('补液','清洁','取瓶','换电池','线束检修')
CHECKS = ('紧固','磨线','管路','渗漏')


def analyze(data, condition, before, after=None):
    if not condition.strip() or not before.strip() or (after is not None and (not after.strip() or before == after)):
        raise ValueError('Specify a condition and distinct revision names')
    samples = {phase:{task:[] for task in TASKS} for phase in ('before','after')}
    flaws, missing, seen_ids, slots = [], [], set(), set()
    excluded = []
    cycles = 0

    def identify(row, slot):
        sample = row.get('sample_id')
        repeat = row.get('repeat')
        if not isinstance(sample,str) or not sample.strip() or type(repeat) is not int or repeat < 1:
            raise ValueError('Each selected observation needs a sample_id and positive repeat')
        if sample in seen_ids or (*slot,repeat) in slots:
            raise ValueError('Duplicate observation or repeat in the selected series')
        seen_ids.add(sample)
        slots.add((*slot,repeat))
        return sample

    def field_observation(row):
        if row.get('evidence_kind') == 'physical_observation':
            return True
        excluded.append(row.get('sample_id'))
        return False

    def recorded(row):
        return (isinstance(row.get('observed_by'),str) and bool(row['observed_by'].strip())
                and isinstance(row.get('evidence_ref'), str) and bool(row['evidence_ref'].strip())
                and isinstance(row.get('faults'),list)
                and all(isinstance(f,str) and f.strip() for f in row['faults']))

    unassigned = sum(not r.get('condition_id') for key in ('maintenance_trials','maintenance_cycles')
                     for r in data.get(key,[]))
    for row in data['maintenance_trials']:
        if row.get('condition_id') != condition: continue
        phase = row.get('before_or_after')
        if phase not in samples: raise ValueError('Unknown before_or_after value')
        revision = before if phase=='before' else after
        if revision is None or row.get('revision') != revision: continue
        if not field_observation(row): continue
        task = row['task']
        if task not in TASKS: raise ValueError('Unknown maintenance task')
        sample = identify(row,(phase,task))
        if row.get('faults'): flaws.append(sample)
        duration = row.get('duration_s')
        if (not recorded(row) or row.get('completed') is not True
                or not isinstance(row.get('steps'), list) or not row['steps']
                or not all(isinstance(step, str) and step.strip() for step in row['steps'])
                or not isinstance(row.get('tools'),list) or not all(isinstance(t,str) and t.strip() for t in row['tools'])
                or type(duration) not in (float,int) or not Decimal(str(duration)).is_finite() or duration <= 0):
            missing.append(sample)
            continue
        samples[phase][task].append(Decimal(str(duration)))

    for row in data.get('maintenance_cycles',[]):
        if not after or row.get('condition_id')!=condition or row.get('revision')!=after: continue
        if not field_observation(row): continue
        sample = identify(row,('cycle',))
        if row.get('faults'): flaws.append(sample)
        checks = row.get('checks')
        if (not recorded(row) or row.get('completed') is not True or not isinstance(checks,dict) or set(checks)!=set(CHECKS)
                or any(v not in ('ok','issue') for v in checks.values())
                or ('issue' in checks.values() and not row['faults'])):
            missing.append(sample)
            continue
        cycles += 1

    medians = {phase:{t:median(v) for t,v in groups.items() if len(v)>=3} for phase,groups in samples.items()}
    baseline = medians['before']
    targets = sorted(TASKS,key=lambda t:-baseline[t])[:2] if len(baseline)==len(TASKS) else []
    comparisons = {}
    for task in targets:
        new = medians['after'].get(task)
        if new is not None:
            gain = (baseline[task]-new)/baseline[task]
            comparisons[task] = dict(reduction_percent=float(round(100*gain,2)),at_least_30_percent=gain>=Decimal('.30'))
    return dict(condition=condition,before=before,after=after,
                counts={p:{t:len(v) for t,v in groups.items()} for p,groups in samples.items()},
                median_seconds={p:{t:float(v) for t,v in values.items()} for p,values in medians.items()},
                slowest_two=targets,comparisons=comparisons,complete_cycles=cycles,ten_cycles_recorded=cycles>=10,
                excluded_nonphysical_or_unclassified=excluded, incomplete_samples=missing,observations_with_faults=flaws,unassigned_observations=unassigned)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('records',type=Path)
    parser.add_argument('--condition',required=True)
    parser.add_argument('--before',required=True)
    parser.add_argument('--after')
    args = parser.parse_args()
    try:
        print(json.dumps(analyze(json.loads(args.records.read_text()),args.condition,args.before,args.after),
                         ensure_ascii=False,indent=2))
    except (KeyError,ValueError) as exc: parser.error(str(exc))
