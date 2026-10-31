#!/usr/bin/env python3
"""Review targeted wire-field observations without inventing model phase labels."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from review_firmware_capture import require, review
from review_full_speech import score_speech

ROOT = Path(__file__).resolve().parents[1]


def inspect(trace, executable, corpus_path):
    require(trace.get('protocol_observations_recorded') is True, 'protocol observation not enabled')
    actual = review(trace, executable, corpus_path)
    speech = score_speech(json.loads(corpus_path.read_bytes()), trace)
    rows = []
    for row in trace['results']:
        messages = row['protocol_observations']
        times = [m['ms'] for m in messages]
        require(all(type(t) is int and t >= 0 for t in times) and times == sorted(times), 'invalid observation clock')
        stages, reasoning, thinking = [], [], []
        shapes = []
        for msg in messages:
            require(set(msg) == {'ms','fields','signals','nested'}, 'unexpected observation data')
            kind = msg['signals'].get('type', 'other')
            if kind not in ('tts', 'llm'): continue
            signature = dict(type=kind, fields=msg['fields'], signals=msg['signals'], nested=msg['nested'])
            if signature not in shapes: shapes.append(signature)
            for prefix, fields in [('', msg['fields']), *[(k+'.',v) for k,v in msg['nested'].items()]]:
                stages.extend(prefix+k for k in ('phase','stage','channel') if k in fields)
                reasoning.extend(prefix+k for k in ('reasoning_content','reasoning','thinking') if k in fields)
            if kind == 'llm' and msg['signals'].get('action') == 'thinking': thinking.append(msg['ms'])
        first = lambda event: next((e['ms'] for e in row['timeline'] if e['event'] == event), None)
        tool, audio, sentence = first('tool_call'), first('first_audio'), first('tts_sentence_start')
        rows.append(dict(id=row['id'], completed=row['completed'], phase_fields=sorted(set(stages)),
            reasoning_fields=sorted(set(reasoning)), thinking_actions=len(thinking), shapes=shapes,
            first_tool_ms=tool, first_audio_ms=audio, first_sentence_ms=sentence,
            audio_before_first_tool=tool is not None and audio is not None and audio < tool,
            sentence_before_first_tool=tool is not None and sentence is not None and sentence < tool,
            replies=row['replies']))
    return dict(scope='Targeted synthetic speech only; field absence applies only to observed packets, not global platform support',
        host_review=actual, subset_tools=dict(scored=speech['tools']['scored'],correct=speech['tools']['correct'],
            forbidden_call_cases=speech['tools']['forbidden_call_cases'],incomplete=speech['tools']['incomplete']),
        subset_transcription=dict(observed=speech['transcription']['observed'],matches=speech['transcription']['matches']),
        phase_fields=sorted({f for r in rows for f in r['phase_fields']}),
        reasoning_fields=sorted({f for r in rows for f in r['reasoning_fields']}), results=rows)


def summarize(directory, executable):
    plan = json.loads((directory/'plan.json').read_bytes())
    require(hashlib.sha256(executable.read_bytes()).hexdigest() == plan['host_sha256'], 'host differs from plan')
    result = dict(scope='Paired targeted protocol observation, not full model evaluation or physical acceptance', groups={})
    for group, prefix in [('baseline',''), ('candidate','candidate-')]:
        suites = {}
        for suite, ids in plan['ids'].items():
            path = directory/f'{prefix}{suite}.json'
            raw = path.read_bytes() if path.exists() else gzip.decompress(path.with_suffix('.json.gz').read_bytes())
            trace = json.loads(raw)
            require([r['id'] for r in trace['results']] == ids, 'missing, reordered or repeated targeted case')
            require(trace['tool_schema_sha256'] == hashlib.sha256((directory/'tools.json').read_bytes()).hexdigest(), 'tool export differs')
            for key in ('host_replay_sha256','role_sha256','capture_source_sha256'):
                require(trace[key] == plan['host_sha256' if key == 'host_replay_sha256' else key], 'capture identity differs: '+key)
            suites[suite] = inspect(trace, executable, ROOT/f'docs/validation/{suite}-cases.json')
        result['groups'][group] = suites
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.directory, args.executable.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
