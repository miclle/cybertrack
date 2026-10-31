import copy
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
try:
    spec=importlib.util.spec_from_file_location('stt_review',ROOT/'scripts/review_stt_host.py')
    review=importlib.util.module_from_spec(spec);spec.loader.exec_module(review)
finally:
    sys.path.pop(0)


class SttReviewTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.binary=Path(self.folder.name)/'host';self.binary.write_bytes(b'pinned host fixture')
        self.wire=dict(result=dict(content=[dict(text='{"result":"accepted"}')]))
        self.final=dict(starts_this_boot=1,logical_outputs=dict(water=True))
        request=dict(name='self.tank.water',arguments=dict(duration_ms=1000))
        row=dict(id='V017',context='设备在线、空闲，四路关闭且不在冷却；网页未占用；距离有效且未锁定',initial_profile='corpus_idle',host_input_mode='platform_stt_events',completed=True,
                 timeline=[dict(event='stt',ms=0,text='not this input'),dict(event='input_sent',ms=0),
                           dict(event='stt',ms=0,text='喷水'),dict(event='tool_call',ms=1,name=request['name'])],
                 calls=[request],host_calls=[dict(input_text='喷水',elapsed_ms=0),dict(**request,rpc_id=3,elapsed_ms=1)],
                 host_inspect_ms=2,host_rpc_replies=[self.wire],host_final_state=self.final)
        self.trace=dict(fixture_version='firmware_host',input_mode='synthetic_opus',host_input_mode='platform_stt_events',
                        host_replay_sha256=hashlib.sha256(self.binary.read_bytes()).hexdigest(),run_id='fixture',results=[row])
        self.replay=patch.object(review,'firmware_replay',return_value=[self.wire,self.final]).start()
        self.addCleanup(patch.stopall)

    def test_boundary_order_and_closed_host_replay(self):
        report=review.review(self.trace,self.binary)
        self.assertEqual(report['cases'],1)
        self.assertEqual(report['results'][0]['stt'],[dict(text='喷水',elapsed_ms=0)])
        self.assertEqual(report['cases_with_tools_before_stt'],[])
        self.assertTrue(all(call.kwargs==dict(await_stt=True) for call in self.replay.call_args_list))

    def test_missing_stt_is_reported_without_inventing_input(self):
        row=self.trace['results'][0]
        del row['timeline'][2];del row['host_calls'][0]
        report=review.review(self.trace,self.binary)
        self.assertEqual(report['cases_with_tools_before_stt'],['V017'])
        self.assertEqual(report['results'][0]['stt'],[])

    def test_no_tool_case_retains_transcription_without_fake_receipt(self):
        row=self.trace['results'][0]
        row['timeline'].pop();row['host_calls'].pop();row['calls']=[];del row['host_rpc_replies']
        self.final.update(starts_this_boot=0,logical_outputs=dict(water=False))
        self.replay.return_value=[self.final]
        report=review.review(self.trace,self.binary)
        self.assertEqual(report['results'][0]['tool_count'],0)
        self.assertEqual(report['results'][0]['starts_this_boot'],0)

    def test_changed_events_receipts_and_empty_cases_are_rejected(self):
        for field,value in [('host_input_mode','simulated_initial_input'),('host_replay_sha256','0'*64),('results',[])]:
            trace={**self.trace,field:value}
            with self.subTest(field=field),self.assertRaises(ValueError):review.review(trace,self.binary)
        for change in ('text','time','reply','missing'):
            trace=copy.deepcopy(self.trace);row=trace['results'][0]
            if change=='text':row['host_calls'][0]['input_text']='前进'
            if change=='time':row['host_calls'][1]['elapsed_ms']=2
            if change=='reply':row['host_rpc_replies']=[dict(error='altered')]
            if change=='missing':row['timeline'].pop(2)
            with self.subTest(change=change),self.assertRaises(ValueError):review.review(trace,self.binary)


if __name__=='__main__':unittest.main()
