"""Synthetic arithmetic and incomplete-evidence regressions, no device data."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("power_budget", ROOT / "scripts/power_budget.py")
budget = importlib.util.module_from_spec(spec)
spec.loader.exec_module(budget)


def q(value):
    return dict(value=value, kind="assumption", source="synthetic unit-test fixture")


def fixture():
    return dict(schema_version=1, supply=dict(voltage_v=q(5), continuous_a=q(4)),
                branches=dict(controller={"run":dict(input_current_a=q(.5))},
                              boost={"run":dict(output_power_w=q(12), efficiency=q(.8))}),
                scenarios=[dict(id="synthetic", kind="steady", modes=dict(controller="run", boost="run"))])


class BudgetTest(unittest.TestCase):
    def test_conversion_and_margin(self):
        report = budget.evaluate(fixture())
        self.assertAlmostEqual(report["scenarios"][0]["total_input_a"], 3.5)
        self.assertAlmostEqual(report["scenarios"][0]["continuous_margin_a"], .5)
        self.assertEqual(report["electrical_acceptance"], "not_established")

    def test_real_unknowns_stay_unknown(self):
        source = json.loads((ROOT / "hardware/architecture/power-budget.json").read_text())
        for result in budget.evaluate(source)["scenarios"]:
            self.assertIsNone(result["total_input_a"])
            self.assertEqual(result["comparison"], "insufficient_data")

    def test_omission_and_double_counting_rejected(self):
        source = fixture()
        del source["scenarios"][0]["modes"]["controller"]
        with self.assertRaises(ValueError): budget.evaluate(source)
        source = fixture()
        source["branches"]["boost"]["run"]["input_current_a"] = q(3)
        with self.assertRaises(ValueError): budget.evaluate(source)

    def test_bad_efficiency_and_nonfinite_rejected(self):
        for value in [0, -1, 1.1, float("nan"), float("inf"), True]:
            source = fixture()
            source["branches"]["boost"]["run"]["efficiency"] = q(value)
            with self.subTest(value=value), self.assertRaises(ValueError): budget.evaluate(source)

    def test_startup_not_compared_with_continuous_rating(self):
        source = fixture()
        source["scenarios"][0]["kind"] = "startup"
        result = budget.evaluate(source)["scenarios"][0]
        self.assertIsNone(result["continuous_margin_a"])
        source["scenarios"][0]["kind"] = "steady"
        source["supply"]["continuous_a"] = q(1)
        self.assertEqual(budget.evaluate(source)["scenarios"][0]["comparison"], "exceeds_limit")


if __name__ == "__main__": unittest.main()
