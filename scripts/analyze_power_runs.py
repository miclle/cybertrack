"""Group observed battery runtimes by test conditions, keeping interrupted runs visible."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
from statistics import median

CONDITION = ("firmware", "battery", "procedure", "condition_id")
RUN_FIELDS = (*CONDITION, "duration_s", "end_reason", "reset_count")


def present(value):
    return isinstance(value, str) and bool(value.strip())


def finite(value):
    return type(value) in (float, int) and math.isfinite(value)


def analyze(rows):
    runs = defaultdict(list)
    missing_id_rows = 0
    for row in rows:
        if present(row.get("run_id")):
            runs[row["run_id"]].append(row)
        else:
            missing_id_rows += 1

    groups = defaultdict(lambda: {"completed_s": {}, "excluded": {}})
    unclassified = []
    for run_id, samples in runs.items():
        first = samples[0]
        if any(first.get(k) != sample.get(k) for k in RUN_FIELDS for sample in samples):
            raise ValueError(f"{run_id}: conflicting run-level fields")
        if not all(present(first.get(k)) for k in CONDITION):
            unclassified.append(run_id)
            continue
        group = groups[tuple(first[k] for k in CONDITION)]
        duration = first.get("duration_s")
        reason = first.get("end_reason")
        reset = first.get("reset_count")
        if reason != "planned_endpoint":
            group["excluded"][run_id] = reason or "unknown_endpoint"
        elif type(reset) is not int or reset != 0:
            group["excluded"][run_id] = "reset_or_missing_reset_count"
        elif not finite(duration) or duration <= 0:
            group["excluded"][run_id] = "invalid_duration"
        elif not any(s.get("rail") == "battery_output"
                     and all(present(s.get(k)) for k in ("instrument", "rating_source"))
                     and all(finite(s.get(k)) for k in ("voltage_v", "current_a", "temperature_c"))
                     for s in samples):
            group["excluded"][run_id] = "missing_battery_measurement"
        else:
            group["completed_s"][run_id] = duration

    reports = []
    for key, group in sorted(groups.items()):
        durations = group["completed_s"].values()
        reports.append({**dict(zip(CONDITION, key)), **group,
                        "completed_count": len(durations),
                        "completed_median_s": median(durations) if len(durations) >= 3 else None})
    return {"groups": reports, "unclassified_run_ids": sorted(unclassified),
            "missing_id_rows": missing_id_rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(json.loads(args.record.read_text())["power_runs"]),
                     indent=2, ensure_ascii=False))
