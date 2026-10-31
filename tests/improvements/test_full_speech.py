import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from review_full_speech import score_speech, score_replay


class FullSpeechTests(unittest.TestCase):
    def setUp(self):
        self.corpus=json.loads((ROOT/'docs/validation/voice-cases.json').read_text())
        self.trace=dict(kind='captured_tool_calls',model='synthetic-unit-fixture-only',run_id='unit-only',role_sha256='a'*64,
            corpus_sha256='b'*64,host_replay_sha256='c'*64,tool_schema_sha256='d'*64,capture_source_sha256='e'*64,
            synthesis_source_sha256='f'*64,input_mode='synthetic_opus',host_input_mode='platform_stt_events',step_argument_format='legacy_string',results=[])
        for case in self.corpus['cases']:
            self.trace['results'].append(dict(id=case['id'],input_text=case['text'],echoed_text=case['text'],completed=True,
                calls=copy.deepcopy(case['expected_calls']),timeline=[dict(event='stt',text=case['text'])],
                uplink=dict(codec='opus',sample_rate_hz=16000,channels=1,frame_ms=60,frames=1,encoded_bytes=1,payload_sha256='0'*64)))

    def test_score_replay_retains_stt_and_every_tool_failure(self):
        self.trace['results'][63]['calls']=[dict(name='self.tank.stop',arguments={})]
        before=score_speech(self.corpus,self.trace)
        after=score_speech(self.corpus,score_replay(self.trace))
        self.assertEqual(before,after)
        self.assertIn('V064',after['tools']['forbidden_call_cases'])
        self.assertFalse(after['tools']['tool_call_target_met'])

    def test_matching_tools_never_imply_transcription(self):
        row=self.trace['results'][0];row['timeline']=[];row['echoed_text']=''
        result=score_speech(self.corpus,self.trace)
        self.assertEqual(result['tools']['correct'],80)
        self.assertEqual(result['transcription']['matches'],79)
        self.assertEqual(result['transcription']['missing_stt'],['V001'])
        del row['echoed_text']
        self.assertEqual(score_speech(self.corpus,self.trace),score_speech(self.corpus,score_replay(self.trace)))

    def test_incomplete_stop_is_not_success_even_with_received_stt_and_tool(self):
        self.trace['results'][44]['completed']=False
        result=score_speech(self.corpus,self.trace)
        self.assertEqual(result['transcription']['matches'],80)
        self.assertEqual(result['tools']['failed_stop_cases'],['V045'])
        self.assertEqual(result['tools']['incomplete'],['V045'])

    def test_echo_cannot_override_received_stt(self):
        self.trace['results'][0]['echoed_text']='伪造正确识别'
        with self.assertRaises(ValueError):score_speech(self.corpus,self.trace)

    def test_text_simulation_cannot_be_scored_as_asr(self):
        self.trace['host_input_mode']='simulated_recognized_text'
        with self.assertRaises(ValueError):score_speech(self.corpus,self.trace)
        self.trace['host_input_mode']='platform_stt_events'
        self.trace['results'][0]['timeline'].append(dict(event='simulated_input',text='前进'))
        with self.assertRaises(ValueError):score_speech(self.corpus,self.trace)

    def test_semantic_characters_are_not_erased_by_normalization(self):
        row=self.trace['results'][0]
        for suffix in ('.5','-1','%'):
            row['echoed_text']=row['input_text']+suffix
            row['timeline']=[dict(event='stt',text=row['echoed_text'])]
            self.assertEqual(score_speech(self.corpus,self.trace)['transcription']['mismatches'],['V001'])

    def test_actual_step_wire_format_stays_strict(self):
        row=next(r for r in self.trace['results'] if any(c['name']=='self.tank.sequence' for c in r['calls']))
        for call in row['calls']:
            if call['name']=='self.tank.sequence':call['arguments']['steps']=json.loads(call['arguments'].pop('steps_json'))
        self.assertIn(row['id'],score_speech(self.corpus,self.trace)['tools']['invalid_tool_argument_cases'])

    def test_encoder_provenance_cannot_be_placeholder_counts(self):
        for field,value in [('frames',True),('encoded_bytes',0),('frame_ms',20)]:
            changed=copy.deepcopy(self.trace);changed['results'][0]['uplink'][field]=value
            with self.assertRaises(ValueError):score_speech(self.corpus,changed)


if __name__=='__main__':unittest.main()
