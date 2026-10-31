#!/usr/bin/env python3
"""Score a preassigned five-family group from local observer sheets, without personal data."""
import argparse
from collections import Counter, defaultdict
import json
import math
import re
from pathlib import Path

FAMILIES = tuple(f"F{i:02}" for i in range(1, 6))
SHOWS = ("登场", "庆祝", "谢幕", "自编剧场")
PLAYS = ("左转一秒", "吹泡泡一秒", *SHOWS[:3])
CUSTOM_SHOW = re.compile(r"自编/[A-Za-z0-9_-]{1,24}")
PROFILE = ("cohort_id", "prototype_or_device", "firmware", "condition_id")


def choices(row, key, allowed):
    values = row.get(key)
    if values is None:
        return None
    if not isinstance(values, list) or any(not isinstance(v, str) or (v not in allowed and not (key == "repeat_plays" and CUSTOM_SHOW.fullmatch(v))) for v in values) or len(values) != len(set(values)):
        raise ValueError(f"Invalid {key} for {row['anonymous_id']}")
    return set(values)


def independently_started_and_stopped(row):
    fields = ("first_use", "first_action_completed", "independent_stop")
    flags = [row.get(k) for k in fields]
    if any(v is not None and type(v) is not bool for v in flags):
        raise ValueError("First use, action and stop observations must be boolean or null")
    elapsed, help_count = row.get("first_use_seconds"), row.get("help_count")
    if elapsed is not None and (type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0):
        raise ValueError("Invalid first use duration")
    if help_count is not None and (type(help_count) is not int or help_count < 0):
        raise ValueError("Invalid help count")
    if row.get("first_use") is not True:
        return None
    if False in flags or (help_count is not None and help_count > 0) or (elapsed is not None and elapsed > 180):
        return False
    if None in flags or help_count is None or elapsed is None:
        return None
    return True


def gate(observed, positive, minimum, mode):
    result = "pending"
    if observed == len(FAMILIES):
        result = "met" if positive >= minimum else "missed"
    return {"observed": observed, "positive": positive, "required": minimum,
            "result": result, "scope": "prototype_only" if mode == "prototype" else "device"}


def summarize(records):
    groups = defaultdict(dict)
    unclassified = dry_runs = 0
    for r in records:
        if r.get("evidence_kind") == "dry_run":
            dry_runs += 1
            continue
        profile = tuple(r.get(k) for k in PROFILE)
        if any(v is None or v == "" for v in profile):
            unclassified += 1  # Historical rows have no cohort or condition.
            continue
        if not all(isinstance(v, str) and v.strip() for v in profile) or profile[1] not in ("device", "prototype"):
            raise ValueError("Invalid cohort, mode, revision or network condition")
        family = r.get("anonymous_id")
        if family not in FAMILIES or family in groups[profile]:
            raise ValueError(f"Unexpected or duplicate family in the selected group: {family}")
        groups[profile][family] = r
    reports = []
    for profile, families in sorted(groups.items()):
        first = []
        repeat_observed = theatre_observed = theatre_positive = 0
        repeats = Counter()
        for row in families.values():
            if row.get("parent_present") is not True or row.get("evidence_kind") != "family_observation":
                continue
            independent = independently_started_and_stopped(row)
            if independent is not None:
                first.append(independent)
            if row.get("free_play_observed") is not True:
                continue
            plays = choices(row, "repeat_plays", PLAYS)
            edits = choices(row, "modified_shows", SHOWS)
            if plays is not None:
                repeat_observed += 1
                repeats.update(plays)
            replayed_show = any(p in SHOWS or CUSTOM_SHOW.fullmatch(p) for p in (plays or ()))
            if replayed_show or edits or (plays is not None and edits is not None):
                theatre_observed += 1
                theatre_positive += bool(replayed_show or edits)
        reports.append({
            **dict(zip(PROFILE, profile)), "missing_sheets": sorted(set(FAMILIES) - families.keys()),
            "independent_use": gate(len(first), sum(first), 4, profile[1]),
            "repeat_by_play": dict(sorted(repeats.items())),
            "same_play_repeated": gate(repeat_observed, max(repeats.values(), default=0), 3, profile[1]),
            "replayed_or_modified_show": gate(theatre_observed, theatre_positive, 3, profile[1]),
        })
    return {"groups": reports, "unclassified_rows": unclassified, "dry_run_rows": dry_runs}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path, nargs="+")
    args = parser.parse_args()
    try:
        records = []
        for path in args.records:
            records.extend(json.loads(path.read_text())["family_sessions"])
        print(json.dumps(summarize(records), indent=2, ensure_ascii=False))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"{exc}\n")
