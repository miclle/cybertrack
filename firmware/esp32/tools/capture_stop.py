"""Record two BOOT presses/releases followed by a user RST; requires pyserial."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time

import serial


def validate(text):
    boots = text.split("CyberTrack no-load boot version=")[1:]
    if len(boots) != 2:
        return False
    expected = [
        "PSRAM heap_integrity=PASS",
        "VALIDATION PASS state=DISARMED capabilities=0 logical_outputs_off=1",
        "BOOT_STOP READY gpio=0 active_low=1 poll_ms=10 release_debounce_ms=30 held=0",
    ] + [f"PSRAM pattern={i} PASS" for i in range(6)]
    if not all(marker in boot for boot in boots for marker in expected):
        return False
    events = re.findall(r"BOOT_STOP (PRESSED|RELEASED) presses=(\d+)", boots[0])
    if events != [("PRESSED", "1"), ("RELEASED", "1"), ("PRESSED", "2"), ("RELEASED", "2")]:
        return False
    for count in (1, 2):
        if f"state=FAULT held=0 presses={count} logical_outputs_off=1" not in boots[0]:
            return False
    return (
        "HEARTBEAT ticks=1000 state=DISARMED held=0 presses=0 logical_outputs_off=1" in boots[1]
        and "BOOT_STOP PRESSED" not in boots[1]
        and not re.search(r"FAIL|Guru Meditation|panic|abort\(\)|Brownout|Task watchdog got triggered", text)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    lines = []
    boots = 0
    started = datetime.now(timezone.utc).isoformat()
    with (args.output / "boot-stop.log").open("w") as log:
        with serial.Serial(port=None, baudrate=115200, timeout=1) as connection:
            connection.dtr = False
            connection.rts = False
            connection.port = args.port
            connection.open()
            connection.rts = True
            time.sleep(0.1)
            connection.reset_input_buffer()
            connection.rts = False
            deadline = time.monotonic() + 1200
            while time.monotonic() < deadline:
                line = connection.readline().decode("utf-8", errors="replace").rstrip()
                if not line:
                    continue
                line = re.sub(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b", "[MAC redacted]", line)
                lines.append(line)
                log.write(line + "\n")
                log.flush()
                if "CyberTrack no-load boot version=" in line:
                    boots += 1
                if "board_check:" in line and ("HEARTBEAT" not in line or "ticks=1000 " in line):
                    print(line, flush=True)
                if boots >= 2 and "HEARTBEAT ticks=1000 " in line:
                    break
                if re.search(r"FAIL|Guru Meditation|panic|abort\(\)|Brownout", line):
                    break
    passed = validate("\n".join(lines))
    result = {"passed": passed, "boots": boots, "started_utc": started,
              "finished_utc": datetime.now(timezone.utc).isoformat(), "log": "boot-stop.log"}
    (args.output / "capture-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
