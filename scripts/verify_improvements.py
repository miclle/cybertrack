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
    parser.add_argument("--model-design", action="store_true", help="include prepared model-design tests, plugin bundle and synthetic UI; no installation")
    parser.add_argument("--output", type=Path, default=ROOT / "output/improvements/checks")
    args = parser.parse_args()
    if args.source and not (args.source.resolve() / "main/audio/audio_service.cc").is_file():
        parser.error("--source must be a prepared xiaozhi tree; no download or regeneration is implicit")
    if args.model_design:
        model_root = ROOT / "tools/model-design"
        required = [model_root / "node_modules/.bin/tsc", model_root / ".venv/bin/python"]
        if not all(path.is_file() for path in required):
            parser.error("--model-design requires prepared dependencies; run python3 scripts/solidcue.py prepare first")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = args.output.resolve() / stamp
    out.mkdir(parents=True, exist_ok=False)
    commands = [[sys.executable, "scripts/check_firmware_current.py"],
                ["git", "diff", "--check"], ["sh", "firmware/esp32-audio/test.sh"],
                ["node", "firmware/esp32-audio/tests/web_ui_test.mjs"]]
    if (ROOT / "tests/improvements").exists():
        commands.append([sys.executable, "-m", "unittest", "discover", "-s", "tests/improvements"])
    if args.source:
        source = args.source.resolve()
        commands.append([sys.executable, "scripts/replay_stop_matrix.py", "--source", str(source)])
        for suite in ("run_mcp_tests.py", "run_audio_tests.py"):
            commands.append([sys.executable, f"firmware/esp32-audio/tests/{suite}", "--source", str(source)])
    if args.model_design:
        commands.extend([["npm", "--prefix", "tools/model-design", "test"],
                         ["npm", "--prefix", "tools/model-design", "run", "test:bundle"],
                         ["npm", "--prefix", "tools/model-design", "run", "test:ui"]])
    report = {"scope": "local software checks only", "created_utc": stamp,
              "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "git_status": subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True),
              "source_sha256": {}, "checks": [],
              "excluded": ["firmware build", "deployment", "online model evaluation", "human voice", "physical acceptance", "native desktop host message delivery", "FreeCAD GUI MCP edits"]}
    for prefix in ("firmware/esp32-audio", "scripts", "tests/improvements"):
        for path in sorted((ROOT / prefix).rglob("*")):
            if path.is_file() and path.suffix in (".py", ".cc", ".h", ".html", ".mjs", ".sh", ".txt", ".json") and "__pycache__" not in path.parts:
                report["source_sha256"][str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    if args.model_design:
        # Respect repository ignores: dependency trees, study data and generated
        # bundles are not source inputs. Include new source files before commit.
        names = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard",
                                         "-z", "--", "tools/model-design"], cwd=ROOT).decode().split("\0")
        for name in sorted(set(filter(None, names))):
            path = ROOT / name
            if path.is_file():
                report["source_sha256"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
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
    report["model_design_checked"] = args.model_design
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(out / "report.json", flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
