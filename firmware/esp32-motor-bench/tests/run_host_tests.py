#!/usr/bin/env python3
"""Compile policy and the real board task against a simulated ESP-IDF boundary."""
from pathlib import Path
import subprocess

project = Path(__file__).resolve().parents[1]
root = project.parents[1]
build = root / "build/motor-bench-l298n-host"
build.mkdir(parents=True, exist_ok=True)
headers = build / "idf-stubs"
for header in ("driver/gpio.h", "driver/ledc.h", "driver/uart.h", "esp_task_wdt.h",
               "esp_timer.h", "freertos/FreeRTOS.h", "freertos/task.h"):
    path = headers / header
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('#include "idf_stub.h"\n')
for name in ("policy_test", "adapter_test"):
    binary = build / name
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-fsanitize=address,undefined", "-g",
        "-I", str(project / "main"), "-I", str(project / "tests"), "-I", str(headers),
        str(project / "main/bench_policy.c"), str(project / f"tests/{name}.c"),
        "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
