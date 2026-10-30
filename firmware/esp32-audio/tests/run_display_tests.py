#!/usr/bin/env python3
"""Exercise actual patched OLED methods with in-memory LVGL labels."""
import argparse
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source", required=True, type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[3]
build = root / "build/audio-host"
build.mkdir(parents=True, exist_ok=True)
code = (args.source / "main/display/oled_display.cc").read_text()
methods = []
for signature in ("void OledDisplay::SetLocalAddress(",
                  "void OledDisplay::UpdateLocalAddress(",
                  "void OledDisplay::SetChatMessage("):
    start = code.index(signature)
    end = code.index("\n}", start) + 2
    methods.append(code[start:end])
(build / "display_methods.inc").write_text("\n".join(methods))
subprocess.run([
    "c++", "-std=c++17", "-g", "-fsanitize=address,undefined",
    "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
    "-I", str(build), str(Path(__file__).with_name("display_test.cc")),
    "-o", str(build / "display_test"),
], check=True)
subprocess.run([str(build / "display_test")], check=True)
