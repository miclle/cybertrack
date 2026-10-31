#!/usr/bin/env python3
"""Verify an extracted reference bundle and reproduce its two tool-call scores offline."""
import hashlib
import json
from pathlib import Path

from evaluate_voice import evaluate

ROOT = Path(__file__).resolve().parents[1]
SCORES = "docs/validation/evidence/role-5991/full-suite-scores.json"
SUITES = ("voice", "compose")


def score_replay(suite, corpus, trace, recorded):
    if hashlib.sha256(corpus).hexdigest() != trace["corpus_sha256"]:
        raise ValueError(f"{suite}: corpus differs from captured evaluation")
    report = evaluate(json.loads(corpus), trace)
    report["mismatch_ids"] = [row["id"] for row in report["results"] if not row["tool_calls_match"]]
    for key in ("corpus_suite", "run_id", "role_sha256", "model", "total", "scored", "correct", "mismatch_ids",
                "failed_stop_cases", "forbidden_call_cases", "missing", "incomplete", "tool_call_target_met"):
        if report[key] != recorded[key]:
            raise ValueError(f"{suite}: recomputed {key} differs from recorded score")
    return {**{key: report[key] for key in ("scored", "correct", "mismatch_ids", "tool_call_target_met", "role_sha256")},
            "fixture_version": trace["fixture_version"]}


def review(root):
    manifest = json.loads((root / "MANIFEST.json").read_bytes())
    for name, expected in manifest["files"].items():
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()) or path.resolve() != path.absolute():
            raise ValueError(f"invalid bundle path: {name}")
        data = path.read_bytes()
        if len(data) != expected["bytes"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
            raise ValueError(f"bundle file differs from manifest: {name}")

    recorded = json.loads((root / SCORES).read_bytes())
    results = {}
    for suite in SUITES:
        corpus = (root / f"docs/validation/{suite}-cases.json").read_bytes()
        trace = json.loads((root / f"replay/{suite}.json").read_bytes())
        results[suite] = score_replay(suite, corpus, trace, recorded[suite])
    return {"git_head": manifest["git_head"], "firmware": manifest["firmware"], "scores": results}


if __name__ == "__main__":
    try:
        print(json.dumps(review(ROOT), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError) as error:
        raise SystemExit(str(error)) from None
