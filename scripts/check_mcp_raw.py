#!/usr/bin/env python3
"""Exercise original JSON fidelity and actual MCP admission; no board IO."""
import argparse
import hashlib
import json
from pathlib import Path

from capture_lingxi import firmware_replay


def scenarios():
    def call(name, arguments, **extra):
        return dict(name='self.tank.'+name, arguments=arguments, **extra)
    read=call('get_status', {})
    stop=call('stop', {})
    move=call('move', dict(direction='forward', duration_ms=1000))
    steps=json.dumps([dict(direction='left', move_ms=880, water_ms=0, bubbles_ms=0, ignition_ms=0)])
    edit=dict(edit='replace_step', revision=7, step=2, steps_json=json.dumps([
        dict(direction='none', move_ms=0, water_ms=0, bubbles_ms=2000, ignition_ms=0)]))
    cancel=dict(edit='cancel', revision=7, step=0, steps_json='')
    return [
        dict(id='direction-zero', calls=[call('move',dict(direction='forward\0extra',duration_ms=1000))], starts=0, error='embedded zero'),
        dict(id='combined-zero', calls=[call('move_and_water',dict(direction='left\0extra',move_duration_ms=880,water_duration_ms=1000))], starts=0,error='embedded zero'),
        dict(id='tool-name-zero', calls=[call('water\0extra',dict(duration_ms=1000))],starts=0,error='embedded zero'),
        dict(id='key-zero',calls=[call('move',{'direction\0extra':'forward','duration_ms':1000})],starts=0,error='embedded zero'),
        dict(id='cancel-zero',profile='corpus_draft7',calls=[read,call('compose',dict(cancel,edit='cancel\0extra'))],starts=0,revision=7,error='embedded zero'),
        dict(id='edit-zero',profile='corpus_draft7',calls=[read,call('compose',dict(edit,edit='replace_step\0extra'))],starts=0,revision=7,error='embedded zero'),
        dict(id='bad-stop-does-not-stop',profile='corpus_forward70',calls=[call('stop\0extra',{})],starts=1,moving=True,error='embedded zero'),
        dict(id='valid-stop-after-bad',profile='corpus_forward70',calls=[call('stop\0extra',{}),stop],starts=1,moving=False,results=['error','ok']),
        dict(id='same-input-no-fallback',calls=[call('move',dict(direction='forward\0extra',duration_ms=1000)),call('bubbles',dict(duration_ms=1000))],starts=0,results=['error','error'],error='voice_input_failed'),
        dict(id='new-input-restores',calls=[call('move',dict(direction='forward\0extra',duration_ms=1000)),dict(input_text='吹泡泡一秒'),call('bubbles',dict(duration_ms=1000))],starts=1,results=['error','accepted']),
        dict(id='valid-move',calls=[move],starts=1,moving=True,results=['accepted']),
        dict(id='valid-legacy-sequence',calls=[call('sequence',dict(steps_json=steps))],starts=1,moving=True,results=['accepted']),
        dict(id='inner-plan-zero',calls=[call('sequence',dict(steps_json=steps.replace('left','left\\u0000extra')))],starts=0,error='Sequence requires'),
        dict(id='literal-escape-not-zero',calls=[call('move',dict(direction=r'left\u0000',duration_ms=880))],starts=0,error='Move requires'),
        dict(id='valid-cancel',profile='corpus_draft7',calls=[read,call('compose',cancel)],starts=0,revision=0,results=['ok','draft_cancelled']),
        dict(id='queued-then-invalid',calls=[dict(move,defer=True),call('water\0extra',dict(duration_ms=1000))],starts=0),
    ]


def check(executable):
    results=[]
    for case in scenarios():
        commands=[dict(command,elapsed_ms=index+1) for index,command in enumerate(case['calls'])]
        wire=firmware_replay(executable,case.get('profile','corpus_idle'),[*commands,dict(inspect_ms=100)])
        replies,final=wire[:-1],wire[-1]
        values=[json.loads(r['result']['content'][0]['text'])['result'] if 'result' in r else 'error' for r in replies]
        passed=final['starts_this_boot']==case['starts']
        if 'moving' in case:passed=passed and bool(final['logical_outputs']['left'] or final['logical_outputs']['right'])==case['moving']
        if 'revision' in case:passed=passed and final['show_draft']['revision']==case['revision']
        if 'error' in case:passed=passed and 'error' in replies[-1] and case['error'] in replies[-1]['error']['message']
        if 'results' in case:passed=passed and values==case['results']
        results.append(dict(id=case['id'],passed=passed,results=values,replies=replies,final=final))
    return dict(scope='Raw test transport with actual MCP dispatcher/callbacks, simulated input/time; no network/model/board IO',
                host_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),scenarios=len(results),
                passed=all(row['passed'] for row in results),failed=[r['id'] for r in results if not r['passed']],results=results)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--executable',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();report=check(a.executable)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False))
    raise SystemExit(0 if report['passed'] else 1)
