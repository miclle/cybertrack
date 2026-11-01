#!/usr/bin/env python3
"""Verify retired interfaces and non-execution requests with actual MCP; no IO."""
import argparse
import json
from pathlib import Path
import subprocess

from capture_lingxi import firmware_replay


def check(executable):
    catalog = json.loads(subprocess.check_output([executable, "--catalog"], text=True))
    names = {tool["name"] for tool in catalog}
    assert len(names) == 11 and "self.tank.compose" not in names
    assert {"self.tank.sequence", "self.tank.move_and_water", "self.tank.stop"} <= names

    def call(name, args=None, ms=10, rpc=1, **extra):
        return dict(name="self.tank." + name, arguments=args or {}, elapsed_ms=ms, rpc_id=rpc, **extra)

    def result(wire):
        return json.loads(wire["result"]["content"][0]["text"])["result"]

    plan = dict(steps_json=json.dumps([
        dict(direction="left", move_ms=880, water_ms=0, bubbles_ms=1000, ignition_ms=0),
        dict(direction="none", move_ms=0, water_ms=500, bubbles_ms=0, ignition_ms=0)]))
    count = 0
    for phrase in ("先前进两秒，再吹泡泡三秒，先别执行", "只预览前进一秒", "帮我编排泡泡表演",
                   "修改表演，第二步左转", "只讨论怎么喷水", "先别动，左转一秒"):
        for tool, args in (("sequence", plan), ("move", dict(direction="forward", duration_ms=1000)),
                           ("water", dict(duration_ms=1000)), ("bubbles", dict(duration_ms=1000)),
                           ("ignition", dict(duration_ms=1000)), ("frenzy", dict(duration_ms=1000))):
            rows = firmware_replay(executable, "corpus_idle", [dict(input_text=phrase, elapsed_ms=0),
                call(tool, args), call("water", dict(duration_ms=1000), 20, 2), call("stop", ms=30, rpc=3)], await_stt=True)
            assert result(rows[0]) == "execution_not_requested", (phrase, tool, rows)
            assert "error" in rows[1] and result(rows[2]) == "ok"
            assert rows[-1]["starts_this_boot"] == 0 and not any(rows[-1]["logical_outputs"].values())
            assert "show_draft" not in rows[-1] and "draft_status_facts" not in rows[-1]
            count += 1
    for tool, args in (("set_speed", dict(speed_percent=100)), ("adjust_speed", dict(delta_percent=10))):
        rows = firmware_replay(executable, "corpus_forward70", [dict(input_text="只预览，先别执行", elapsed_ms=0),
            call(tool, args), call("stop", ms=20, rpc=2, defer=True), dict(inspect_ms=60000)], await_stt=True)
        assert result(rows[0]) == "execution_not_requested" and result(rows[1]) == "ok"
        assert rows[-1]["starts_this_boot"] == 1 and not any(rows[-1]["logical_outputs"].values())
        count += 1
    for ms in (10, 30010):
        rows = firmware_replay(executable, "corpus_sequence", [dict(input_text="先别执行", elapsed_ms=ms),
            call("stop", ms=ms+1, defer=True), dict(inspect_ms=60000)], await_stt=True)
        assert result(rows[0]) == "ok" and not rows[-1]["sequence_active"]
        assert rows[-1]["starts_this_boot"] == 1 and not any(rows[-1]["logical_outputs"].values())
        count += 1
    rows = firmware_replay(executable, "corpus_idle", [call("compose", dict(edit="cancel", revision=0, step=0, steps_json="")),
        call("sequence", plan, 20, 2), dict(input_text="左转并吹泡泡，再喷水", elapsed_ms=30),
        call("sequence", plan, 40, 3), dict(inspect_ms=6000)])
    assert "error" in rows[0] and "error" in rows[1] and result(rows[2]) == "accepted"
    assert rows[-1]["starts_this_boot"] == 3 and rows[-1]["sequence_result"] == "completed"
    return dict(passed=True, tool_count=len(names), refusal_and_stop_cases=count, retired_tool_rejected=True,
                new_input_recovers=True, concurrent_then_sequential_completed=True,
                scope="Actual MCP/guards with synthetic recognized text and virtual clock; no model, device or physical acceptance")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = check(args.executable)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))
