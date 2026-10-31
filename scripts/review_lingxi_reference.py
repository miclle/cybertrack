#!/usr/bin/env python3
"""Verify an extracted reference bundle and reproduce recorded tool-call scores offline."""
import hashlib
import json
from pathlib import Path

from evaluate_voice import evaluate
from review_spoken_cases import review as review_spoken

STT_SPOKEN_SCORE = "docs/validation/evidence/ct62-stt-host/spoken-review.json"
STT_EXPERIMENT = "docs/validation/evidence/ct62-stt-host/experiment.json"
STT_CAPTURE = "docs/validation/evidence/ct62-stt-host/full20.json.gz"


def score_spoken_replay(trace, recorded):
    if trace.get("host_input_mode") != "platform_stt_events" or trace.get("fixture_version") != "firmware_host":
        raise ValueError("STT speech replay requires observed input events")
    report = review_spoken(trace)
    if report != recorded:
        raise ValueError("STT speech replay differs from recorded review")
    return {key: value for key, value in report.items() if key != "results"}

ROOT = Path(__file__).resolve().parents[1]
SCORES = "docs/validation/evidence/role-5991/full-suite-scores.json"
SUITES = ("voice", "compose")
CANDIDATE_SCORES = "docs/validation/evidence/ct57-full/full-suite-scores.json"
FIRMWARE_HOST_SCORES = "docs/validation/evidence/ct61-firmware-host/full-suite-scores.json"
QWEN_MODEL_SCORES = "docs/validation/evidence/model-qwen/full-suite-scores.json"
DOUBAO_MODEL_SCORES = "docs/validation/evidence/model-doubao/suite-scores.json"
COMPACT_RECEIPT_SCORES = "docs/validation/evidence/compact-model-receipts/full-suite-scores.json"
STOP_NEGATION_SCORES = "docs/validation/evidence/stop-negation/full-suite-scores.json"
EVALUATIONS = (
    ("", SCORES, SUITES, "scores"),
    ("ct57/", CANDIDATE_SCORES, SUITES, "candidate_scores"),
    ("firmware-host/", FIRMWARE_HOST_SCORES, SUITES, "firmware_host_scores"),
    ("qwen/", QWEN_MODEL_SCORES, SUITES, "qwen_scores"),
    ("doubao/", DOUBAO_MODEL_SCORES, ("compose",), "doubao_compose_scores"),
    ("compact-receipts/", COMPACT_RECEIPT_SCORES, ("compose",), "compact_receipt_scores"),
    ("stop-negation/", STOP_NEGATION_SCORES, SUITES, "stop_negation_scores"),
)


def score_replay(suite, corpus, trace, recorded):
    if hashlib.sha256(corpus).hexdigest() != trace["corpus_sha256"]:
        raise ValueError(f"{suite}: corpus differs from captured evaluation")
    report = evaluate(json.loads(corpus), trace)
    report["mismatch_ids"] = [row["id"] for row in report["results"] if not row["tool_calls_match"]]
    for key in ("corpus_suite", "run_id", "role_sha256", "model", "total", "scored", "correct", "mismatch_ids",
                "failed_stop_cases", "forbidden_call_cases", "missing", "incomplete", "tool_call_target_met"):
        if report[key] != recorded[key]:
            raise ValueError(f"{suite}: recomputed {key} differs from recorded score")
    if report["invalid_tool_argument_cases"] != recorded.get("invalid_tool_argument_cases", []):
        raise ValueError(f"{suite}: invalid argument cases differ from recorded score")
    return {**{key: report[key] for key in ("model", "scored", "total", "correct", "mismatch_ids", "incomplete", "missing",
                                          "failed_stop_cases", "forbidden_call_cases", "invalid_tool_argument_cases",
                                          "tool_call_target_met", "role_sha256")},
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

    groups = {}
    for prefix, score_path, suites, name in EVALUATIONS:
        recorded = json.loads((root / score_path).read_bytes())
        results = {}
        for suite in suites:
            corpus = (root / f"docs/validation/{suite}-cases.json").read_bytes()
            trace = json.loads((root / f"replay/{prefix}{suite}.json").read_bytes())
            if prefix:
                for key in ("tool_schema_sha256", "input_mode", "fixture_version"):
                    if trace[key] != recorded[suite][key]:
                        raise ValueError(f"{prefix}{suite}: recorded {key} differs")
                if "host_replay_sha256" in recorded[suite]:
                    if trace["host_replay_sha256"] != recorded[suite]["host_replay_sha256"]:
                        raise ValueError(f"{prefix}{suite}: host implementation differs")
            results[suite] = score_replay(suite, corpus, trace, recorded[suite])
            if prefix:
                results[suite]["tool_source_version"] = recorded[suite]["tool_source_version"]
                results[suite]["input_mode"] = trace["input_mode"]
        groups[name] = results
    spoken = score_spoken_replay(json.loads((root / "replay/stt/voice.json").read_bytes()),
                                  json.loads((root / STT_SPOKEN_SCORE).read_bytes()))
    return {"git_head": manifest["git_head"], "firmware": manifest["firmware"], **groups, "spoken_stt_review": spoken}


if __name__ == "__main__":
    try:
        print(json.dumps(review(ROOT), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError) as error:
        raise SystemExit(str(error)) from None
