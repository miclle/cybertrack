import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('capture_lingxi', ROOT/'scripts/capture_lingxi.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CaptureTests(unittest.TestCase):
    def test_actual_stt_events_reach_closed_host_in_received_order(self):
        class Socket:
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
            send=AsyncMock()
            recv=AsyncMock(side_effect=[json.dumps(message) for message in [
                dict(type='hello',session_id='fixture'),
                dict(type='mcp',payload=dict(id=1,method='tools/list',params={})),
                dict(type='stt',text='喷水'),dict(type='stt',text=''),dict(type='stt',text='喷水'),
                dict(type='mcp',payload=dict(id=2,method='tools/call',params=dict(name='self.tank.water',arguments=dict(duration_ms=1000)))),
                dict(type='tts',state='stop')]])
        histories=[]
        wire=dict(result=dict(content=[dict(type='text',text='{"result":"accepted"}')],isError=False))
        def replay(binary,profile,calls,**kwargs):
            histories.append((copy.deepcopy(calls),kwargs))
            return [wire,dict(starts_this_boot=1)]
        case=dict(id='V001',text='喷水',context='空闲',fixture_version='firmware_host',
                  host_binary=Path('unused'),initial_profile='corpus_idle',host_stt_events=True,opus_frames=[])
        client=SimpleNamespace(connect=lambda *args,**kwargs:Socket())
        with patch.dict(sys.modules,{'websockets.asyncio.client':client}),patch.object(module,'firmware_replay',side_effect=replay):
            row=asyncio.run(module.capture_case(dict(token='test',device_id='test',client_id='test'),
                [dict(name='self.tank.water'),*[dict(name='self.tank.t'+str(i)) for i in range(11)]],case))
        self.assertTrue(row['completed'])
        self.assertEqual(row['host_input_mode'],'platform_stt_events')
        self.assertEqual([event.get('input_text') for event in row['host_calls'][:-1]],['喷水','','喷水'])
        self.assertEqual(row['host_calls'][-1]['name'],'self.tank.water')
        self.assertTrue(all(kwargs==dict(await_stt=True) for _,kwargs in histories))
        self.assertEqual(histories[0][0],row['host_calls'])

    def test_schema_pagination_is_complete_and_bounded(self):
        tools=[dict(name='self.tank.tool'+str(i),description='中文'*1200) for i in range(12)]
        seen=[];cursor=''
        while True:
            page=module.tools_page(tools,cursor)
            seen.extend(page['tools'])
            self.assertLess(len(json.dumps(page,ensure_ascii=False,separators=(',',':')).encode()),8000)
            cursor=page.get('nextCursor')
            if not cursor:break
        self.assertEqual(seen,tools)
        with self.assertRaises(ValueError):module.tools_page([dict(name='self.tank.big',description='x'*9000)])

    def test_timed_status_rejects_writes_before_running_host(self):
        with patch.object(module.subprocess,'check_output') as run_host:
            for name,args in [('self.tank.stop',{}),('self.tank.get_status',{'extra':True})]:
                with self.assertRaises(ValueError):
                    module.timed_status('forward70',1200,name,args)
            run_host.assert_not_called()

    def test_stop_clears_active_motion_without_another_start(self):
        status = module.fixture('向前行走，当前速度70%')
        stopped = module.simulated_reply(status,'self.tank.stop',{})
        self.assertEqual(status['move_remaining_ms'],4000)
        self.assertEqual(stopped['move_remaining_ms'],0)
        self.assertEqual(stopped['move_speed_percent'],0)
        self.assertEqual(stopped['move_direction'],'none')
        self.assertEqual(stopped['move_source'],'none')
        self.assertEqual(stopped['starts_this_boot'],status['starts_this_boot'])
        self.assertEqual(stopped['recent_command']['operation'],'stop')

    def test_fixture_draft_preserves_non_target_and_source(self):
        corpus=json.loads((ROOT/'docs/validation/compose-cases.json').read_text())
        status=module.fixture(corpus['cases'][1]['context']);before=copy.deepcopy(status)
        step=copy.deepcopy(status['show_draft']['steps'][1]);step['bubbles_ms']=2000
        reply=module.simulated_reply(status,'self.tank.compose',dict(edit='replace_step',revision=7,step=2,steps_json=json.dumps([step])))
        self.assertEqual(status,before)
        self.assertEqual(reply['show_draft']['steps'][0],status['show_draft']['steps'][0])
        self.assertEqual(reply['show_draft']['steps'][1]['bubbles_ms'],2000)
        self.assertEqual(reply['starts_this_boot'],0)
        self.assertEqual(reply['actuator_backend'],'capture_fixture')

    def test_invalid_draft_preserves_original(self):
        corpus=json.loads((ROOT/'docs/validation/compose-cases.json').read_text())
        status=module.fixture(corpus['cases'][1]['context']);before=copy.deepcopy(status)
        valid=status['show_draft']['steps'][1]
        for changes in ({'water_ms':1000},{'ignition_ms':1000},{'bubbles_ms':30001},
                        {'bubbles_ms':True},{'direction':'left'},{'speed_percent':59}):
            bad={**valid,**changes}
            reply=module.simulated_reply(status,'self.tank.compose',dict(edit='replace_step',revision=7,step=1,steps_json=json.dumps([bad])))
            self.assertEqual(reply['result'],'invalid_plan')
            self.assertEqual(reply['show_draft'],before['show_draft'])
            self.assertEqual(status,before)
        for value in ([],{},[valid,valid],None):
            reply=module.simulated_reply(status,'self.tank.compose',dict(edit='replace_step',revision=7,step=1,steps_json=json.dumps(value)))
            self.assertEqual(reply['result'],'invalid_plan')

    def test_runner_strips_oracles_and_refuses_overwrite(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as tmp:
                base=Path(tmp)
                for name,value in [('connection',{}),('tools',{'tools':[{'name':f'self.tank.t{i}'} for i in range(12)]}),
                                   ('corpus',{'cases':[{'id':'V001','text':'查询','context':'空闲','fixture_version':'DO NOT SEND','expected_calls':['DO NOT SEND'],'response_expectation':'DO NOT SEND'},
                                                       {'id':'D001','text':'查询','context':'合成故障','fixture_status':{'fault':'driver_error'},'expected_calls':['DO NOT SEND']}]})]:
                    (base/name).write_text(json.dumps(value));(base/name).chmod(0o600)
                (base/'role').write_text('fixture')
                args=SimpleNamespace(**{k:base/k for k in ['connection','tools','corpus','role','output']},ids=None,model='fixture',timeout=1)
                mock=AsyncMock(return_value={'id':'V001','calls':[],'completion':'tts_stop','completed':True})
                with patch.object(module,'capture_case',mock):await module.run(args)
                self.assertEqual(set(mock.call_args_list[0].args[2]),{'id','text','context','fixture_version'})
                self.assertEqual(set(mock.call_args_list[1].args[2]),{'id','text','context','fixture_status','fixture_version'})
                self.assertEqual(mock.call_args_list[0].args[2]['fixture_version'],'ct45')
                self.assertEqual(mock.call_args_list[1].args[2]['fixture_status'],{'fault':'driver_error'})
                with self.assertRaises(ValueError):await module.run(args)
        asyncio.run(exercise())
