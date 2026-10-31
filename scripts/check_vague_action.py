#!/usr/bin/env python3
"""Exercise actual MCP admission for generic recognized action requests; no IO."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from capture_lingxi import firmware_replay

ROOT = Path(__file__).resolve().parents[1]


def check(executable):
    def call(name, args=None, ms=10, rpc=1, **extra):
        return dict(name='self.tank.'+name, arguments=args or {}, elapsed_ms=ms, rpc_id=rpc, **extra)

    def text(value, ms=0):
        return dict(input_text=value, elapsed_ms=ms)

    def receipt(wire):
        if 'error' in wire:
            return dict(result='rpc_error', message=wire['error']['message'])
        return json.loads(wire['result']['content'][0]['text'])

    results = []

    def run(name, commands, verify, profile='corpus_idle'):
        wires = firmware_replay(executable, profile, commands, await_stt=True)
        replies = [receipt(w) for w in wires[:-1]]
        results.append(dict(name=name, passed=bool(verify(replies, wires[-1])), profile=profile,
                            commands=commands, receipts=replies, final_state=wires[-1]))

    idle = lambda s: s['starts_this_boot'] == 0 and not any(s['logical_outputs'].values())
    move = dict(direction='forward', duration_ms=1000)
    for phrase in ('动一下那个东西', '让那个东西动起来', '移动一下', '转一下那个东西', '启动一下它', '来个效果', '动一下三秒'):
        run(phrase, [text(phrase), call('move', move)],
            lambda r, s: r[0]['result'] == 'action_unspecified' and bool(r[0].get('clarification_facts')) and idle(s))

    for tool, args in [('water', dict(duration_ms=1000)), ('bubbles', dict(duration_ms=1000)),
                       ('ignition', dict(duration_ms=1000)), ('frenzy', dict(duration_ms=1000)),
                       ('sequence', dict(steps_json='[{"direction":"left","move_ms":880,"water_ms":0,"bubbles_ms":0,"ignition_ms":0}]'))]:
        run('cannot_substitute_'+tool, [text('来个效果'), call(tool, args)],
            lambda r, s: r[0]['result'] == 'action_unspecified' and idle(s))

    run('query_fallback_latch_and_new_explicit_input', [text('动一下那个东西'), call('get_status'),
        call('move', move, 20, 2), call('bubbles', dict(duration_ms=1000), 30, 3), call('get_status', ms=40, rpc=4),
        text('前进一秒', 50), call('move', move, 60, 5)],
        lambda r, s: r[0]['result'] == r[3]['result'] == 'ok' and r[1]['result'] == 'action_unspecified'
        and r[2]['result'] == 'rpc_error' and 'voice_input_failed' in r[2]['message']
        and r[4]['result'] == 'accepted' and s['starts_this_boot'] == 1)

    run('blank_input_cannot_clear_guard', [text('动一下那个东西'), text(' \t ', 5), call('move', move)],
        lambda r, s: r[0]['result'] == 'action_unspecified' and idle(s))

    run('generic_query_does_not_stop_existing_motion', [text('那个动了吗'), call('get_status')],
        lambda r, s: r[0]['result'] == 'ok' and s['starts_this_boot'] == 1 and s['logical_outputs']['left'], 'corpus_forward70')

    run('vague_speed_cannot_change_existing_motion', [text('动一下那个东西'), call('set_speed', dict(speed_percent=100))],
        lambda r, s: r[0]['result'] == 'action_unspecified' and s['move_speed_percent'] == 70
        and s['starts_this_boot'] == 1, 'corpus_forward70')

    run('stop_remains_immediate_after_rejection', [text('动一下那个东西，停下'), call('set_speed', dict(speed_percent=100)),
        call('stop', ms=20, rpc=2, defer=True), dict(inspect_ms=60000)],
        lambda r, s: r[0]['result'] == 'action_unspecified' and r[1]['result'] == 'ok'
        and not any(s['logical_outputs'].values()) and not s['sequence_active'], 'corpus_sequence')

    run('old_queued_action_cannot_bypass_new_guard', [text('前进一秒'), call('move', move, defer=True),
        text('动一下那个东西', 20), dict(flush=True, elapsed_ms=30), call('move', move, 40, 2)],
        lambda r, s: r[0]['result'] == 'voice_input_changed' and r[1]['result'] == 'action_unspecified' and idle(s))

    edit = dict(edit='replace_step', revision=7, step=2,
                steps_json='[{"direction":"none","move_ms":0,"water_ms":0,"bubbles_ms":2000,"ignition_ms":0}]')
    run('creative_draft_is_allowed_without_actuation', [text('帮我编排一个表演，你来想动作'),
        call('get_status'), call('compose', edit, 20, 2)],
        lambda r, s: r[1]['result'] == 'draft_saved' and s['show_draft']['revision'] == 8 and idle(s), 'corpus_draft7')

    new_draft = dict(edit='replace', revision=0, step=0,
                     steps_json='[{"direction":"left","move_ms":880,"water_ms":0,"bubbles_ms":1000,"ignition_ms":0}]')
    run('creative_new_draft_keeps_read_version_gate', [text('帮我编排一个表演，你来想动作'),
        call('get_status'), call('compose', new_draft, 20, 2)],
        lambda r, s: r[1]['result'] == 'draft_saved' and s['show_draft']['revision'] == 1 and idle(s))

    run('relative_edit_guard_still_precedes_creative_draft', [text('第二步动作短一点'),
        call('get_status'), call('compose', edit, 20, 2)],
        lambda r, s: r[1]['result'] == 'draft_duration_unspecified' and s['show_draft']['revision'] == 7 and idle(s), 'corpus_draft7')

    for phrase, tool, args in [('让那个小车向前动两秒', 'move', dict(direction='forward', duration_ms=2000)),
                               ('向右转一下那个机器人', 'move', dict(direction='right', duration_ms=880)),
                               ('启动一下泡泡', 'bubbles', dict(duration_ms=1000)),
                               ('开枪一秒', 'water', dict(duration_ms=1000))]:
        run('named_'+phrase, [text(phrase), call(tool, args)],
            lambda r, s: r[0]['result'] == 'accepted' and s['starts_this_boot'] == 1)

    archive = ROOT/'docs/validation/evidence/stop-negation/full-voice.json.gz'
    original = json.loads(gzip.decompress(archive.read_bytes()))
    row = next(row for row in original['results'] if row['id'] == 'V079')
    run('retained_V079_with_simulated_recognized_text', [text(row['input_text']), *row['host_calls'],
        dict(inspect_ms=row['host_inspect_ms'])],
        lambda r, s: any(v['result'] == 'action_unspecified' for v in r) and idle(s))

    return dict(scope='Actual MCP with simulated recognized input/clock and no board IO; historical V079 is not a new model or ASR score',
                host_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                archived_source_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), scenarios=len(results),
                passed=all(r['passed'] for r in results), failed=[r['name'] for r in results if not r['passed']], results=results)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--executable', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    report = check(args.executable)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k != 'results'}, ensure_ascii=False))
    raise SystemExit(0 if report['passed'] else 1)
