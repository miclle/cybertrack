import gzip
import json
from pathlib import Path
import unittest
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from review_draft_replies import review


class DraftRepliesTest(unittest.TestCase):
    def setUp(self):
        path = ROOT / "docs/validation/evidence/role-5991/edit-variants-1.json.gz"
        self.trace = json.loads(gzip.decompress(path.read_bytes()))

    def test_separates_narration_from_clarification(self):
        edit, removal, question = review(self.trace)["rows"]
        self.assertTrue(edit["english_phrase"] and edit["tool_word"] and edit["audio_before_saved"])
        self.assertFalse(removal["english_phrase"])
        self.assertEqual(edit["before_saved_segments"], 1)
        self.assertIsNone(question["before_saved_segments"])
        self.assertIsNone(question["audio_before_saved"])
        self.assertIn("具体秒数", question["reply"])

    def test_requires_complete_matching_trace(self):
        self.trace["results"][0]["completed"] = False
        with self.assertRaises(ValueError):
            review(self.trace)

    def test_rejects_missing_boundary(self):
        row = self.trace["results"][0]
        row["timeline"] = [e for e in row["timeline"] if e["event"] != "tts_sentence_start"]
        with self.assertRaises(ValueError):
            review(self.trace)
