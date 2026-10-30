#!/usr/bin/env python3
"""Compute a nominal supply-current budget; missing evidence remains unknown."""
import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KINDS = {"measured", "vendor_spec", "user_spec", "assumption", "derived", "unknown"}


def quantity(item, name, positive=False, maximum=None):
    if not isinstance(item, dict) or set(item) != {"value", "kind", "source"}:
        raise ValueError(f"{name}: require value, kind and source")
    if item["kind"] not in KINDS or not isinstance(item["source"], str) or not item["source"].strip():
        raise ValueError(f"{name}: evidence kind and source required")
    value = item["value"]
    if value is None:
        if item["kind"] != "unknown":
            raise ValueError(f"{name}: missing value must be unknown")
        return None
    if item["kind"] == "unknown" or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name}: finite number with evidence required")
    if value < 0 or (positive and value == 0) or (maximum is not None and value > maximum):
        raise ValueError(f"{name}: value outside range")
    return value


def demand_current(item, voltage, name):
    if set(item) == {"input_current_a"}:
        return quantity(item["input_current_a"], name)
    if set(item) != {"output_power_w", "efficiency"}:
        raise ValueError(f"{name}: use input current OR complete output power/efficiency, never both")
    power = quantity(item["output_power_w"], name + ".output_power_w")
    efficiency = quantity(item["efficiency"], name + ".efficiency", positive=True, maximum=1)
    if None in (power, efficiency, voltage):
        return None
    return power / (voltage * efficiency)


def evaluate(data):
    if data["schema_version"] != 1:
        raise ValueError("unsupported schema")
    supply = data["supply"]
    voltage = quantity(supply["voltage_v"], "supply.voltage_v", positive=True)
    continuous = quantity(supply["continuous_a"], "supply.continuous_a", positive=True)
    # Runtime deliberately omitted: nameplate cell capacity is not measured usable output energy.
    branches = data["branches"]
    if not branches:
        raise ValueError("at least one branch required")
    currents = {}
    for branch, modes in branches.items():
        if not modes:
            raise ValueError(f"{branch}: no modes")
        currents[branch] = {mode: demand_current(item, voltage, branch + "." + mode) for mode, item in modes.items()}
    scenarios, names = [], set()
    for scenario in data["scenarios"]:
        name = scenario["id"]
        if name in names or scenario["kind"] not in ("steady", "startup"):
            raise ValueError("duplicate scenario or invalid kind")
        names.add(name)
        if set(scenario["modes"]) != set(branches):
            raise ValueError(f"{name}: every branch must be accounted for, including idle leakage")
        values = {branch: currents[branch][mode] for branch, mode in scenario["modes"].items()}
        missing = [branch for branch, value in values.items() if value is None]
        total = None if missing else sum(values.values())
        margin = continuous - total if total is not None and continuous is not None and scenario["kind"] == "steady" else None
        scenarios.append({"id": name, "kind": scenario["kind"], "branch_input_a": values,
                          "missing_branches": missing, "total_input_a": total,
                          "continuous_margin_a": margin,
                          "comparison": "insufficient_data" if margin is None else ("exceeds_limit" if margin < 0 else "within_stated_limit")})
    if not scenarios:
        raise ValueError("at least one scenario required")
    return {"schema_version": 1, "scope": "nominal algebraic budget only; evidence classes remain in input",
            "supply_voltage_v": voltage, "supply_continuous_a": continuous, "scenarios": scenarios,
            "electrical_acceptance": "not_established", "runtime_estimate": "not_computed",
            "limits": ["no physical load, wiring loss, temperature, protection or transient validation",
                       "startup sums are hypotheses; no pulse-duration-qualified source comparison",
                       "assumed/specification inputs do not become measurements"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=ROOT / "hardware/architecture/power-budget.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        source = json.loads(args.input.read_text())
        report = evaluate(source)
    except (ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    # Keep provenance attached to every report, including derived totals.
    report["input"] = source
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
