"""Synthetic prices exercise accounting only."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "cost", Path(__file__).resolve().parents[2] / "scripts/summarize_parts_cost.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PartsCostTest(unittest.TestCase):
    def test_prices_are_separate_and_exact(self):
        purchase = dict(bom_id="H01", source="receipt-A/1", quantity=3, actual_unit_cny="0.10",
                        purchased_on="2026-10-31", estimate_only=False)
        quote = dict(bom_id="H02", source="offer-B/3", quantity=2, estimated_unit_cny="0.33",
                     scenario="batch-A", estimate_only=True)
        rows = [purchase, quote, dict(purchase, actual_unit_cny=None)]
        r = module.summarize(rows, {"H01", "H02"})
        self.assertEqual(r["actual_subtotal_cny"], "0.30")
        self.assertEqual(r["quote_subtotals_cny"], {"batch-A": "0.66"})
        self.assertEqual(r["bom_ids_without_purchase_evidence"], ["H02"])
        self.assertEqual(r["incomplete_row_numbers"], [3])
        with self.assertRaises(ValueError):
            module.summarize([purchase, purchase], {"H01"})

    def test_empty_and_unknown(self):
        self.assertIsNone(module.summarize([], {"H01"})["actual_subtotal_cny"])
        with self.assertRaises(ValueError):
            module.summarize([{"bom_id": "H999"}], {"H01"})
