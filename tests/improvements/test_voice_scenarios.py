import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from review_voice_scenarios import score_turn


class VoiceScenarioTests(unittest.TestCase):
    def test_incomplete_silence_is_not_a_pass(self):
        result=score_turn(dict(text='先别执行',expected_calls=[]),[],[],[],False,'')
        self.assertFalse(result['strict_tool_match'])
        self.assertFalse(result['expected_receipts_match'])
        self.assertFalse(result['transcript_matches'])

    def test_rejected_call_is_still_wrong_for_non_execution(self):
        call=dict(name='self.tank.move',arguments=dict(direction='forward',duration_ms=1000))
        events=[dict(event='stt',text='先别执行'),dict(event='tool_call')]
        result=score_turn(dict(text='先别执行',expected_calls=[]),[call],
                          [dict(error=dict(message='blocked'))],events,True,'没有执行')
        self.assertTrue(result['transcript_matches'])
        self.assertTrue(result['rejected'])
        self.assertFalse(result['strict_tool_match'])
        self.assertFalse(result['expected_receipts_match'])

    def test_extra_query_before_stop_fails_and_early_call_is_visible(self):
        stop=dict(name='self.tank.stop',arguments={})
        query=dict(name='self.tank.get_status',arguments={})
        events=[dict(event='tool_call'),dict(event='stt',text='停止'),dict(event='tool_call')]
        result=score_turn(dict(text='停止',expected_calls=[stop]),[query,stop],[],events,True,'')
        self.assertFalse(result['strict_tool_match'])
        self.assertTrue(result['tools_before_stt'])

    def test_success_cannot_hide_missing_recognition(self):
        stop=dict(name='self.tank.stop',arguments={})
        wire=dict(result=dict(content=[dict(text='{"result":"ok"}')]))
        result=score_turn(dict(text='停止',expected_calls=[stop]),[stop],[wire],
                          [dict(event='tool_call')],True,'停下了')
        self.assertTrue(result['strict_tool_match'])
        self.assertTrue(result['expected_receipts_match'])
        self.assertFalse(result['transcript_matches'])
        self.assertTrue(result['tools_before_stt'])
        self.assertFalse(result['remote_text_empty'])
