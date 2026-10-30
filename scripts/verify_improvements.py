#!/usr/bin/env python3
"""Run bounded local checks and retain evidence; never flash or contact a device."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="prepared xiaozhi source for actual overlay/MCP/audio checks")
    parser.add_argument("--output", type=Path, default=ROOT / "output/improvements/checks")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = args.output.resolve() / stamp
    out.mkdir(parents=True, exist_ok=False)
    commands = [[sys.executable, "scripts/check_firmware_current.py"],
                ["git", "diff", "--check"], ["sh", "firmware/esp32-audio/test.sh"]]
    if (ROOT / "tests/improvements").exists():
        commands.append([sys.executable, "-m", "unittest", "discover", "-s", "tests/improvements"])
    if args.source:
        source = args.source.resolve()
        if not (source / "main/audio/audio_service.cc").is_file():
            parser.error("--source must be a prepared xiaozhi tree; no download or regeneration is implicit")
        for suite in ("run_mcp_tests.py", "run_audio_tests.py"):
            commands.append([sys.executable, f"firmware/esp32-audio/tests/{suite}", "--source", str(source)])
    report = {"scope": "local software checks only", "created_utc": stamp,
              "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "git_status": subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True),
              "source_sha256": {}, "checks": [],
              "excluded": ["firmware build", "deployment", "online model evaluation", "human voice", "physical acceptance"]}
    for prefix in ("firmware/esp32-audio", "scripts", "tests/improvements"):
        for path in sorted((ROOT / prefix).rglob("*")):
            if path.is_file() and path.suffix in (".py", ".cc", ".h", ".html", ".mjs", ".sh", ".txt", ".json") and "__pycache__" not in path.parts:
                report["source_sha256"][str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    for i, command in enumerate(commands):
        print("Running:", " ".join(command), flush=True)
        log = out / f"{i:02d}.log"
        try:
            with log.open("w") as stream:
                result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=300)
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = 124
        report["checks"].append({"command": command, "exit_code": code, "log": log.name})
    report["passed"] = all(item["exit_code"] == 0 for item in report["checks"])
    report["prepared_source_checked"] = bool(args.source)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(out / "report.json", flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
