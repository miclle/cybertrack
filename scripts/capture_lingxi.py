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
import subprocess
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
        status.update(state='ACTIVE',starts_this_boot=1,move_direction='forward',move_speed_percent=70,move_remaining_ms=4000,move_source='voice')
        status['logical_outputs'].update(left=70,right=70)
    if 'revision=7' in context:
        steps=json.loads(re.search(r'steps=(\[.*\])；',context).group(1))
        status['show_draft']=dict(active=True,revision=7,steps=steps,expires_in_ms=300000)
    return status


def valid_draft_steps(steps):
    """Mirror the ct45 draft subset, not its timing/ownership execution logic."""
    required={'direction','move_ms','water_ms','bubbles_ms','ignition_ms'}
    if not isinstance(steps,list) or not 1<=len(steps)<=16:return False
    for step in steps:
        if not isinstance(step,dict) or not required<=step.keys() or step.keys()-required-{'speed_percent'}:return False
        values=[step[k] for k in ('move_ms','water_ms','bubbles_ms','ignition_ms')]
        speed=step.get('speed_percent',100)
        if any(type(v) is not int or v<0 for v in values) or type(speed) is not int or not 60<=speed<=100:return False
        move,water,bubbles,ignition=values
        if water or ignition or not (move or bubbles) or move>2147483647 or bubbles>30000:return False
        if step['direction'] not in (('forward','backward','left','right') if move else ('none',)):return False
    return True


def simulated_reply(status, name, args):
    """Only in-memory fixtures. No callback or device address can be supplied."""
    name=name.replace('self_tank_','self.tank.',1)
    if name=='self.tank.get_status':
        return copy.deepcopy(status)
    result=copy.deepcopy(status)
    result['operation']=name.removeprefix('self.tank.')
    if name=='self.tank.stop':
        result.update(result='ok',fault='stopped',state='STOPPED')
        result.update(move_direction='none',move_speed_percent=0,drive_hold_id=0,water_hold_id=0,
                      bubbles_hold_id=0,frenzy_remaining_ms=0,sequence_active=False)
        if status['sequence_active']:result['sequence_result']='cancelled'
        for channel in ('move','water','bubbles','ignition'):
            result[channel+'_remaining_ms']=0
            result[channel+'_source']='none'
        result['recent_command']=dict(valid=True,operation='stop',result='ok',source='voice',age_ms=0)
        result['logical_outputs']=dict(left=0,right=0,water=False,bubbles=False,ignition=False)
        result['show_draft']=dict(active=False,revision=0,steps=[],expires_in_ms=0)
    elif name=='self.tank.compose':
        draft=status['show_draft'];edit=args.get('edit');rev=args.get('revision')
        if rev!=draft['revision']:result['result']='draft_changed'
        elif edit=='cancel':
            result['result']='draft_cancelled';result['show_draft']=dict(active=False,revision=0,steps=[],expires_in_ms=0)
        else:
            steps=copy.deepcopy(draft['steps']);index=args.get('step',0)-1
            if edit in ('replace','replace_step'):
                try:incoming=json.loads(args['steps_json'])
                except (ValueError,TypeError):incoming=None
                if not valid_draft_steps(incoming) or (edit=='replace_step' and len(incoming)!=1):
                    result['result']='invalid_plan';return result
            if edit=='replace':steps=incoming
            elif edit=='replace_step' and 0<=index<len(steps):steps[index]=incoming[0]
            elif edit=='remove_step' and 0<=index<len(steps):steps.pop(index)
            else:raise ValueError('unsupported fixture edit')
            if not valid_draft_steps(steps):result['result']='invalid_plan';return result
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


def timed_status(profile, elapsed_ms, name, args):
    """A frozen host image can evaluate a pure status read at any sampled offset."""
    if name.replace('self_tank_','self.tank.',1) != 'self.tank.get_status' or args != {}:
        raise ValueError('timed status evaluation accepts read-only queries')
    if profile not in ('forward70','short_forward70','idle') or not 0 <= elapsed_ms <= 300000:
        raise ValueError('invalid timed status input')
    call = dict(name='self.tank.get_status', arguments={}, elapsed_ms=elapsed_ms)
    output = subprocess.check_output([str(ROOT/'build/audio-host/receipt_replay'),profile],
                                     input=json.dumps([call]),text=True,timeout=10)
    receipt = json.loads(output.splitlines()[0])
    # All board identifiers in this binary are fixed stubs.
    receipt.update(actuator_backend='host_stub',source='host_firmware_replay')
    return receipt


def host_reply(executable, profile, history, name, args, elapsed_ms):
    """Re-run this conversation's valid RPC prefix from the same initial firmware state."""
    tool = name.replace('self_tank_', 'self.tank.', 1)
    allowed = ('get_status', 'stop', 'compose') if profile == 'two_step_web_draft' else ('get_status', 'set_speed')
    if tool.removeprefix('self.tank.') not in allowed:
        raise ValueError('RPC outside host replay')
    call = dict(name=tool, arguments=args, elapsed_ms=elapsed_ms)
    calls = [*history, call]
    process = subprocess.run([str(executable), profile], input=json.dumps(calls),
                             text=True, capture_output=True, timeout=10)
    if process.returncode == 3:
        raise ValueError('invalid host RPC arguments')
    process.check_returncode()
    lines = process.stdout.splitlines()
    if len(lines) != len(calls) + 1:
        raise RuntimeError('incomplete firmware replay')
    receipt = json.loads(lines[-2])  # The last line is a separate inspection read.
    history.append(call)
    return receipt


async def capture_case(connection,tools,case,timeout=45):
    from websockets.asyncio.client import connect
    status=copy.deepcopy(case['fixture_status']) if 'fixture_status' in case else fixture(case['context'])
    version = case.get('fixture_version','ct46' if case.get('ct46') else 'ct45')
    row=dict(id=case['id'],calls=[],replies=[],events=[],completed=False,input_text=case['text'],context=case['context'])
    headers={'Authorization':'Bearer '+connection['token'].removeprefix('Bearer '),
             'Device-Id':connection['device_id'],'Client-Id':connection['client_id'],'Protocol-Version':'1'}
    opened = time.monotonic()
    timeline = row['timeline'] = []
    def mark(event, **details):
        timeline.append(dict(ms=round((time.monotonic()-opened)*1000), event=event, **details))
    uplink = case.get('opus_frames')
    input_ms=None
    call_history=[]
    draft_observed_at=None
    session=None;sent=False;deadline=opened+timeout;audio_bytes=0
    async with connect(ENDPOINT,additional_headers=headers,proxy=None,open_timeout=15,max_size=2**20) as ws:
        async def send(message):await ws.send(json.dumps(message,ensure_ascii=False))
        await send(dict(type='hello',version=1,transport='websocket',features={'mcp':True},audio_params=dict(format='opus',sample_rate=16000,channels=1,frame_duration=60)))
        while time.monotonic()<deadline:
            try:raw=await asyncio.wait_for(ws.recv(),min(5,max(.01,deadline-time.monotonic())))
            except asyncio.TimeoutError:continue
            if isinstance(raw,bytes):
                if not audio_bytes:mark('first_audio')
                if case.get('audio_packets'):mark('audio_packet', size=len(raw))
                audio_bytes+=len(raw)
                continue
            msg=json.loads(raw);kind=msg.get('type')
            if kind=='hello':session=msg.get('session_id');row['events'].append('hello')
            elif kind=='mcp':
                payload=msg.get('payload',{});method=payload.get('method');params=payload.get('params') or {}
                row['events'].append(method)
                result=None
                rpc_error=None
                if method=='initialize':result=dict(protocolVersion='2024-11-05',capabilities={'tools':{}},serverInfo=dict(name='CyberTrack capture only',version=version))
                elif method=='tools/list':result=tools_page(tools,params.get('cursor',''))
                elif method=='tools/call':
                    name=params['name'];args=params.get('arguments',{})
                    mark('tool_call', name=name)
                    row['calls'].append(dict(name=name,arguments=args))
                    try:
                        if name.replace('self_tank_','self.tank.',1) not in {t['name'] for t in tools}:raise ValueError('unknown tool')
                        if version in ('draft_host','speed_host'):
                            if input_ms is None:raise ValueError('missing evaluation input')
                            receipt=host_reply(case['host_binary'],case['initial_profile'],call_history,name,args,timeline[-1]['ms']-input_ms)
                        elif version == 'timed_host':
                            if input_ms is None:raise ValueError('missing evaluation input')
                            receipt=timed_status(case['initial_motion'],timeline[-1]['ms']-input_ms,name,args)
                        elif version != 'ct45' and name.endswith('compose') and (
                                draft_observed_at is None or time.monotonic()-draft_observed_at >= 30):
                            receipt={**copy.deepcopy(status),'operation':'show_edit','result':'draft_changed'}
                        else:
                            receipt=simulated_reply(status,name,args)
                        if name.endswith('compose') or name.endswith('stop'):draft_observed_at=None
                        if name.endswith('get_status'):draft_observed_at=time.monotonic()
                        if version == 'ct47' or (version == 'ct46' and name.endswith('get_status')):
                            helper = Path(__file__).resolve().parents[1] / 'build/lingxi-schema-export/status-fixture'
                            output = subprocess.run([str(helper), version], input=json.dumps(receipt),
                                text=True, capture_output=True, check=True).stdout.strip()
                            if version == 'ct47':
                                fields = json.loads(output)
                                receipt['show_draft']['editing_capabilities'] = fields.pop('editing_capabilities')
                                if name.endswith('get_status'): receipt.update(fields)
                            else: receipt['status_facts'] = output
                        if name.endswith('compose') or name.endswith('stop'):status=copy.deepcopy(receipt);status['result']='ok'
                        if 'rpc_error' in receipt:
                            rpc_error=dict(message=receipt['rpc_error'])
                            row.setdefault('rpc_errors',[]).append(dict(name=name, **rpc_error))
                        else:
                            row.setdefault('simulated_receipts',[]).append(receipt)
                            result={'content':[{'type':'text','text':json.dumps(receipt,ensure_ascii=False)}],'isError':False}
                    except (ValueError,KeyError,TypeError,IndexError):result={'content':[{'type':'text','text':'capture fixture rejected invalid arguments'}],'isError':True}
                if rpc_error is not None:
                    await send(dict(type='mcp',payload=dict(jsonrpc='2.0',id=payload['id'],error=rpc_error)))
                elif result is not None:
                    await send(dict(type='mcp',payload=dict(jsonrpc='2.0',id=payload['id'],result=result)))
                if method=='tools/call':
                    mark('tool_reply_sent', name=name, is_error=rpc_error is not None or result['isError'])
                if method=='tools/list' and not result.get('nextCursor') and not sent:
                    # Context is visibly separate from the user's phrase; the
                    # runner never reads expected_calls or response_expectation.
                    mark('input_sent');input_ms=timeline[-1]['ms']
                    if uplink is not None:
                        await send(dict(session_id=session,type='listen',state='start',mode='manual'))
                        for frame in uplink:
                            await ws.send(frame)
                            await asyncio.sleep(.060)
                        await send(dict(session_id=session,type='listen',state='stop'))
                        mark('uplink_end')
                    else:
                        text=case['text'] if case.get('raw_text') else '本轮为无执行器的文本评测，以下仅是模拟前置状态，不是动作指令：'+case['context']+'。请只处理这条用户原话：'+case['text']
                        await send(dict(session_id=session,type='listen',state='detect',text=text))
                    sent=True;row['events'].append('test_input_sent')
            elif kind=='tts':
                state=msg.get('state')
                if state in ('start','sentence_start','stop'):
                    mark('tts_'+state, reply_index=len(row['replies']))
                if msg.get('state')=='sentence_start':row['replies'].append(msg.get('text',''))
                if msg.get('state')=='stop' and sent:
                    row['completed']=msg.get('is_aborted') is not True
                    if not row['completed']:row['completion']='tts_aborted'
                    break
            elif kind=='stt':
                row['echoed_text']=msg.get('text','');mark('stt', text=row['echoed_text'])
            elif kind in ('error','goodbye'):row['events'].append(kind);break
    row['received_audio_bytes_discarded']=audio_bytes
    row.setdefault('completion','tts_stop' if row['completed'] else 'incomplete_or_timeout')
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
    fields=('id','text','context','fixture_status')
    timed=getattr(args,'timed_host',False)
    if timed:
        if not args.raw_text or any(c.get('initial_motion') not in ('forward70','short_forward70','idle') for c in cases):
            raise ValueError('timed host requires raw input and a known motion profile')
        fields=('id','text','context','initial_motion')
    cases=[{k:c[k] for k in fields if k in c} for c in cases]
    if getattr(args, 'raw_text', False):
        for case in cases: case['raw_text']=True
    version = 'timed_host' if timed else 'ct47' if getattr(args,'ct47',False) else 'ct46' if getattr(args,'ct46',False) else 'ct45'
    draft_host=getattr(args,'draft_host',None)
    speed_host=getattr(args,'speed_host',None)
    if speed_host and not getattr(args,'synthetic_speech',False):
        raise ValueError('speed host requires synthetic speech')
    if draft_host or speed_host:
        version='draft_host' if draft_host else 'speed_host'
        binary=draft_host or ROOT/'build/audio-host/receipt_replay'
        for case in cases:
            case.update(host_binary=binary.resolve(), initial_profile='two_step_web_draft' if draft_host else speed_host)
    for case in cases:
        case['fixture_version']=version
        if getattr(args,'audio_packets',False): case['audio_packets']=True
    trace=dict(fixture_version=version,kind='captured_tool_calls',run_id=str(uuid.uuid4()),date=datetime.datetime.now(datetime.timezone.utc).isoformat(),model=args.model,
               model_source='visible platform configuration; no model identity in WSS response',role_sha256=hashlib.sha256(args.role.read_bytes()).hexdigest(),
               transport=ENDPOINT,tool_schema_sha256=hashlib.sha256(args.tools.read_bytes()).hexdigest(),corpus_sha256=hashlib.sha256(args.corpus.read_bytes()).hexdigest(),
               input_mode='raw_text_diagnostic' if getattr(args,'raw_text',False) else 'context_prefixed',
               capture_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               scope='Real platform calls; synthetic receipt/context fixtures; zero device forwarding; text not microphone ASR',results=[])
    synthetic = getattr(args, 'synthetic_speech', False)
    if synthetic:
        if timed or draft_host:
            raise ValueError('synthetic speech currently uses static isolated receipts')
        import synthetic_speech
        trace['input_mode'] = 'synthetic_opus'
        trace['synthesis_source_sha256'] = hashlib.sha256(Path(synthetic_speech.__file__).read_bytes()).hexdigest()
        trace['scope'] = 'Synthesized speech over real platform ASR; isolated fixture receipts; no microphone, speaker or device IO'
    if timed or draft_host or speed_host:
        binary=draft_host or ROOT/'build/audio-host/receipt_replay'
        trace['host_replay_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest()
    if getattr(args,'audio_packets',False):trace['audio_packet_sizes_recorded']=True
    if draft_host or speed_host:
        trace['initial_profile']='two_step_web_draft' if draft_host else speed_host
    if speed_host:
        trace['scope']='Synthesized speech over platform ASR; timed firmware host receipts; zero device IO'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for case in cases:
        if synthetic:
            case['opus_frames'], metadata = synthetic_speech.synthesize(case['text'])
        row=await capture_case(connection,tools,case,args.timeout)
        if synthetic:
            row['uplink'] = metadata
        trace['results'].append(row);args.output.write_text(json.dumps(trace,ensure_ascii=False,indent=2)+'\n')
        print(case['id'],row['completion'],','.join(c['name'] for c in row['calls']) or '(no tools)',flush=True)
        if not row['completed']:raise RuntimeError('incomplete case; capture retained, not counted as a successful no-call result')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('connection','tools','corpus','role','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--model',required=True);p.add_argument('--ids');p.add_argument('--timeout',type=float,default=45)
    p.add_argument('--audio-packets',action='store_true',help='Record arrival and size of every remote audio packet; discard its content')
    inputs=p.add_mutually_exclusive_group()
    inputs.add_argument('--synthetic-speech',action='store_true',help='Send synthesized Mandarin as Opus frames, without input text or a microphone')
    inputs.add_argument('--raw-text',action='store_true',help='Diagnostic only: omit the context prefix; not equivalent to the fixed contextual suite')
    versions=p.add_mutually_exclusive_group()
    versions.add_argument('--speed-host',choices=('idle','thirty_second_forward70','voice_offline','wifi_offline'),help='Use timed firmware speed/status receipts for a synthetic utterance')
    versions.add_argument('--draft-host',type=Path,metavar='REPLAY',help='Use host firmware with a two-step web draft at revision 7')
    versions.add_argument('--timed-host',action='store_true',help='Use read-only host firmware receipts at observed RPC offsets')
    versions.add_argument('--ct47', action='store_true', help='Include draft capabilities and fault recovery in candidate receipts')
    versions.add_argument('--ct46', action='store_true', help='Use candidate status facts compiled from status_facts.h')
    args=p.parse_args()
    try:asyncio.run(run(args))
    except Exception as error:
        # Connection errors can contain headers or tokens. Keep values private.
        raise SystemExit('Capture stopped: '+type(error).__name__+'; inspect local evidence, no device requests were forwarded') from None
