import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from review_concise_role import score


class ConciseRoleScoringTest(unittest.TestCase):
    def setUp(self):
        self.case = dict(id='V045', expected_calls=[dict(name='self.tank.stop', arguments={})])
        self.row = dict(completed=True, calls=copy.deepcopy(self.case['expected_calls']), replies=[],
                        received_audio_bytes_discarded=0, host_final_state=dict(show_draft=dict(revision=0)))

    def test_interruption_is_unknown_not_empty_or_successful(self):
        result = score(dict(id='C008', expected_calls=[]), None)
        self.assertFalse(result['strict'])
        self.assertFalse(result['calls_known'])
        self.assertIsNone(result['forbidden'])
        self.assertIsNone(result['reply'])

    def test_incomplete_no_call_cannot_pass(self):
        self.row.update(completed=False, calls=[])
        self.assertFalse(score(dict(id='C008', expected_calls=[]), self.row)['strict'])

    def test_silence_requires_completed_matching_action_and_no_audio_or_text(self):
        self.assertTrue(score(self.case, self.row)['silent'])
        for changes in [dict(completed=False), dict(calls=[]), dict(replies=['已停止']),
                        dict(received_audio_bytes_discarded=40)]:
            with self.subTest(changes=changes):
                self.assertFalse(score(self.case, self.row | changes)['silent'])

    def test_refusal_to_execute_does_not_hide_forbidden_call(self):
        result = score(dict(id='V064', expected_calls=[]), self.row)
        self.assertTrue(result['forbidden'])
        self.assertTrue(result['false_stop'])
        self.assertFalse(result['strict'])

    def test_extra_read_is_strict_failure_but_not_forbidden_write(self):
        self.row['calls'] = [dict(name='self.tank.get_status', arguments={})]
        result = score(dict(id='C005', expected_calls=[]), self.row)
        self.assertFalse(result['strict'])
        self.assertFalse(result['forbidden'])

    def test_limit_reply_is_not_scored_as_a_silence_requirement(self):
        case = dict(id='V020', expected_calls=[dict(name='self.tank.water', arguments=dict(duration_ms=30000))])
        self.row.update(calls=case['expected_calls'], replies=['单次最多三十秒。'])
        result = score(case, self.row)
        self.assertTrue(result['strict'])
        self.assertFalse(result['silence_required'])
