import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
try:
    spec=importlib.util.spec_from_file_location('firmware_capture_review',ROOT/'scripts/review_firmware_capture.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
finally:
    sys.path.pop(0)


class FirmwareCaptureReviewTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.binary=Path(self.folder.name)/'host';self.binary.write_bytes(b'fixture host')
        self.corpus=Path(self.folder.name)/'corpus.json'
        self.case=json.loads((ROOT/'docs/validation/voice-cases.json').read_bytes())['cases'][-2]
        self.corpus.write_text(json.dumps(dict(cases=[self.case])))
        self.call=dict(name='self.tank.move',arguments=dict(direction='forward',duration_ms=1000))
        self.wire=dict(result=dict(content=[dict(text='{"result":"action_unspecified"}')]))
        self.final=dict(starts_this_boot=0,show_draft=dict(revision=0))
        def replay(binary,profile,calls,**kwargs):
            return [self.wire for c in calls if 'name' in c]+[self.final]
        self.replay=patch.object(module,'firmware_replay',side_effect=replay).start();self.addCleanup(patch.stopall)

    def trace(self, mode='simulated_recognized_text'):
        timeline=[dict(event='input_sent',ms=20)];history=[]
        if mode!='simulated_initial_input':
            timeline.append(dict(event='stt' if mode=='platform_stt_events' else 'simulated_input',ms=20,text=self.case['text']))
            history.append(dict(input_text=self.case['text'],elapsed_ms=0))
        if mode!='platform_stt_events':timeline.append(dict(event='stt',ms=21,text='unrelated service echo'))
        timeline.append(dict(event='tool_call',ms=30,name=self.call['name']))
        history.append(dict(self.call,elapsed_ms=10,rpc_id=44))
        row=dict(id=self.case['id'],input_text=self.case['text'],context=self.case['context'],initial_profile='corpus_idle',
            host_input_mode=mode,completed=True,timeline=timeline,host_calls=history,calls=[self.call],
            host_rpc_replies=[self.wire],host_inspect_ms=15,host_final_state=self.final,replies=['请说具体方向'])
        return dict(fixture_version='firmware_host',host_replay_sha256=hashlib.sha256(self.binary.read_bytes()).hexdigest(),
            corpus_sha256=hashlib.sha256(self.corpus.read_bytes()).hexdigest(),host_input_mode=mode,
            input_mode='synthetic_opus' if mode=='platform_stt_events' else 'raw_text_diagnostic',results=[row])

    def test_all_three_modes_keep_their_original_input_semantics(self):
        for mode in ('simulated_initial_input','simulated_recognized_text','platform_stt_events'):
            self.replay.reset_mock()
            report=module.review(self.trace(mode),self.binary,self.corpus)
            self.assertEqual(report['host_input_mode'],mode)
            self.assertEqual(report['results'][0]['input_events'],int(mode!='simulated_initial_input'))
            self.assertEqual(report['strict_tool_matches'],0)
            self.assertTrue(all(c.kwargs==dict(await_stt=mode!='simulated_initial_input') for c in self.replay.call_args_list))

    def test_wrong_original_text_order_time_or_reply_is_rejected(self):
        for change in ('text','history','time','reply','final'):
            trace=self.trace();row=trace['results'][0]
            if change=='text':row['timeline'][1]['text']='前进'
            if change=='history':row['host_calls'].pop(0)
            if change=='time':row['host_calls'][-1]['elapsed_ms']=11
            if change=='reply':row['host_rpc_replies']=[dict(error='changed')]
            if change=='final':row['host_final_state']=dict(starts_this_boot=1)
            with self.subTest(change=change),self.assertRaises(ValueError):module.review(trace,self.binary,self.corpus)

    def test_missing_or_duplicate_simulated_input_is_rejected(self):
        for change in ('missing','duplicate'):
            trace=self.trace();row=trace['results'][0]
            if change=='missing':row['timeline'].pop(1);row['host_calls'].pop(0)
            else:
                row['timeline'].insert(1,copy.deepcopy(row['timeline'][1]));row['host_calls'].insert(0,copy.deepcopy(row['host_calls'][0]))
            with self.subTest(change=change),self.assertRaises(ValueError):module.review(trace,self.binary,self.corpus)

    def test_missing_actual_stt_is_reported_without_fabricating_input(self):
        trace=self.trace('platform_stt_events');row=trace['results'][0]
        row['timeline'].pop(1);row['host_calls'].pop(0)
        report=module.review(trace,self.binary,self.corpus)
        self.assertEqual(report['tools_before_input'],[self.case['id']])
        self.assertEqual(report['results'][0]['input_events'],0)

    def test_wrong_provenance_binary_or_corpus_is_rejected(self):
        for field,value in [('host_input_mode','unknown'),('input_mode','synthetic_opus'),
                            ('host_replay_sha256','0'*64),('corpus_sha256','0'*64),('results',[])]:
            trace=self.trace();trace[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):module.review(trace,self.binary,self.corpus)
