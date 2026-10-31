#!/usr/bin/env python3
"""Check the host protocol engine with synthetic requests, never a model or device."""
import argparse
import json
from pathlib import Path

from capture_lingxi import firmware_profile, firmware_replay

ROOT = Path(__file__).resolve().parents[1]


def check(executable):
    corpus = json.loads((ROOT/"docs/validation/voice-cases.json").read_bytes())
    assert len(corpus["cases"]) == 80 and {c["id"] for c in corpus["cases"]} == {f"V{i:03d}" for i in range(1,81)}
    for case in corpus["cases"]:
        profile = firmware_profile(case["context"])
        calls = [dict(call, elapsed_ms=(index+1)*500, rpc_id=index+1)
                 for index, call in enumerate(case["expected_calls"])]
        if case["category"] == "stop":
            calls.append(dict(inspect_ms=60000))
        rows = firmware_replay(executable, profile, calls)
        for wire in rows[:-1]:
            assert "result" in wire, (case["id"], wire)
            receipt = json.loads(wire["result"]["content"][0]["text"])
            assert receipt["result"] in ("accepted", "ok"), (case["id"], receipt)
        final = rows[-1]
        assert final["distance"]["valid"] and final["distance"]["distance_mm"] == 600
        if case["category"] == "stop":
            assert not any(final["logical_outputs"].values()) and final["starts_this_boot"] == 1
        if not case["expected_calls"]:
            assert final["starts_this_boot"] == 0

    compose = json.loads((ROOT/"docs/validation/compose-cases.json").read_bytes())
    assert len(compose["cases"]) == 8 and {c["id"] for c in compose["cases"]} == {f"C{i:03d}" for i in range(1,9)}
    for case in compose["cases"]:
        calls = [dict(call, elapsed_ms=(index+1)*500, rpc_id=index+1)
                 for index, call in enumerate(case["expected_calls"])]
        rows = firmware_replay(executable, firmware_profile(case["context"]),
                               [*calls, dict(inspect_ms=6000)])
        assert all("result" in wire for wire in rows[:-1])
        final = rows[-1]
        draft = final["show_draft"]
        expected_revision = {"C001":1,"C002":8,"C003":8,"C004":0}.get(case["id"],7)
        assert draft["revision"] == expected_revision, (case["id"], draft)
        assert final["starts_this_boot"] == 0 and not any(final["logical_outputs"].values())
        if case["id"] == "C002":
            assert draft["steps"][0]["move_ms"] == 880 and draft["steps"][1]["bubbles_ms"] == 2000
        if case["id"] == "C003":
            assert len(draft["steps"]) == 1 and draft["steps"][0]["bubbles_ms"] == 1000
    edit = next(case for case in compose["cases"] if case["id"] == "C002")
    calls = [dict(call, elapsed_ms=(index+1)*500, rpc_id=index+1)
             for index, call in enumerate(edit["expected_calls"])]
    no_read = firmware_replay(executable, "corpus_draft7", [
        dict(edit["expected_calls"][1], elapsed_ms=500, rpc_id=1)])
    assert json.loads(no_read[0]["result"]["content"][0]["text"])["result"] == "draft_changed"
    assert no_read[-1]["show_draft"]["revision"] == 7
    rows = firmware_replay(executable, "corpus_draft7_conflict", [*calls, dict(inspect_ms=60000)])
    rejected = json.loads(rows[1]["result"]["content"][0]["text"])
    assert rejected["result"] == "draft_changed"
    assert rows[-1]["show_draft"]["revision"] == 8
    assert rows[-1]["show_draft"]["steps"][1]["bubbles_ms"] == 3000
    assert rows[-1]["starts_this_boot"] == 0

    invalid = [
        dict(name="self.tank.bubbles", arguments={"duration_ms":60000}),
        dict(name="self.tank.water", arguments={"duration_ms":True}),
        dict(name="self.tank.move", arguments={"direction":"forward","duration_ms":1000,"_ct_ticket":1}),
        dict(name="self.tank.sequence", arguments={"steps_json":"[]"}),
        dict(name="self.tank.unknown", arguments={}),
    ]
    for call in invalid:
        wire, final = firmware_replay(executable, "corpus_idle", [dict(call,elapsed_ms=0,rpc_id=1)])
        assert "error" in wire and final["starts_this_boot"] == 0
        assert not any(final["logical_outputs"].values())
    calls = [
        dict(name="self.tank.water",arguments={"duration_ms":1000},elapsed_ms=0,rpc_id=17),
        dict(name="self.tank.water",arguments={"duration_ms":1000},elapsed_ms=50,rpc_id=17),
    ]
    first, duplicate, final = firmware_replay(executable, "corpus_idle", calls)
    assert "result" in first and "error" in duplicate
    assert final["starts_this_boot"] == 1 and final["water_remaining_ms"] == 950
    wire, final = firmware_replay(executable, "corpus_forward70", [
        dict(name="self.tank.stop",arguments={"unexpected":True},elapsed_ms=0,rpc_id=1)])
    assert "error" in wire and final["move_speed_percent"] == 70
    return dict(scope="Synthetic protocol requests, virtual timing and simulated range; no model or board IO",
                expected_traces=80, compose_traces=8, concurrent_edit_rejected=True, invalid_requests=len(invalid), duplicate_id_did_not_restart=True,
                invalid_stop_did_not_change_motion=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.executable), indent=2))
