"""Synthetic durations only. No device measurements."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "power_runs", Path(__file__).resolve().parents[2] / "scripts/analyze_power_runs.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def run(number, **changes):
    return dict(dict(run_id=str(number), firmware="fixture", battery="test-pack",
                     procedure="sequence", condition_id="full-to-stop", rail="battery_output",
                     duration_s=100*number, voltage_v=5, current_a=1, temperature_c=25,
                     rating_source="test specification", instrument="test meter",
                     reset_count=0, end_reason="planned_endpoint"), **changes)


class PowerRunsTest(unittest.TestCase):
    def test_rails_share_a_clock_and_resets_remain_visible(self):
        rows = [run(1), run(1, rail="controller"), run(2), run(3), run(4, reset_count=1)]
        report, = module.analyze(rows)["groups"]
        self.assertEqual(report["completed_count"], 3)
        self.assertEqual(report["completed_median_s"], 200)
        self.assertIn("4", report["excluded"])

    def test_distinct_conditions_and_missing_data(self):
        rows = [run(1), run(2), run(3, condition_id="different"),
                run(4, end_reason="manual_stop"), run(5, current_a=None),
                run(6, condition_id=None), run(7, run_id=None)]
        result = module.analyze(rows)
        self.assertTrue(all(g["completed_median_s"] is None for g in result["groups"]))
        self.assertEqual(result["groups"][1]["excluded"],
                         {"4": "manual_stop", "5": "missing_battery_measurement"})
        self.assertEqual(result["unclassified_run_ids"], ["6"])
        self.assertEqual(result["missing_id_rows"], 1)

    def test_conflicting_run_duration_rejected(self):
        with self.assertRaises(ValueError):
            module.analyze([run(1), run(1, duration_s=200)])
