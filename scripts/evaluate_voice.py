#!/usr/bin/env python3
"""Score captured tool-call traces against the fixed corpus; no model/device calls."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def canonical(calls):
    if not isinstance(calls, list):
        raise ValueError("calls must be a list")
    normalized = []
    for item in calls:
        if not isinstance(item, dict) or set(item) != {"name", "arguments"}:
            raise ValueError("each call needs exactly name and arguments")
        name, args = item["name"], item["arguments"]
        if not isinstance(name, str) or not isinstance(args, dict):
            raise ValueError("invalid call shape")
        if name.startswith("self_tank_"):
            name = "self.tank." + name[len("self_tank_"):]
        args = dict(args)
        if name in ("self.tank.move", "self.tank.move_and_water"):
            args.setdefault("speed_percent", 100)
        if name == "self.tank.sequence" or (name == "self.tank.compose" and args.get("edit") in ("replace", "replace_step")):
            steps = args.get("steps_json")
            if not isinstance(steps, str):
                raise ValueError("sequence steps_json must be the wire-format JSON string")
            steps = json.loads(steps)
            if not isinstance(steps, list) or not all(isinstance(s, dict) for s in steps):
                raise ValueError("invalid sequence steps")
            for step in steps:
                step.setdefault("speed_percent", 100)
            args["steps_json"] = steps
        normalized.append({"name": name, "arguments": args})
    # JSON preserves bool versus int, unlike Python dict equality.
    return json.dumps(normalized, sort_keys=True, ensure_ascii=False, allow_nan=False)


def evaluate(corpus, trace):
    expected = {c["id"]: c for c in corpus["cases"]}
    suite = corpus.get("suite", "voice-v1")
    suites = {"voice-v1": {f"V{i:03d}" for i in range(1, 81)},
              "compose-v1": {f"C{i:03d}" for i in range(1, 9)}}
    if suite not in suites or len(expected) != len(corpus["cases"]) or set(expected) != suites[suite]:
        raise ValueError("corpus must contain the complete, unique IDs for its fixed suite")
    for key in ("model", "role_sha256", "run_id"):
        if not isinstance(trace.get(key), str) or not trace[key].strip():
            raise ValueError(f"trace needs {key}")
    if trace.get("kind") != "captured_tool_calls":
        raise ValueError("trace kind must explicitly identify captured_tool_calls")
    results, seen, unsafe = [], set(), []
    for result in trace.get("results", []):
        cid = result["id"]
        if cid in seen or cid not in expected:
            raise ValueError("duplicate or unknown case ID: " + cid)
        seen.add(cid)
        calls = result["calls"]
        match = canonical(calls) == canonical(expected[cid]["expected_calls"])
        if expected[cid]["category"] in ("no_action", "clarify"):
            if any(c["name"] not in ("self.tank.get_status", "self_tank_get_status") for c in calls):
                unsafe.append(cid)
        allowed = expected[cid].get("allowed_tools")
        if allowed is not None and any(c["name"].replace("self_tank_", "self.tank.", 1) not in allowed for c in calls):
            if cid not in unsafe:
                unsafe.append(cid)
        results.append({"id": cid, "tool_calls_match": match})
    passed = sum(r["tool_calls_match"] for r in results)
    missing = sorted(set(expected) - seen)
    return {"corpus_suite": suite, "run_id": trace["run_id"], "model": trace["model"], "role_sha256": trace["role_sha256"],
            "scored": len(results), "total": len(expected), "correct": passed,
            "accuracy_all_cases": passed / len(expected), "missing": missing,
            "forbidden_call_cases": unsafe,
            "tool_call_target_met": not missing and not unsafe and passed / len(expected) >= .95,
            "results": results, "reply_semantics": "manual review required",
            "physical_or_spoken_acceptance": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--corpus", type=Path, default=ROOT / "docs/validation/voice-cases.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(json.loads(args.corpus.read_text()), json.loads(args.trace.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False, indent=2))
    return 0 if report["tool_call_target_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
