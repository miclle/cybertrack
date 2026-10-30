"""Synthetic observations test arithmetic and gates, never supply field evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("stop_trials", ROOT / "scripts/analyze_stop_trials.py")
stop = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = stop
spec.loader.exec_module(stop)


def profile(name="synthetic", kind="software_simulation"):
    return {"id": name, "evidence_kind": kind, "firmware_sha256": "a"*64, "battery": "synthetic",
            "load": "synthetic", "ground_surface": "synthetic", "speed_percent": 100,
            "method": "synthetic test only", "timing_uncertainty_ms": 1, "observation_window_ms": 5000}


def trial(case, repeat=1, name="synthetic"):
    channels = {}
    for channel, source in case.sources.items():
        off = 1010 if case.phase == "active" else 900
        channels[channel] = {"source": source, "output_off_ms": off if channel in case.stop else None,
                             "mechanical_stop_ms": (1030 if case.phase == "active" else 920) if channel == "move" and channel in case.stop else None,
                             "stopping_distance_mm": 12 if channel == "move" and channel in case.stop else None,
                             "continued_until_own_deadline": True if channel in case.keep else None}
    return {"id": f"{name}-{case.id}-{repeat}", "profile_id": name, "case_id": case.id,
            "repeat": repeat, "evidence_ref": f"synthetic:{name}:{case.id}:{repeat}", "event_ms": 1000,
            "channels": channels, "recovery_observed": True, "stale_action_resumed": False}


def dataset():
    return {"schema_version": 1, "profiles": [profile()],
            "trials": [trial(c, n) for c in stop.CASES for n in range(1, 6)]}


class StopTrialsTest(unittest.TestCase):
    def test_initialized_rows_are_all_unknown_and_do_not_count(self):
        data = stop.initialize(profile())
        self.assertEqual(len(data["trials"]), 85)
        report = stop.analyze(data)
        self.assertFalse(report["profiles"][0]["coverage_complete"])
        self.assertEqual(report["physical_profiles_with_complete_records"], [])
        for row in report["profiles"][0]["cases"]:
            self.assertEqual(row["complete_records"], 0)
            self.assertEqual(row["additional_complete_records_needed"], 5)
            self.assertTrue(all(t["missing"] for t in row["trials"]))

    def test_empty_is_not_physical_coverage(self):
        report = stop.analyze(json.loads((ROOT / "docs/validation/stop-trials.json").read_text()))
        self.assertEqual(len(report["required_cases"]), 17)
        self.assertEqual(report["physical_profiles_with_complete_records"], [])
        self.assertEqual(report["physical_acceptance"], "not_established")

    def test_simulated_complete_matrix_is_never_physical(self):
        report = stop.analyze(dataset())
        self.assertTrue(report["profiles"][0]["coverage_complete"])
        self.assertEqual(report["physical_profiles_with_complete_records"], [])
        row = report["profiles"][0]["cases"][0]
        self.assertEqual(row["metrics"]["move"]["output_latency_ms"], {"count": 5, "median": 10, "max": 10})
        self.assertEqual(row["metrics"]["move"]["mechanical_latency_ms"]["median"], 30)
        self.assertEqual(row["metrics"]["move"]["stopping_distance_mm"]["median"], 12)

    def test_source_isolation_and_replay_failure_cannot_be_diluted(self):
        data = dataset()
        failed = trial(stop.CASE_BY_ID["page_hidden_mixed"], 6)
        failed["channels"]["bubbles"]["continued_until_own_deadline"] = False
        failed["stale_action_resumed"] = True
        data["trials"].append(failed)
        report = stop.analyze(data)
        row = next(c for c in report["profiles"][0]["cases"] if c["case_id"] == "page_hidden_mixed")
        self.assertEqual(row["status"], "violations_recorded")
        self.assertEqual(len(row["trials"][-1]["violations"]), 2)
        self.assertFalse(report["profiles"][0]["coverage_complete"])

    def test_unknown_mechanical_stop_and_recovery_are_not_zero(self):
        data = dataset()
        data["trials"][0]["channels"]["move"]["mechanical_stop_ms"] = None
        data["trials"][0]["recovery_observed"] = None
        report = stop.analyze(data)
        row = report["profiles"][0]["cases"][0]
        self.assertEqual(row["complete_records"], 4)
        self.assertEqual(row["metrics"]["move"]["mechanical_latency_ms"]["count"], 4)
        self.assertEqual(row["status"], "incomplete")
        # An incomplete extra repetition is not hidden after five complete ones.
        extra = trial(stop.CASES[0], 6)
        data = dataset(); extra["stale_action_resumed"] = None; data["trials"].append(extra)
        self.assertEqual(stop.analyze(data)["profiles"][0]["cases"][0]["status"], "incomplete")

    def test_profiles_and_phases_are_not_pooled(self):
        data = {"schema_version": 1, "profiles": [profile("a"), profile("b")],
                "trials": [trial(stop.CASES[0], n, "a") for n in range(1, 4)] +
                          [trial(stop.CASES[0], n, "b") for n in range(1, 3)]}
        report = stop.analyze(data)
        self.assertEqual([p["cases"][0]["complete_records"] for p in report["profiles"]], [3, 2])
        self.assertTrue(all(not p["coverage_complete"] for p in report["profiles"]))
        self.assertEqual(report["profiles"][0]["cases"][1]["complete_records"], 0)

    def test_waiting_outputs_already_off_and_independent_mechanical_clock(self):
        case = stop.CASE_BY_ID["sequence_cancel_web_waiting"]
        data = {"schema_version": 1, "profiles": [profile()], "trials": [trial(case)]}
        report = stop.analyze(data)
        row = next(c for c in report["profiles"][0]["cases"] if c["case_id"] == case.id)
        self.assertEqual(row["metrics"]["move"]["output_latency_ms"]["median"], 0)
        data["trials"][0]["channels"]["move"]["output_off_ms"] = 1010
        report = stop.analyze(data)
        row = next(c for c in report["profiles"][0]["cases"] if c["case_id"] == case.id)
        self.assertEqual(row["status"], "violations_recorded")
        # A track can mechanically stop before the drive signal is disabled.
        data["trials"] = [trial(stop.CASES[0])]
        data["trials"][0]["channels"]["move"]["mechanical_stop_ms"] = 1005
        self.assertEqual(stop.analyze(data)["profiles"][0]["cases"][0]["complete_records"], 1)

    def test_bad_values_duplicate_identity_and_source_are_rejected(self):
        base = {"schema_version": 1, "profiles": [profile()], "trials": [trial(stop.CASES[0])]}
        mutations = [
            lambda d: d["trials"].append(copy.deepcopy(d["trials"][0])),
            lambda d: d["trials"][0].update(case_id="unknown"),
            lambda d: d["trials"][0].update(repeat=True),
            lambda d: d["trials"][0].update(stale_action_resumed="false"),
            lambda d: d["trials"][0].update(event_ms=float("nan")),
            lambda d: d["trials"][0]["channels"]["move"].update(source="voice"),
            lambda d: d["trials"][0]["channels"]["move"].update(output_off_ms=-1),
            lambda d: d["trials"][0]["channels"]["move"].update(output_off_ms=999),
            lambda d: d["profiles"][0].update(speed_percent=True),
            lambda d: d["profiles"][0].update(observation_window_ms=0),
            lambda d: d["profiles"][0].update(firmware_sha256="ct45"),
        ]
        for mutate in mutations:
            data = copy.deepcopy(base); mutate(data)
            with self.subTest(data=data), self.assertRaises(ValueError): stop.analyze(data)
        duplicate = trial(stop.CASES[0], 2); duplicate["evidence_ref"] = base["trials"][0]["evidence_ref"]
        base["trials"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "event already counted"): stop.analyze(base)

    def test_cli_keeps_input_and_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder)/"trials.json", Path(folder)/"report.json"
            source.write_text(json.dumps(dataset()))
            command = [sys.executable, str(ROOT/"scripts/analyze_stop_trials.py"), str(source), "--output"]
            result = subprocess.run(command+[str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text())
            self.assertEqual(report["input"], dataset())
            self.assertRegex(report["input_sha256"], r"^[a-f0-9]{64}$")
            before = source.read_bytes()
            result = subprocess.run(command+[str(source)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(source.read_bytes(), before)
            source.write_text('{"schema_version": 1, "schema_version": 1, "profiles": [], "trials": []}')
            result = subprocess.run(command+[str(output)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate JSON field", result.stderr)
            source.write_text(json.dumps(profile()))
            target = Path(folder)/"unobserved.json"
            init = [sys.executable, str(ROOT/"scripts/analyze_stop_trials.py"), "--init-profile", str(source), "--output", str(target)]
            result = subprocess.run(init, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(target.read_text()), stop.initialize(profile()))
            before = target.read_bytes()
            result = subprocess.run(init, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
