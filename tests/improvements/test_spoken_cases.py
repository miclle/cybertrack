import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from review_spoken_cases import corpus, new_sheet, review


class SpokenCasesTests(unittest.TestCase):
    def setUp(self):
        self.sheet = new_sheet("安静")
        self.sheet.update(run_id="test", firmware="fixture", role_sha256="a" * 64, model="test")

    def test_empty_sheet_has_no_scores(self):
        result = review(self.sheet)
        self.assertEqual(len(result["not_completed"]), 20)
        for key in ("completed", "transcript_observed", "calls_scored", "reply_assessed"):
            self.assertEqual(result[key], 0)

    def test_independent_observations_and_missing_receipt(self):
        row = next(r for r in self.sheet["results"] if r["id"] == "V045")
        row.update(
            actual_utterance=row["input_text"],
            evidence_ref="anonymous observation 3",
            completed=True,
            echoed_text="停止。",
            calls=[],
            heard_reply="",
            reply_matches_expectation=True,
        )
        result = review(self.sheet)
        self.assertEqual(result["transcript_matches"], 1)
        self.assertEqual(result["stop_mismatches"], ["V045"])
        self.assertEqual(result["reply_matches"], 1)
        row["evidence_ref"] = " "
        self.assertEqual(review(self.sheet)["calls_scored"], 0)

    def test_forbidden_request_on_incomplete_run(self):
        row = next(r for r in self.sheet["results"] if r["id"] == "V067")
        row.update(
            actual_utterance=row["input_text"],
            evidence_ref="observed",
            completed=False,
            calls=copy.deepcopy(corpus()["V001"]["expected_calls"]),
        )
        result = review(self.sheet)
        self.assertEqual(result["calls_scored"], 0)
        self.assertEqual(result["forbidden_call_cases"], ["V067"])

    def test_text_input_and_unproven_synthetic_rejected(self):
        for mode in ("raw_text_diagnostic", "synthetic_opus"):
            self.sheet["input_mode"] = mode
            with self.assertRaises(ValueError):
                review(self.sheet)
