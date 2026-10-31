#!/usr/bin/env python3
"""Reproduce the paired native-step experiment without contacting a platform or device."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from evaluate_voice import evaluate
from review_firmware_capture import require, review

ROOT = Path(__file__).resolve().parents[1]


def read(directory, name):
    path = directory / name
    if path.exists():
        return json.loads(path.read_bytes())
    return json.loads(gzip.decompress(path.with_suffix(path.suffix + '.gz').read_bytes()))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(directory, baseline_executable, candidate_executable):
    inventory = read(directory, 'experiment.json')['files']
    require(set(inventory) == {p.name for p in directory.iterdir() if p.is_file() and p.name != 'experiment.json'}, 'archive inventory differs')
    for name, entry in inventory.items():
        require(Path(name).name == name and digest(directory / name) == entry['sha256']
                and (directory / name).stat().st_size == entry['bytes'], 'archived artifact differs: ' + name)
    plan = read(directory, 'plan.json')
    require(plan['repeats'] == 1, 'unexpected experiment repetitions')
    tools = {group: read(directory, group + '-tools.json')['tools'] for group in ('baseline', 'candidate')}
    require(len(tools['baseline']) == len(tools['candidate']) == 12, 'tool count changed')
    require([t['name'] for t in tools['baseline']] == [t['name'] for t in tools['candidate']], 'tool order changed')
    changed = [before['name'] for before, after in zip(tools['baseline'], tools['candidate']) if before != after]
    require(changed == plan['changed_tools'], 'undeclared tool changes')
    old = 'sequence唯一参数steps_json，是JSON数组编码成的字符串，最多16步，不自动拆单。'
    new = 'sequence唯一参数steps，是步骤对象数组，直接传数组而非JSON字符串，最多16步，不自动拆单。'
    baseline_role = (directory / 'baseline-role.txt').read_text()
    require(baseline_role.count(old) == 1, 'baseline role anchor differs')
    require(baseline_role.replace(old, new) == (directory / 'candidate-role.txt').read_text(), 'unrelated role changes')
    groups = {}
    for group, executable, wire in (('baseline', baseline_executable, 'legacy_string'),
                                    ('candidate', candidate_executable, 'native_array')):
        require(digest(executable) == plan[group + '_host_sha256'], 'host binary differs')
        role_hash = digest(directory / (group + '-role.txt'))
        require(role_hash == plan[group + '_role_sha256'], 'role snapshot differs')
        for tool in tools[group]:
            if tool['name'] in changed:
                schema = tool['inputSchema']
                key, kind = ('steps', 'array') if wire == 'native_array' else ('steps_json', 'string')
                require(key in schema['required'] and schema['properties'][key]['type'] == kind, 'advertised step schema differs')
        if group == 'candidate':
            manifest = read(executable.parent, 'manifest.json')
            require(read(directory, 'candidate-host-manifest.json') == manifest, 'archived candidate manifest differs')
            require(manifest['executable_sha256'] == digest(executable), 'candidate manifest differs')
            require(manifest['tool_catalog_sha256'] == digest(executable.parent / 'tool-catalog.json'), 'catalog hash differs')
            require(read(executable.parent, 'tool-catalog.json') == tools[group], 'compiled and advertised tools differ')
        suites = {}
        for suite, count in (('voice', 80), ('compose', 8)):
            trace = read(directory, group + '-' + suite + '.json')
            require(trace['role_sha256'] == role_hash, 'captured role identity differs')
            capture_key = 'capture_source_sha256' if group == 'baseline' else 'candidate_capture_source_sha256'
            require(trace['capture_source_sha256'] == plan[capture_key], 'capture source differs')
            require(trace['host_input_mode'] == 'simulated_recognized_text', 'not simulated recognized originals')
            require(trace['tool_schema_sha256'] == digest(directory / (group + '-tools.json')), 'captured schema differs')
            require(trace['model'] == 'deepseek-v4-flash', 'model label differs')
            require(trace.get('step_argument_format', wire) == wire, 'captured wire declaration differs')
            # Old captures predate the declaration. Derive it from their saved
            # advertised schema for this review only; never rewrite wire calls.
            checked_trace = dict(trace, step_argument_format=wire)
            corpus_path = ROOT / ('docs/validation/' + suite + '-cases.json')
            corpus = json.loads(corpus_path.read_bytes())
            require([r['id'] for r in trace['results']] == [c['id'] for c in corpus['cases']], 'missing/reordered fixed cases')
            reproduced = review(checked_trace, executable, corpus_path)
            require(reproduced['cases'] == reproduced['completed'] == count, 'incomplete fixed suite')
            score = evaluate(corpus, checked_trace)
            suites[suite] = dict(score=score, replay=reproduced)
        groups[group] = dict(host_sha256=digest(executable), role_sha256=role_hash, wire_format=wire, suites=suites)
    numerical_gate = all(groups['candidate']['suites'][s]['score']['correct'] >= groups['baseline']['suites'][s]['score']['correct']
                         and len(groups['candidate']['suites'][s]['score']['invalid_tool_argument_cases']) <=
                             len(groups['baseline']['suites'][s]['score']['invalid_tool_argument_cases']) for s in ('voice', 'compose'))
    restoration = read(directory, 'restored-platform-readback.json')
    baseline_platform = read(directory, 'baseline-platform-readback.json')
    require(restoration['roleSha256'] == plan['baseline_role_sha256'] and restoration['reopened'], 'platform role not restored')
    require(restoration['parameters'] == baseline_platform['parameters'] and restoration['model'] == baseline_platform['model'], 'platform settings differ')
    restored_source = read(directory, 'restored-source-check.json')
    require(restored_source['source_version'] == '2.0.3-ct68' and restored_source['recorded_deployment'] == '2.0.3-ct45'
            and restored_source['role_sha256'] == plan['baseline_role_sha256']
            and restored_source['local_source_image_checked'] and restored_source['local_deployed_image_checked'], 'source restoration differs')
    return dict(scope='176 real-platform text sessions, simulated recognized originals, frozen actual MCP hosts; no ASR, speaker or board IO',
                groups=groups, numerical_adoption_gate_met=numerical_gate, adopted=False,
                decision='Reject: both original fixed suites regress; forbidden control calls remain. No failed sample was replaced.',
                all_176_rpc_histories_and_final_states_reproduced=True,
                platform_restored_to_baseline=True, device_deployed=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--baseline-executable', type=Path, required=True)
    p.add_argument('--candidate-executable', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = summarize(a.directory, a.baseline_executable, a.candidate_executable)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'groups'}, ensure_ascii=False))
