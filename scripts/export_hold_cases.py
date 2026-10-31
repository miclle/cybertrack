#!/usr/bin/env python3
"""Reproduce the three spoken timing questions using a particular firmware host build."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def snapshots(replay, profile, offsets):
    calls = [dict(name="self.tank.get_status", arguments={}, elapsed_ms=t) for t in offsets]
    result = subprocess.run([str(replay.resolve()), profile], input=json.dumps(calls),
                            text=True, capture_output=True, check=True, timeout=10)
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    if len(rows) != len(calls) + 1 or any(row["result"] != "ok" for row in rows):
        raise ValueError("Missing successful firmware status read")
    return rows[:-1]


def corpus(replay):
    held, expired = snapshots(replay, "web_forward_hold", [200, 600])
    timed, = snapshots(replay, "forward70", [3600])
    if not (held["drive_hold_id"] and held["move_remaining_ms"] == timed["move_remaining_ms"] == 400
            and timed["drive_hold_id"] == expired["drive_hold_id"] == expired["move_remaining_ms"] == 0):
        raise ValueError("Firmware samples do not match hold, fixed timer and expiry preconditions")
    original = json.loads((ROOT / "docs/validation/status-hold-cases.json").read_text())
    observations = {"H201": held, "H202": timed, "H203": expired}
    if [c["id"] for c in original["cases"]] != list(observations):
        raise ValueError("Timing corpus IDs changed")
    for case in original["cases"]:
        case["fixture_status"] = observations[case["id"]]
        case["context"] = "冻结的固件主机回执"
    original["scope"] = "Independent raw text sessions; firmware host receipts with a controlled clock and stub IO."
    return original


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("replay", type=Path, help="receipt_replay from the desired source revision")
    parser.add_argument("output", type=Path, help="new corpus file")
    args = parser.parse_args()
    payload = corpus(args.replay)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
