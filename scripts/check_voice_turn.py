#!/usr/bin/env python3
"""Exercise input generations through the actual MCP host; never a model or board."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from capture_lingxi import firmware_replay

ROOT = Path(__file__).resolve().parents[1]


def check(executable):
    def call(name, args, ms=0, rpc=1, **extra):
        return dict(name='self.tank.'+name, arguments=args, elapsed_ms=ms, rpc_id=rpc, **extra)

    def result(wire):
        return json.loads(wire['result']['content'][0]['text'])

    invalid = call('bubbles', {'duration_ms':60000})
    move = dict(direction='forward',duration_ms=1000)
    rows = firmware_replay(executable, 'corpus_idle', [
        invalid, call('get_status',{},10,2), dict(input_text='  \t',elapsed_ms=15),
        call('move',move,20,3), call('stop',{},30,4), call('water',{'duration_ms':1000},300,5),
        dict(input_text='喷水',elapsed_ms=500), call('water',{'duration_ms':1000},500,6), dict(inspect_ms=600)])
    assert 'error' in rows[0] and result(rows[1])['result']=='ok'
    assert 'voice_input_failed' in rows[2]['error']['message']
    assert result(rows[3])['result']=='ok' and 'error' in rows[4]
    assert result(rows[5])['result']=='accepted' and rows[-1]['starts_this_boot']==1
    assert rows[-1]['water_remaining_ms']==900

    rows = firmware_replay(executable,'corpus_idle',[
        call('move',move,defer=True), call('bubbles',{'duration_ms':60000},1,2),
        dict(flush=True,elapsed_ms=2)])
    assert len(rows)==3 and all('error' in wire or result(wire)['result']!='accepted' for wire in rows[:-1])
    assert rows[-1]['starts_this_boot']==0

    rows = firmware_replay(executable,'corpus_idle',[
        call('compose',dict(edit='cancel',revision=0,step=0,steps_json=''),defer=True),
        dict(input_text='吹泡泡',elapsed_ms=10),call('bubbles',{'duration_ms':1000},20,2),
        dict(flush=True,elapsed_ms=30),call('water',{'duration_ms':1000},40,3)])
    assert result(rows[0])['result']=='accepted' and result(rows[1])['result']=='voice_input_changed'
    assert result(rows[2])['result']=='accepted' and rows[-1]['starts_this_boot']==2
    assert rows[-1]['logical_outputs']['water'] and rows[-1]['logical_outputs']['bubbles']

    edit=dict(edit='replace_step',revision=7,step=2,steps_json='[{"direction":"none","move_ms":0,"water_ms":0,"bubbles_ms":2000,"ignition_ms":0}]')
    rows=firmware_replay(executable,'corpus_draft7',[
        call('get_status',{},defer=True),dict(input_text='修改第二步',elapsed_ms=10),
        dict(flush=True,elapsed_ms=20),call('compose',edit,30,2)])
    assert result(rows[0])['result']=='voice_input_changed' and result(rows[1])['result']=='draft_changed'
    assert rows[-1]['show_draft']['revision']==7 and rows[-1]['starts_this_boot']==0

    rows=firmware_replay(executable,'corpus_idle',[
        call('move',move,defer=True),dict(input_text='新的指令',elapsed_ms=10),
        dict(flush=True,elapsed_ms=20),call('move',move,30,1),
        dict(input_text='前进',elapsed_ms=40),call('move',move,40,3)])
    assert result(rows[0])['result']=='voice_input_changed' and 'error' in rows[1]
    assert result(rows[2])['result']=='accepted' and rows[-1]['starts_this_boot']==1

    rows=firmware_replay(executable,'corpus_idle',[
        call('water',{'duration_ms':1000}),call('get_status',{},1,2),call('stop',{},2,3),
        dict(input_text=' \t',elapsed_ms=3),call('water',{'duration_ms':1000},4,4),
        dict(input_text='喷水',elapsed_ms=5),call('water',{'duration_ms':1000},5,5)],await_stt=True)
    assert 'voice_input_changed' in rows[0]['error']['message']
    assert result(rows[1])['result']=='ok' and result(rows[2])['result']=='ok'
    assert 'error' in rows[3] and result(rows[4])['result']=='accepted'
    assert rows[-1]['starts_this_boot']==1

    rows=firmware_replay(executable,'corpus_forward70',[
        invalid,call('stop',{},10,2),dict(inspect_ms=60000)])
    assert result(rows[1])['result']=='ok' and not any(rows[-1]['logical_outputs'].values())
    assert rows[-1]['starts_this_boot']==1

    rows=firmware_replay(executable,'corpus_idle',[
        dict(voice_online=False,elapsed_ms=0),dict(voice_online=True,elapsed_ms=1),
        call('water',{'duration_ms':1000},2),dict(input_text='喷水',elapsed_ms=3),
        call('water',{'duration_ms':1000},3,2)])
    assert 'error' in rows[0] and result(rows[1])['result']=='accepted'

    rows=firmware_replay(executable,'corpus_idle',[
        call('water',{'duration_ms':1000,'_ct_turn':123}),call('water',{'duration_ms':1000},1,2),
        dict(input_text='喷水',elapsed_ms=2),call('water',{'duration_ms':1000},2,3)])
    assert 'error' in rows[0] and 'voice_input_failed' in rows[1]['error']['message']
    assert result(rows[2])['result']=='accepted' and rows[-1]['starts_this_boot']==1

    raw=(ROOT/'docs/validation/evidence/model-doubao/full-compose.json.gz').read_bytes()
    trace=json.loads(gzip.decompress(raw)); replayed=[]
    for row in trace['results']:
        if row['id'] not in ('C002','C004','C005','C007'):continue
        rows=firmware_replay(executable,row['initial_profile'],[*row['host_calls'],dict(inspect_ms=row['host_inspect_ms'])])
        assert rows[-1]['starts_this_boot']==0 and rows[-1]['show_draft']['revision']==7
        assert not any(rows[-1]['logical_outputs'].values())
        replayed.append(dict(id=row['id'],results=[wire.get('error',{}).get('message') if 'error' in wire else result(wire)['result'] for wire in rows[:-1]],final_revision=7,starts=0))
    assert len(replayed)==4
    return dict(scope='Offline protocol and archived request replay only; input/timing and deferred scheduling simulated; no new model run or board IO',
                synthetic_scenarios=9,await_stt_mode_checked=True,invalid_then_retry_blocked=True,stops_available=True,new_input_recovers=True,
                caller_cannot_set_input_token=True,
                stale_callbacks_and_reads_isolated=True,rpc_replay_preserved=True,reconnect_requires_input=True,
                source_capture_gzip_sha256=hashlib.sha256(raw).hexdigest(),archived_cases=replayed)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable',type=Path,required=True)
    print(json.dumps(check(parser.parse_args().executable),ensure_ascii=False,indent=2))
