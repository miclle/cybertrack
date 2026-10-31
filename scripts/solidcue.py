#!/usr/bin/env python3
"""Prepare or run the CyberTrack model design service in CyberTrack-owned data."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def configuration():
    lock = json.loads((ROOT / "tools/solidcue/lock.json").read_text())
    source = ROOT / lock["source_directory"]
    data = ROOT / lock["data_directory"]
    return lock, source, data


def verified_source(lock, source):
    if lock.get("source_mode") == "vendored":
        provenance = json.loads((source / "UPSTREAM.json").read_text())
        if provenance["revision"] != lock["revision"] or not (source / "LICENSE").is_file():
            raise ValueError("Vendored source provenance or license missing")
        return
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=source, text=True)
    if revision != lock["revision"] or dirty:
        raise ValueError("SolidCue checkout differs from lock or has local changes; preserve it and inspect manually")


def environment(data):
    env = os.environ.copy()
    for key in ("CODEX_THREAD_ID", "CAD_CHAT_THREAD_ID"):
        env.pop(key, None)
    env.update(CAD_COMMENT_INITIAL_MODEL="blank", CAD_COMMENT_DATA_DIR=str(data),
               CAD_COMMENT_CAD_INBOX=str(data / "cad-inbox"),
               CAD_COMMENT_EXPORT_DIR=str(data.parent / "exports"), CAD_COMMENT_PORT="9473")
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "check", "start"))
    args = parser.parse_args()
    lock, source, data = configuration()
    if args.command == "prepare" and not source.exists() and lock.get("source_mode") != "vendored":
        source.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--no-checkout", lock["repository"], str(source)], check=True)
        subprocess.run(["git", "checkout", "--detach", lock["revision"]], cwd=source, check=True)
    verified_source(lock, source)
    if args.command == "prepare":
        for command in (["npm", "ci"], ["uv", "venv", "--python", "3.12", ".venv"],
                        ["uv", "pip", "install", "--python", ".venv/bin/python", "-r", "requirements-lock.txt"],
                        [".venv/bin/python", "-c", "import cadquery; print(cadquery.__version__)"],
                        ["npm", "run", "build:plugin"]):
            # Do not replace a configured Python environment on subsequent prepares.
            if command[:2] == ["uv", "venv"] and (source / ".venv/bin/python").exists():
                continue
            subprocess.run(command, cwd=source, check=True)
    elif args.command == "start":
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", lock["port"]))
            except OSError as exc:
                raise SystemExit("Port 9473 is occupied; no service was stopped or replaced") from exc
        if not (source / "dist/server.js").is_file():
            raise SystemExit("Run prepare first")
        data.mkdir(parents=True, exist_ok=True)
        os.execvpe("node", ["node", str(source / "dist/server.js")], environment(data))
    else:
        print(json.dumps({"revision": lock["revision"], "source": str(source),
                          "data": str(data), "bridge": str(source / "freecad_bridge.py"),
                          "built": (source / "dist/server.js").is_file(),
                          "note": "checkout check, not service or desktop acceptance"}, indent=2))


if __name__ == "__main__":
    main()
