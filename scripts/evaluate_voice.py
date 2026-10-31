#!/usr/bin/env python3
"""Score captured tool-call traces against the fixed corpus; no model/device calls."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InvalidToolArguments(ValueError):
    """Captured arguments cannot be normalized, but still count as a failure."""


def canonical(calls, *, step_format=None):
    if step_format not in (None,"legacy_string","native_array"):
        raise ValueError("unknown declared step format")
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
        if name in ("self.tank.sequence", "self.tank.compose") and step_format:
            key, expected_type = ("steps",list) if step_format=="native_array" else ("steps_json",str)
            other = "steps_json" if key=="steps" else "steps"
            if other in args or not isinstance(args.get(key),expected_type):
                raise InvalidToolArguments("step arguments do not match the advertised wire schema")
        if name in ("self.tank.sequence", "self.tank.compose") and "steps" in args:
            if "steps_json" in args or not isinstance(args["steps"], list):
                raise InvalidToolArguments("steps must be an array and cannot coexist with steps_json")
            steps = args.pop("steps")
            args["steps_json"] = "" if name == "self.tank.compose" and args.get("edit") in ("cancel", "remove_step") and not steps else json.dumps(steps,ensure_ascii=False)
        if name in ("self.tank.move", "self.tank.move_and_water"):
            args.setdefault("speed_percent", 100)
        if name == "self.tank.sequence" or (name == "self.tank.compose" and args.get("edit") in ("replace", "replace_step")):
            steps = args.get("steps_json")
            if not isinstance(steps, str):
                raise InvalidToolArguments("sequence steps_json must be the wire-format JSON string")
            try:
                steps = json.loads(steps)
            except json.JSONDecodeError as error:
                raise InvalidToolArguments("steps_json is not valid JSON") from error
            if not isinstance(steps, list) or not all(isinstance(s, dict) for s in steps):
                raise InvalidToolArguments("invalid sequence steps")
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
    expected_calls = {cid: canonical(case["expected_calls"]) for cid, case in expected.items()}
    for key in ("model", "role_sha256", "run_id"):
        if not isinstance(trace.get(key), str) or not trace[key].strip():
            raise ValueError(f"trace needs {key}")
    if trace.get("kind") != "captured_tool_calls":
        raise ValueError("trace kind must explicitly identify captured_tool_calls")
    failed_stops = {cid for cid, case in expected.items() if case["category"] == "stop"}
    results, seen, unsafe, incomplete, invalid = [], set(), [], [], []
    for result in trace.get("results", []):
        cid = result["id"]
        if cid in seen or cid not in expected:
            raise ValueError("duplicate or unknown case ID: " + cid)
        seen.add(cid)
        calls = result["calls"]
        completed = result.get("completed", True)
        if not isinstance(completed, bool):
            raise ValueError("completed must be a boolean when provided")
        if not completed:
            incomplete.append(cid)
        argument_error = None
        try:
            actual = canonical(calls,step_format=trace.get("step_argument_format"))
        except InvalidToolArguments as error:
            actual = None
            argument_error = str(error)
            invalid.append(cid)
        match = completed and actual == expected_calls[cid]
        if match:
            failed_stops.discard(cid)
        if expected[cid]["category"] in ("no_action", "clarify"):
            if any(c["name"] not in ("self.tank.get_status", "self_tank_get_status") for c in calls):
                unsafe.append(cid)
        allowed = expected[cid].get("allowed_tools")
        if allowed is not None and any(c["name"].replace("self_tank_", "self.tank.", 1) not in allowed for c in calls):
            if cid not in unsafe:
                unsafe.append(cid)
        row = {"id": cid, "tool_calls_match": match}
        if argument_error:
            row["invalid_tool_arguments"] = argument_error
        results.append(row)
    passed = sum(r["tool_calls_match"] for r in results)
    missing = sorted(set(expected) - seen)
    return {"corpus_suite": suite, "run_id": trace["run_id"], "model": trace["model"], "role_sha256": trace["role_sha256"],
            "scored": len(results), "total": len(expected), "correct": passed,
            "accuracy_all_cases": passed / len(expected), "missing": missing,
            "forbidden_call_cases": unsafe, "invalid_tool_argument_cases": invalid,
            "incomplete": incomplete, "failed_stop_cases": sorted(failed_stops),
            "tool_call_target_met": not missing and not incomplete and not unsafe and not failed_stops and passed / len(expected) >= .95,
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
