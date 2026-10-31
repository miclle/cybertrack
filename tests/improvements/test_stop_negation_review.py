import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
try:
    spec=importlib.util.spec_from_file_location('stop_negation_review',ROOT/'scripts/review_stop_negation.py')
    review=importlib.util.module_from_spec(spec);spec.loader.exec_module(review)
finally:
    sys.path.pop(0)


class StopNegationReviewTests(unittest.TestCase):
    def summary(self,calls,expected,revision=7,wanted=7,completed=True):
        row=dict(id='N001',completed=completed,calls=calls,replies=[])
        case=dict(expected_calls=expected,expected_draft_revision=wanted)
        final=dict(show_draft=dict(revision=revision),starts_this_boot=0)
        result=review.summarize_case(row,case,final)
        return result,review.contrast_can_proceed([result],dict(N001=case))

    def test_read_only_query_is_still_a_strict_mismatch(self):
        result,proceed=self.summary([dict(name='self.tank.get_status',arguments={})],[])
        self.assertFalse(result['strict_tool_match'])
        self.assertEqual(result['unexpected_control_calls'],[])
        self.assertTrue(proceed) # Only permission to run the fixed suite, never a semantic pass.

    def test_erroneous_stop_fails_even_if_outputs_are_off(self):
        result,proceed=self.summary([dict(name='self.tank.stop',arguments={})],[],revision=0)
        self.assertEqual(result['unexpected_control_calls'],['self.tank.stop'])
        self.assertFalse(result['draft_matches'])
        self.assertFalse(proceed)

    def test_stop_must_be_direct_and_positive_parameters_must_match(self):
        stop=dict(name='self.tank.stop',arguments={})
        query=dict(name='self.tank.get_status',arguments={})
        self.assertTrue(self.summary([stop],[stop],revision=0,wanted=0)[1])
        self.assertFalse(self.summary([query,stop],[stop],revision=0,wanted=0)[1])
        effect=dict(name='self.tank.bubbles',arguments=dict(duration_ms=2000))
        wrong=dict(name='self.tank.bubbles',arguments=dict(duration_ms=1000))
        self.assertFalse(self.summary([wrong],[effect])[1])

    def test_incomplete_and_non_boolean_completion_cannot_pass(self):
        self.assertFalse(self.summary([],[],completed=False)[1])
        for value in ('false',None,1):
            with self.assertRaises(ValueError):self.summary([],[],completed=value)


if __name__=='__main__':unittest.main()
