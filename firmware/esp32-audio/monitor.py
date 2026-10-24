#!/usr/bin/env python3
"""Read-only serial observer: save tool receipts/state, not audio or raw logs."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import serial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.log.parent.mkdir(parents=True, exist_ok=True)
    device = serial.Serial(port=None, baudrate=115200, timeout=.2, exclusive=True)
    device.dtr = False
    device.rts = False
    device.port = args.port
    device.open()
    pending = bytearray()
    try:
        with args.log.open("a", buffering=1) as log:
            def report(event):
                stamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
                record = json.dumps({"time": stamp, **event}, ensure_ascii=False)
                print(record, flush=True)
                log.write(record + "\n")
            report({"observer": "opened; no serial application commands"})
            while True:
                pending.extend(device.read(device.in_waiting or 1))
                while b"\n" in pending:
                    raw, _, pending = pending.partition(b"\n")
                    line = re.sub(r"\x1b\[[0-9;]*m", "", raw.decode(errors="replace"))
                    marker = re.search(r"CT_AUDIO: (.+)", line)
                    if marker:
                        report({"cybertrack": marker[1]})
                    state = re.search(r"Application: STATE: ([a-z_]+)", line)
                    if state:
                        report({"application_state": state[1]})
                    version = re.search(r"app_init: App version:\s+([a-zA-Z0-9_.+-]+)", line)
                    if version:
                        report({"firmware": version[1]})
                    if "got ip:" in line.lower():
                        report({"network": "IP acquired; address withheld"})
                    if "SSD1306 driver installed" in line:
                        report({"display": "SSD1306 driver installed"})
                    if "Guru Meditation" in line or "Stack overflow" in line:
                        report({"error": line.strip()})
                    if "Backtrace:" in line:
                        report({"backtrace": re.findall(r"0x[0-9a-fA-F]+", line)})
                    if "Stack canary" in line or "assert failed:" in line:
                        report({"diagnostic": line.strip()})
                if len(pending) > 16384:
                    pending.clear()
    except KeyboardInterrupt:
        pass
    finally:
        device.close()


if __name__ == "__main__":
    main()
