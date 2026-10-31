#!/usr/bin/env python3
"""Capture real Lingxi calls against simulated receipts, without any device transport.

Requires websockets==15.0.1. Connection secrets stay in an ignored, mode-0600
file. The only network destination is the official Lingxi WSS endpoint.
"""
import argparse
import asyncio
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

ENDPOINT = 'wss://xrobo-io.qiniuapi.com/v1/ws/'
ROOT = Path(__file__).resolve().parents[1]


def fixture(context):
    """Provide declared test preconditions, never expected calls or answers."""
    status = dict(result='ok', fault='none', state='STOPPED', boot_held=False,
                  logical_outputs=dict(left=0,right=0,water=False,bubbles=False,ignition=False),
                  starts_this_boot=0, physical_feedback=False, actuator_backend='capture_fixture',
                  sequence_active=False, sequence_result='idle', frenzy_remaining_ms=0,
                  show_draft=dict(active=False,revision=0,steps=[],expires_in_ms=0),
                  distance=dict(valid=True,error='none',distance_mm=600,age_ms=0),
                  proximity=dict(auto_avoidance_enabled=False,forward_blocked=False),
                  recent_command=dict(valid=False,age_ms=None),
                  move_direction='none',move_speed_percent=0,web_speed_percent=100,
                  drive_hold_id=0,water_hold_id=0,bubbles_hold_id=0)
    for channel in ('move','water','bubbles','ignition'):
        status[channel+'_remaining_ms']=0
        status[channel+'_cooldown_ms']=0
        status[channel+'_source']='none'
    if '当前速度70%' in context:
        status.update(state='ACTIVE',move_direction='forward',move_speed_percent=70,move_remaining_ms=4000,move_source='voice')
        status['logical_outputs'].update(left=70,right=70)
    if 'revision=7' in context:
        steps=json.loads(re.search(r'steps=(\[.*\])；',context).group(1))
        status['show_draft']=dict(active=True,revision=7,steps=steps,expires_in_ms=300000)
    return status


def simulated_reply(status, name, args):
    """Only in-memory fixtures. No callback or device address can be supplied."""
    name=name.replace('self_tank_','self.tank.',1)
    if name=='self.tank.get_status':
        return copy.deepcopy(status)
    result=copy.deepcopy(status)
    result['operation']=name.removeprefix('self.tank.')
    if name=='self.tank.stop':
        result.update(result='ok',fault='stopped',state='STOPPED')
        result['logical_outputs']=dict(left=0,right=0,water=False,bubbles=False,ignition=False)
        result['show_draft']=dict(active=False,revision=0,steps=[],expires_in_ms=0)
    elif name=='self.tank.compose':
        draft=status['show_draft'];edit=args.get('edit');rev=args.get('revision')
        if rev!=draft['revision']:result['result']='draft_changed'
        elif edit=='cancel':
            result['result']='draft_cancelled';result['show_draft']=dict(active=False,revision=0,steps=[],expires_in_ms=0)
        else:
            steps=copy.deepcopy(draft['steps']);index=args.get('step',0)-1
            if edit=='replace':steps=json.loads(args['steps_json'])
            elif edit=='replace_step' and 0<=index<len(steps):steps[index]=json.loads(args['steps_json'])[0]
            elif edit=='remove_step' and 0<=index<len(steps):steps.pop(index)
            else:raise ValueError('unsupported fixture edit')
            result['result']='draft_saved';result['show_draft']=dict(active=True,revision=rev+1,steps=steps,expires_in_ms=300000)
    else:
        # This is a simulated acceptance used to observe the model's subsequent
        # response, never evidence that firmware accepted or executed a request.
        result['result']='accepted'
        if 'duration_ms' in args:result['last_duration_ms']=args['duration_ms']
        if name=='self.tank.frenzy':result['frenzy_last_duration_ms']=args.get('duration_ms')
    return result


def tools_page(tools, cursor=''):
    start=0 if not cursor else next(i for i,t in enumerate(tools) if t['name']==cursor)
    page=[];size=len('{"tools":[')
    for tool in tools[start:]:
        length=len((json.dumps(tool,ensure_ascii=False,separators=(',',':'))+',').encode())
        if size+length+30>8000:
            if not page:raise ValueError('tool exceeds firmware page limit')
            return dict(tools=page,nextCursor=tool['name'])
        page.append(tool);size+=length
    return dict(tools=page)


async def capture_case(connection,tools,case,timeout=45):
    from websockets.asyncio.client import connect
    status=fixture(case['context'])
    row=dict(id=case['id'],calls=[],replies=[],events=[],completed=False,input_text=case['text'],context=case['context'])
    headers={'Authorization':'Bearer '+connection['token'].removeprefix('Bearer '),
             'Device-Id':connection['device_id'],'Client-Id':connection['client_id'],'Protocol-Version':'1'}
    session=None;sent=False;deadline=time.monotonic()+timeout;audio_bytes=0
    async with connect(ENDPOINT,additional_headers=headers,proxy=None,open_timeout=15,max_size=2**20) as ws:
        async def send(message):await ws.send(json.dumps(message,ensure_ascii=False))
        await send(dict(type='hello',version=1,transport='websocket',features={'mcp':True},audio_params=dict(format='opus',sample_rate=16000,channels=1,frame_duration=60)))
        while time.monotonic()<deadline:
            try:raw=await asyncio.wait_for(ws.recv(),min(5,max(.01,deadline-time.monotonic())))
            except asyncio.TimeoutError:continue
            if isinstance(raw,bytes):audio_bytes+=len(raw);continue
            msg=json.loads(raw);kind=msg.get('type')
            if kind=='hello':session=msg.get('session_id');row['events'].append('hello')
            elif kind=='mcp':
                payload=msg.get('payload',{});method=payload.get('method');params=payload.get('params') or {}
                row['events'].append(method)
                result=None
                if method=='initialize':result=dict(protocolVersion='2024-11-05',capabilities={'tools':{}},serverInfo=dict(name='CyberTrack capture only',version='ct45'))
                elif method=='tools/list':result=tools_page(tools,params.get('cursor',''))
                elif method=='tools/call':
                    name=params['name'];args=params.get('arguments',{})
                    row['calls'].append(dict(name=name,arguments=args))
                    try:
                        if name.replace('self_tank_','self.tank.',1) not in {t['name'] for t in tools}:raise ValueError('unknown tool')
                        receipt=simulated_reply(status,name,args)
                        if name.endswith('compose') or name.endswith('stop'):status=copy.deepcopy(receipt);status['result']='ok'
                        row.setdefault('simulated_receipts',[]).append(receipt)
                        result={'content':[{'type':'text','text':json.dumps(receipt,ensure_ascii=False)}],'isError':False}
                    except (ValueError,KeyError,TypeError,IndexError):result={'content':[{'type':'text','text':'capture fixture rejected invalid arguments'}],'isError':True}
                if result is not None:
                    await send(dict(type='mcp',payload=dict(jsonrpc='2.0',id=payload['id'],result=result)))
                if method=='tools/list' and not result.get('nextCursor') and not sent:
                    # Context is visibly separate from the user's phrase; the
                    # runner never reads expected_calls or response_expectation.
                    text='本轮为无执行器的文本评测，以下仅是模拟前置状态，不是动作指令：'+case['context']+'。请只处理这条用户原话：'+case['text']
                    await send(dict(session_id=session,type='listen',state='detect',text=text))
                    sent=True;row['events'].append('test_input_sent')
            elif kind=='tts':
                if msg.get('state')=='sentence_start':row['replies'].append(msg.get('text',''))
                if msg.get('state')=='stop' and sent:
                    row['completed']=True;break
            elif kind=='stt':row['echoed_text']=msg.get('text','')
            elif kind in ('error','goodbye'):row['events'].append(kind);break
    row['received_audio_bytes_discarded']=audio_bytes
    row['completion']='tts_stop' if row['completed'] else 'incomplete_or_timeout'
    return row


async def run(args):
    os.umask(0o077)
    if args.connection.stat().st_mode&0o077:raise ValueError('connection file must be private (0600)')
    if args.output.exists():raise ValueError('refusing to overwrite an existing capture')
    connection=json.loads(args.connection.read_text())
    tools=json.loads(args.tools.read_text())['tools']
    if len(tools)!=12 or any(not t['name'].startswith('self.tank.') for t in tools):raise ValueError('expected 12 robot-only schemas')
    cases=json.loads(args.corpus.read_text())['cases']
    if args.ids:
        requested=set(args.ids.split(','));cases=[c for c in cases if c['id'] in requested]
        if {c['id'] for c in cases}!=requested:raise ValueError('unknown case id')
    # Deliberately discard all oracle fields before entering the capture loop.
    cases=[{k:c[k] for k in ('id','text','context')} for c in cases]
    trace=dict(kind='captured_tool_calls',run_id=str(uuid.uuid4()),date=datetime.datetime.now(datetime.timezone.utc).isoformat(),model=args.model,
               model_source='visible platform configuration; no model identity in WSS response',role_sha256=hashlib.sha256(args.role.read_bytes()).hexdigest(),
               transport=ENDPOINT,tool_schema_sha256=hashlib.sha256(args.tools.read_bytes()).hexdigest(),corpus_sha256=hashlib.sha256(args.corpus.read_bytes()).hexdigest(),
               scope='Real platform calls; synthetic receipt/context fixtures; zero device forwarding; text not microphone ASR',results=[])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for case in cases:
        row=await capture_case(connection,tools,case,args.timeout)
        trace['results'].append(row);args.output.write_text(json.dumps(trace,ensure_ascii=False,indent=2)+'\n')
        print(case['id'],row['completion'],','.join(c['name'] for c in row['calls']) or '(no tools)',flush=True)
        if not row['completed']:raise RuntimeError('incomplete case; capture retained, not counted as a successful no-call result')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('connection','tools','corpus','role','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--model',required=True);p.add_argument('--ids');p.add_argument('--timeout',type=float,default=45)
    args=p.parse_args()
    try:asyncio.run(run(args))
    except Exception as error:
        # Connection errors can contain headers or tokens. Keep values private.
        raise SystemExit('Capture stopped: '+type(error).__name__+'; inspect local evidence, no device requests were forwarded') from None
