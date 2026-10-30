#!/usr/bin/env python3
"""Record live engineering changes and evidence without estimating missing effort."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRECTORY = ROOT / "output/engineering"
EFFORT_FIELDS = ("human_minutes", "model_wait_minutes", "revision_rounds", "failed_checks", "regressions_found")


def now() -> str:
    """Use an aware UTC timestamp at the time the command actually runs."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def parse_time(value: str) -> datetime:
    """Require an explicit timezone; local wall-clock strings are ambiguous."""
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return result


def git(*args: str, root: Path = ROOT) -> str:
    """Read repository state without changing it."""
    return subprocess.check_output(["git", *args], cwd=root, text=True, stderr=subprocess.PIPE).strip()


def identifier(value: str) -> str:
    """Keep record IDs portable and confined to one directory."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
        raise ValueError("id must be 1..64 lowercase letters, digits, underscores or hyphens")
    return value


def write_new(path: Path, data: dict) -> None:
    """Never replace a previous start or finish record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with path.open("x") as stream:
        stream.write(payload)


def start(directory: Path, record_id: str, summary: str, root: Path = ROOT) -> Path:
    """Start live recording; do not infer the beginning of prior unrecorded work."""
    identifier(record_id)
    if not summary.strip():
        raise ValueError("summary is required")
    path = directory / f"{record_id}.start.json"
    if (directory / f"{record_id}.finish.json").exists():
        raise ValueError("finished record ID cannot be reused")
    write_new(path, {"schema_version": 1, "kind": "engineering_change_start", "id": record_id,
                     "summary": summary, "recording_started_at": now(),
                     "base_commit": git("rev-parse", "HEAD", root=root),
                     "worktree_was_dirty": bool(git("status", "--porcelain", root=root))})
    return path


def validate_effort(effort: dict) -> None:
    """Keep unknown values explicit and reject ambiguous numeric coercions."""
    if set(effort) != set(EFFORT_FIELDS):
        raise ValueError("effort fields do not match the recording contract")
    for key, value in effort.items():
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"{key}: finite nonnegative number or null required")
        if key.endswith("rounds") or key in ("failed_checks", "regressions_found"):
            if type(value) is not int:
                raise ValueError(f"{key}: integer required")


def finish(directory: Path, record_id: str, commit: str, evidence: list[Path], effort: dict,
           root: Path = ROOT) -> Path:
    """Bind a live interval to a new commit and hash existing validation artifacts."""
    identifier(record_id)
    validate_effort(effort)
    source = directory / f"{record_id}.start.json"
    raw = source.read_bytes()
    opened = json.loads(raw)
    if opened.get("kind") != "engineering_change_start" or opened.get("schema_version") != 1 or opened.get("id") != record_id:
        raise ValueError("start record mismatch")
    if not re.fullmatch(r"[a-fA-F0-9]{7,40}", commit):
        raise ValueError("commit must be an explicit commit hash, not a moving ref")
    resolved = git("rev-parse", "--verify", f"{commit}^{{commit}}", root=root)
    if resolved == opened["base_commit"]:
        raise ValueError("finish requires a new commit after recording began")
    for existing in directory.glob("*.finish.json"):
        if existing.name != f"{record_id}.finish.json" and json.loads(existing.read_bytes()).get("commit") == resolved:
            raise ValueError("commit already belongs to another change record")
    subprocess.run(["git", "merge-base", "--is-ancestor", opened["base_commit"], resolved],
                   cwd=root, check=True, capture_output=True)
    if not evidence:
        raise ValueError("at least one existing validation artifact is required")
    artifacts, seen = [], set()
    for path in evidence:
        resolved_path = path.resolve()
        relative = resolved_path.relative_to(root.resolve()).as_posix()
        if any(part in {"secrets", ".git", ".env", "recordings"} for part in Path(relative).parts):
            raise ValueError("sensitive evidence path is not allowed")
        if relative in seen:
            raise ValueError("duplicate evidence path")
        seen.add(relative)
        content = resolved_path.read_bytes()
        artifacts.append({"path": relative, "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)})
    ended = now()
    elapsed = (parse_time(ended)-parse_time(opened["recording_started_at"])).total_seconds()
    if elapsed < 0:
        raise ValueError("clock moved backwards; interval cannot be reported")
    path = directory / f"{record_id}.finish.json"
    write_new(path, {"schema_version": 1, "kind": "engineering_change_finish", "id": record_id,
                     "start_sha256": hashlib.sha256(raw).hexdigest(), "recording_finished_at": ended,
                     "recorded_elapsed_seconds": elapsed, "commit": resolved, "evidence": artifacts,
                     "reported_effort": effort})
    return path


def report(directory: Path, root: Path = ROOT) -> dict:
    """List observations and missing effort without fabricating a speedup ratio."""
    changes, ids, commits, complete = [], set(), set(), 0
    for path in sorted(directory.glob("*.start.json")):
        raw = path.read_bytes()
        opened = json.loads(raw)
        record_id = identifier(opened["id"])
        if path.name != f"{record_id}.start.json" or opened.get("kind") != "engineering_change_start" or opened.get("schema_version") != 1:
            raise ValueError("invalid start record")
        ids.add(record_id)
        parse_time(opened["recording_started_at"])
        closed_path = directory / f"{record_id}.finish.json"
        item = {"start": opened, "finish": None, "missing": ["finish record"]}
        if closed_path.exists():
            closed = json.loads(closed_path.read_bytes())
            if closed.get("kind") != "engineering_change_finish" or closed.get("schema_version") != 1 or closed.get("id") != record_id:
                raise ValueError("invalid finish record")
            if closed.get("start_sha256") != hashlib.sha256(raw).hexdigest():
                raise ValueError("start record changed after finish")
            elapsed = (parse_time(closed["recording_finished_at"])-parse_time(opened["recording_started_at"])).total_seconds()
            if elapsed < 0 or type(closed["recorded_elapsed_seconds"]) not in (float, int) or elapsed != closed["recorded_elapsed_seconds"]:
                raise ValueError("recorded interval mismatch")
            validate_effort(closed["reported_effort"])
            missing = [key for key, value in closed["reported_effort"].items() if value is None]
            if not isinstance(closed.get("commit"), str) or not re.fullmatch(r"[a-f0-9]{40}", closed["commit"]):
                raise ValueError("finish must contain a full commit hash")
            if closed["commit"] in commits:
                raise ValueError("duplicate commit across change records")
            commits.add(closed["commit"])
            git("cat-file", "-e", f"{closed['commit']}^{{commit}}", root=root)
            if closed["commit"] == opened["base_commit"]:
                raise ValueError("finish must reference a new commit")
            subprocess.run(["git", "merge-base", "--is-ancestor", opened["base_commit"], closed["commit"]],
                           cwd=root, check=True, capture_output=True)
            if not closed.get("evidence"):
                missing.append("validation evidence")
            seen_evidence = set()
            for artifact in closed.get("evidence", []):
                artifact_path = (root / artifact["path"]).resolve()
                relative = artifact_path.relative_to(root.resolve()).as_posix()
                if relative != artifact["path"] or relative in seen_evidence:
                    raise ValueError("evidence path must be relative, normalized and unique")
                seen_evidence.add(relative)
                if not artifact_path.is_file():
                    missing.append(f"evidence missing: {relative}")
                elif hashlib.sha256(artifact_path.read_bytes()).hexdigest() != artifact["sha256"]:
                    missing.append(f"evidence changed: {relative}")
            if not missing:
                complete += 1
            item.update(finish=closed, missing=missing)
        changes.append(item)
    for path in directory.glob("*.finish.json"):
        if path.name.removesuffix(".finish.json") not in ids:
            raise ValueError("orphan finish record")
    return {"schema_version": 1, "changes": changes, "complete_records": complete,
            "target_records": 5, "additional_complete_records_needed": max(0, 5-complete),
            "efficiency_improvement": "not_established",
            "limitations": ["elapsed time starts at instrumentation, not at an inferred task beginning",
                           "human time, model wait and rework counts are separately reported observations",
                           "evidence hashes identify files; they do not prove that the recorded checks passed",
                           "no matched non-AI baseline, no causal speedup or quality claim",
                           "repository truth and artifact contents require independent review"]}


def main() -> None:
    """Operate only on local records and read-only Git queries."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("start")
    create.add_argument("id")
    create.add_argument("--summary", required=True)
    close = commands.add_parser("finish")
    close.add_argument("id")
    close.add_argument("--commit", required=True)
    close.add_argument("--evidence", type=Path, action="append", required=True)
    for key in EFFORT_FIELDS:
        close.add_argument("--"+key.replace("_", "-"), type=float if key.endswith("minutes") else int)
    commands.add_parser("report")
    args = parser.parse_args()
    try:
        if args.command == "start":
            print(start(args.directory, args.id, args.summary))
        elif args.command == "finish":
            print(finish(args.directory, args.id, args.commit, args.evidence,
                         {key: getattr(args, key) for key in EFFORT_FIELDS}))
        else:
            print(json.dumps(report(args.directory), ensure_ascii=False, indent=2, allow_nan=False))
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
