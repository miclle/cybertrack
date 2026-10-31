import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("evaluate_voice", ROOT / "scripts/evaluate_voice.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class VoiceEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.corpus = json.loads((ROOT / "docs/validation/voice-cases.json").read_text())
        self.trace = {"kind": "captured_tool_calls", "model": "synthetic-test-only", "role_sha256": "test",
                      "run_id": "synthetic-unit-test", "results": [
                          {"id": c["id"], "calls": copy.deepcopy(c["expected_calls"])} for c in self.corpus["cases"]]}

    def test_complete_trace_and_missing_results(self):
        self.assertTrue(module.evaluate(self.corpus, self.trace)["tool_call_target_met"])
        self.trace["results"].pop()
        result = module.evaluate(self.corpus, self.trace)
        self.assertFalse(result["tool_call_target_met"])
        self.assertEqual(len(result["missing"]), 1)

    def test_negative_action_is_failure_despite_high_average(self):
        row = next(r for r in self.trace["results"] if r["id"] == "V061")
        row["calls"] = [{"name": "self.tank.move", "arguments": {"direction": "forward", "duration_ms": 1}}]
        result = module.evaluate(self.corpus, self.trace)
        self.assertGreater(result["accuracy_all_cases"], .95)
        self.assertFalse(result["tool_call_target_met"])
        self.assertEqual(result["forbidden_call_cases"], ["V061"])

    def test_no_duplicate_or_unknown_case(self):
        self.trace["results"].append(self.trace["results"][0])
        with self.assertRaises(ValueError): module.evaluate(self.corpus, self.trace)

    def test_timeout_is_not_a_successful_no_action_case(self):
        row = next(r for r in self.trace["results"] if r["id"] == "V061")
        row["completed"] = False
        result = module.evaluate(self.corpus, self.trace)
        self.assertGreater(result["accuracy_all_cases"], .95)
        self.assertEqual(result["incomplete"], ["V061"])
        self.assertFalse(result["tool_call_target_met"])
        row["completed"] = "false"
        with self.assertRaises(ValueError): module.evaluate(self.corpus, self.trace)

    def test_equivalent_names_defaults_but_not_types(self):
        left = [{"name": "self_tank_move", "arguments": {"direction": "forward", "duration_ms": 1}}]
        right = [{"name": "self.tank.move", "arguments": {"direction": "forward", "duration_ms": 1, "speed_percent": 100}}]
        self.assertEqual(module.canonical(left), module.canonical(right))
        right[0]["arguments"]["duration_ms"] = True
        self.assertNotEqual(module.canonical(left), module.canonical(right))

    def test_draft_contract_never_allows_direct_action(self):
        corpus = json.loads((ROOT / "docs/validation/compose-cases.json").read_text())
        trace = {"kind": "captured_tool_calls", "model": "synthetic-test", "role_sha256": "synthetic", "run_id": "unit",
                 "results": [{"id": case["id"], "calls": case["expected_calls"]} for case in corpus["cases"]]}
        self.assertTrue(module.evaluate(corpus, trace)["tool_call_target_met"])
        trace["results"][4]["calls"] = [{"name": "self.tank.move", "arguments": {"direction": "forward", "duration_ms": 1}}]
        self.assertIn("C005", module.evaluate(corpus, trace)["forbidden_call_cases"])

    def test_twenty_spoken_cases_are_real_corpus_references(self):
        spoken = json.loads((ROOT / "docs/validation/spoken-cases.json").read_text())
        self.assertEqual(len(set(spoken["case_ids"])), 20)
        self.assertTrue(set(spoken["case_ids"]) <= {c["id"] for c in self.corpus["cases"]})


if __name__ == "__main__": unittest.main()
