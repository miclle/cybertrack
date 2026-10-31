#!/usr/bin/env python3
"""Replay relative draft requests with simulated STT through actual MCP code."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from capture_lingxi import firmware_replay

ROOT=Path(__file__).resolve().parents[1]


def check(executable):
    def call(name,args=None,ms=10,rpc=1,**extra):
        return dict(name='self.tank.'+name,arguments=args or {},elapsed_ms=ms,rpc_id=rpc,**extra)

    def receipt(wire):
        if 'error' in wire:return dict(result='rpc_error',message=wire['error']['message'])
        return json.loads(wire['result']['content'][0]['text'])

    def text(value,ms=0):return dict(input_text=value,elapsed_ms=ms)
    def edit(ms=500):
        return dict(edit='replace_step',revision=7,step=2,steps_json=json.dumps([
            dict(direction='none',move_ms=0,water_ms=0,bubbles_ms=ms,ignition_ms=0)]))

    results=[]
    def run(name,commands,verify,profile='corpus_draft7'):
        wires=firmware_replay(executable,profile,commands,await_stt=True)
        replies=[receipt(w) for w in wires[:-1]]
        results.append(dict(name=name,passed=bool(verify(replies,wires[-1])),profile=profile,commands=commands,
                            receipts=replies,final_state=wires[-1]))

    unchanged=lambda s:s['show_draft']['revision']==7 and s['show_draft']['steps'][1]['bubbles_ms']==1000 and s['starts_this_boot']==0
    for phrase in ['第二步短一点','把结尾的泡泡改短','第一步稍长一些']:
        run(phrase,[text(phrase),call('get_status'),call('compose',edit(),20,2)],
            lambda r,s:len(r)==2 and r[1]['result']=='draft_duration_unspecified'
            and bool(r[1].get('clarification_facts')) and unchanged(s))

    for name,args in [('compose',dict(edit='cancel',revision=7,step=0,steps_json='')),
                      ('move',dict(direction='forward',duration_ms=1000)),
                      ('sequence',dict(steps_json='[{"direction":"left","move_ms":880,"water_ms":0,"bubbles_ms":0,"ignition_ms":0}]'))]:
        run('first_'+name+'_cannot_replace_clarification',[text('第二步短一点'),call(name,args)],
            lambda r,s:r[0]['result']=='draft_duration_unspecified' and unchanged(s))

    run('failure_latch_then_new_quantified_input',[
        text('第二步短一点'),call('get_status'),call('compose',edit(),20,2),
        call('move',dict(direction='forward',duration_ms=1000),30,3),call('get_status',ms=40,rpc=4),
        text('第二步改成两秒',50),call('get_status',ms=60,rpc=5),call('compose',edit(2000),70,6)],
        lambda r,s:r[1]['result']=='draft_duration_unspecified' and r[2]['result']=='rpc_error'
        and 'voice_input_failed' in r[2]['message'] and r[3]['result']==r[4]['result']=='ok'
        and r[5]['result']=='draft_saved' and s['show_draft']['revision']==8
        and s['show_draft']['steps'][0]['move_ms']==880 and s['show_draft']['steps'][1]['bubbles_ms']==2000 and s['starts_this_boot']==0)

    run('new_cancel_input_recovers',[
        text('第二步短一点'),call('compose',edit()),text('取消草稿',20),
        call('get_status',ms=30,rpc=2),call('compose',dict(edit='cancel',revision=7,step=0,steps_json=''),40,3)],
        lambda r,s:r[0]['result']=='draft_duration_unspecified' and r[2]['result']=='draft_cancelled'
        and s['show_draft']['revision']==0 and s['starts_this_boot']==0)

    run('mixed_stop_is_unconditional',[text('第二步短一点，马上停下'),call('stop',defer=True),dict(inspect_ms=60000)],
        lambda r,s:r[0]['result']=='ok' and not any(s['logical_outputs'].values()) and not s['sequence_active'],profile='corpus_sequence')

    direction=dict(edit='replace_step',revision=7,step=2,steps_json='[{"direction":"right","move_ms":880,"water_ms":0,"bubbles_ms":0,"ignition_ms":0}]')
    run('direction_only_replacement_keeps_default',[
        text('第二步改成右转'),call('get_status'),call('compose',direction,20,2)],
        lambda r,s:r[1]['result']=='draft_saved' and s['show_draft']['steps'][1]['direction']=='right'
        and s['show_draft']['steps'][1]['move_ms']==880 and s['starts_this_boot']==0)

    long_step=dict(edit='replace_step',revision=7,step=1,steps_json='[{"direction":"left","move_ms":1814400000,"water_ms":0,"bubbles_ms":0,"ignition_ms":0}]')
    run('quantified_weeks_preserve_protocol_duration',[
        text('第一步改长为三周'),call('get_status'),call('compose',long_step,20,2)],
        lambda r,s:r[1]['result']=='draft_saved' and s['show_draft']['steps'][0]['move_ms']==1814400000
        and s['show_draft']['steps'][1]['bubbles_ms']==1000 and s['starts_this_boot']==0)

    run('old_callback_does_not_poison_new_input',[
        text('第二步改成半秒'),call('get_status'),call('compose',edit(),20,2,defer=True),
        text('第二步短一点',30),dict(flush=True,elapsed_ms=40),call('get_status',ms=50,rpc=3),call('compose',edit(),60,4)],
        lambda r,s:r[1]['result']=='voice_input_changed' and r[2]['result']=='ok'
        and r[3]['result']=='draft_duration_unspecified' and unchanged(s))

    archive=ROOT/'docs/validation/evidence/stop-role-qualifier/baseline-compose.json.gz'
    original=json.loads(gzip.decompress(archive.read_bytes()))
    row=next(row for row in original['results'] if row['id']=='C008')
    run('retained_C008_requests_with_simulated_recognized_text',[
        text(row['input_text']),*row['host_calls'],dict(inspect_ms=row['host_inspect_ms'])],
        lambda r,s:r[1]['result']=='draft_duration_unspecified' and unchanged(s))

    return dict(scope='Actual MCP dispatcher/callbacks with simulated recognized text and clock; historical requests only, not new model or ASR scores',
                host_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                archived_source_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                scenarios=len(results),passed=all(row['passed'] for row in results),
                failed=[row['name'] for row in results if not row['passed']],results=results)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--executable',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();report=check(args.executable)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False))
    raise SystemExit(0 if report['passed'] else 1)
