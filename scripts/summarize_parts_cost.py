"""Subtotal traceable prototype purchases and keep each quote scenario separate."""
import argparse
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def amount(value):
    try:
        n = Decimal(str(value))
    except InvalidOperation:
        return None
    return n if n.is_finite() and n >= 0 else None


def money(value):
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def summarize(rows, bom_ids):
    actual = {}
    quotes = defaultdict(dict)
    seen = set()
    missing = []
    for index, item in enumerate(rows, 1):
        bom = item.get("bom_id")
        if bom not in bom_ids:
            raise ValueError(f"row {index}: unknown BOM ID {bom}")
        estimate = item.get("estimate_only")
        source = item.get("source")
        qty = amount(item.get("quantity"))
        price = amount(item.get("estimated_unit_cny") if estimate else item.get("actual_unit_cny"))
        scenario = item.get("scenario")
        if type(estimate) is not bool or not isinstance(source, str) or not source.strip() or not qty or price is None:
            missing.append(index)
            continue
        if estimate:
            if not isinstance(scenario, str) or not scenario.strip():
                missing.append(index)
                continue
            bucket = quotes[scenario]
        else:
            try:
                date.fromisoformat(item.get("purchased_on"))
            except (TypeError, ValueError):
                missing.append(index)
                continue
            bucket = actual
        # A redacted source identifies one receipt/quotation line, including its line number.
        key = (estimate, scenario if estimate else None, source.strip())
        if key in seen:
            raise ValueError(f"row {index}: duplicate source line")
        seen.add(key)
        bucket[bom] = bucket.get(bom, Decimal(0)) + qty * price
    return {"actual_by_bom_cny": {k: money(v) for k, v in sorted(actual.items())},
            "actual_subtotal_cny": money(sum(actual.values())) if actual else None,
            "quote_subtotals_cny": {k: money(sum(v.values())) for k, v in sorted(quotes.items())},
            "bom_ids_without_purchase_evidence": sorted(bom_ids - actual.keys()),
            "incomplete_row_numbers": missing}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    args = parser.parse_args()
    ids = set(re.findall(r"^\| (H\d+[a-z]?) \|", (ROOT / "hardware/BOM.md").read_text(), re.M))
    if not ids:
        parser.error("missing hardware BOM IDs")
    print(json.dumps(summarize(json.loads(args.record.read_text(), parse_float=Decimal)["cost_items"], ids),
                     indent=2, ensure_ascii=False))
