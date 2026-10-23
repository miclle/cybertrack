"""Capture repeatable no-load checks; requires pyserial and the board-check image."""

import argparse
import json
from pathlib import Path
import re
import time

import serial


def capture(port, output, run):
    lines = []
    with serial.Serial(port=None, baudrate=115200, timeout=1) as connection:
        connection.dtr = False
        connection.rts = False
        connection.port = port
        connection.open()
        connection.rts = True
        time.sleep(0.1)
        connection.reset_input_buffer()
        connection.rts = False
        deadline = time.monotonic() + 100
        while time.monotonic() < deadline:
            line = connection.readline().decode("utf-8", errors="replace").rstrip()
            if not line:
                continue
            line = re.sub(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b", "[MAC redacted]", line)
            lines.append(line)
            if "HEARTBEAT ticks=6000 state=DISARMED held=0 presses=0 logical_outputs_off=1" in line:
                break
    output.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    (output / f"boot-{run}.log").write_text(text)
    required = [
        "PSRAM initialized=1 detected_bytes=8388608",
        "PSRAM test_bytes=6291456 patterns=6",
        "PSRAM heap_integrity=PASS",
        "VALIDATION PASS state=DISARMED capabilities=0 logical_outputs_off=1",
        "HEARTBEAT ticks=6000 state=DISARMED held=0 presses=0 logical_outputs_off=1",
    ] + [f"PSRAM pattern={index} PASS" for index in range(6)]
    passed = (
        all(marker in text for marker in required)
        and text.count("CyberTrack no-load boot version=") == 1
        and text.count("VALIDATION PASS") == 1
        and not re.search(r"FAIL|Guru Meditation|panic|abort\(\)|Brownout|Task watchdog got triggered", text)
    )
    result = {"run": run, "passed": passed, "log": f"boot-{run}.log"}
    print(json.dumps(result), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = []
    for run in range(1, 4):
        result = capture(args.port, args.output, run)
        results.append(result)
        if not result["passed"]:
            break
    (args.output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    raise SystemExit(0 if len(results) == 3 and all(item["passed"] for item in results) else 1)


if __name__ == "__main__":
    main()
