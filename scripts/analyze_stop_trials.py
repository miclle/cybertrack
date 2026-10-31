#!/usr/bin/env python3
"""Analyze recorded stop trials offline; never control or certify a device."""
import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
REPEATS = 5


@dataclass(frozen=True)
class Case:
    """One source/phase-specific observation requirement."""

    id: str
    event: str
    phase: str
    sources: dict[str, str]
    stop: tuple[str, ...]
    keep: tuple[str, ...] = ()


# Low-voltage motion/bubble trials only. No ignition or high-voltage procedure.
MIXED = {"move": "web", "bubbles": "voice"}
CASES = tuple(
    Case(f"release_{channel}", "pointer_release", "active", {channel: "web"}, (channel,))
    for channel in ("move", "water", "bubbles")
) + (
    Case("boot_mixed", "boot", "active", MIXED, ("move", "bubbles")),
    Case("stop_mixed", "global_stop", "active", MIXED, ("move", "bubbles")),
    Case("page_hidden_mixed", "page_hidden", "active", MIXED, ("move",), ("bubbles",)),
    Case("web_loss_mixed", "web_network_loss", "active", MIXED, ("move",), ("bubbles",)),
    Case("wifi_loss_mixed", "wifi_disconnect", "active", MIXED, ("move", "bubbles")),
    Case("voice_loss_mixed", "voice_disconnect", "active", MIXED, ("bubbles",), ("move",)),
) + tuple(
    Case(f"sequence_{event}_{source}_{phase}", event, phase,
         {"move": source, "bubbles": source}, ("move", "bubbles"))
    for event in ("cancel", "source_disconnect")
    for source in ("web", "voice")
    for phase in ("active", "waiting")
)
CASE_BY_ID = {case.id: case for case in CASES}


def text(value: object, label: str) -> str:
    """Require a nonblank record label without interpreting its evidence."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: nonblank string required")
    return value


def number(value: object, label: str, *, nullable: bool = False) -> float | None:
    """Reject booleans, non-finite numbers and negative timestamps."""
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{label}: finite nonnegative number required")
    return value


def flag(value: object, label: str) -> bool | None:
    """Unknown observations remain null, never become a false/zero result."""
    if value is not None and type(value) is not bool:
        raise ValueError(f"{label}: boolean or null required")
    return value


def fields(value: object, keys: set[str], label: str) -> None:
    """Catch misspelled or missing observation fields before aggregation."""
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label}: exact fields required: {', '.join(sorted(keys))}")


def stats(values: list[float]) -> dict:
    """Return descriptive sample statistics, not an acceptance threshold."""
    return {"count": len(values), "median": median(values) if values else None,
            "max": max(values) if values else None}


def analyze(data: dict) -> dict:
    """Check per-profile coverage and report known violations separately."""
    fields(data, {"schema_version", "profiles", "trials"}, "input")
    if type(data["schema_version"]) is not int or data["schema_version"] not in (1, 2):
        raise ValueError("unsupported schema")
    if not isinstance(data["profiles"], list) or not isinstance(data["trials"], list):
        raise ValueError("profiles and trials must be arrays")
    profiles = {}
    for profile in data["profiles"]:
        fields(profile, {"id", "evidence_kind", "firmware_sha256", "battery", "load", "ground_surface",
                         "speed_percent", "method", "timing_uncertainty_ms", "observation_window_ms"}, "profile")
        name = text(profile["id"], "profile.id")
        if name in profiles:
            raise ValueError(f"duplicate profile: {name}")
        if profile["evidence_kind"] not in ("physical_observation", "software_simulation"):
            raise ValueError(f"{name}: unsupported evidence kind")
        if not isinstance(profile["firmware_sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", profile["firmware_sha256"]):
            raise ValueError(f"{name}: firmware SHA-256 required")
        for key in ("battery", "load", "ground_surface", "method"):
            text(profile[key], f"{name}.{key}")
        if type(profile["speed_percent"]) is not int or not 60 <= profile["speed_percent"] <= 100:
            raise ValueError(f"{name}: PWM speed must be integer 60..100")
        number(profile["timing_uncertainty_ms"], f"{name}.timing_uncertainty_ms")
        if number(profile["observation_window_ms"], f"{name}.observation_window_ms") <= 0:
            raise ValueError(f"{name}: positive recovery observation window required")
        profiles[name] = profile
    rows = {name: {case.id: [] for case in CASES} for name in profiles}
    seen_ids, seen_repeats, seen_events = set(), set(), set()
    for trial in data["trials"]:
        times = {"device_event_ms", "recovered_ms", "observed_until_ms"} if data["schema_version"] == 2 else set()
        fields(trial, times | {"id", "profile_id", "case_id", "repeat", "evidence_ref", "event_ms", "channels",
                       "recovery_observed", "stale_action_resumed"}, "trial")
        trial_id = text(trial["id"], "trial.id")
        if trial_id in seen_ids:
            raise ValueError(f"duplicate trial: {trial_id}")
        seen_ids.add(trial_id)
        profile_id, case_id = trial["profile_id"], trial["case_id"]
        text(profile_id, "trial.profile_id")
        text(case_id, "trial.case_id")
        if profile_id not in profiles or case_id not in CASE_BY_ID:
            raise ValueError(f"{trial_id}: unknown profile or case")
        if type(trial["repeat"]) is not int or trial["repeat"] < 1:
            raise ValueError(f"{trial_id}: positive integer repeat required")
        repeat_key = (profile_id, case_id, trial["repeat"])
        if repeat_key in seen_repeats:
            raise ValueError(f"{trial_id}: duplicate case repeat")
        seen_repeats.add(repeat_key)
        evidence = trial["evidence_ref"]
        if evidence is not None:
            text(evidence, f"{trial_id}.evidence_ref")
        event = number(trial["event_ms"], f"{trial_id}.event_ms", nullable=True)
        # The same event cannot be relabelled as five repetitions or two cases.
        event_key = (evidence, event)
        if evidence is not None and event is not None and event_key in seen_events:
            raise ValueError(f"{trial_id}: evidence event already counted")
        if evidence is not None and event is not None:
            seen_events.add(event_key)
        case = CASE_BY_ID[case_id]
        fields(trial["channels"], set(case.sources), f"{trial_id}.channels")
        missing, violations, measurements = [], [], {}
        if evidence is None:
            missing.append("evidence reference missing")
        if event is None:
            missing.append("trigger timestamp missing")
        detected, recovered, observed_until = [number(trial.get(key), key, nullable=True) for key in
                                              ("device_event_ms", "recovered_ms", "observed_until_ms")]
        recorded_times = [t for t in (event, detected, recovered, observed_until) if t is not None]
        if recorded_times != sorted(recorded_times):
            raise ValueError(f"{trial_id}: event, device detection, recovery and observation must be ordered")
        if detected is None:
            missing.append("device trigger timestamp missing")
        window = None if recovered is None or observed_until is None else observed_until - recovered
        if window is None or window < profiles[profile_id]["observation_window_ms"]:
            missing.append("insufficient timed observation after recovery")
        for channel, source in case.sources.items():
            row = trial["channels"][channel]
            deadline_field = {"normal_end"} if data["schema_version"] == 2 else set()
            fields(row, deadline_field | {"source", "output_off_ms", "mechanical_stop_ms", "stopping_distance_mm",
                         "continued_until_own_deadline"}, f"{trial_id}.{channel}")
            if row["source"] != source:
                raise ValueError(f"{trial_id}.{channel}: expected {source} source")
            off = number(row["output_off_ms"], f"{trial_id}.{channel}.output_off_ms", nullable=True)
            mechanical = number(row["mechanical_stop_ms"], f"{trial_id}.{channel}.mechanical_stop_ms", nullable=True)
            distance = number(row["stopping_distance_mm"], f"{trial_id}.{channel}.stopping_distance_mm", nullable=True)
            continued = flag(row["continued_until_own_deadline"], f"{trial_id}.{channel}.continued")
            normal_end = row.get("normal_end")
            held = normal_end == "while_held"
            if held and (source != "web" or case_id.startswith("sequence_")):
                raise ValueError(f"{trial_id}.{channel}: renewable hold requires an independent web channel")
            deadline = None if held else number(normal_end, f"{trial_id}.{channel}.normal_end", nullable=True)
            if case.phase == "active" and channel in case.stop and not held:
                if deadline is None:
                    missing.append(f"{channel}: independent deadline missing")
                elif off is not None and deadline - off <= profiles[profile_id]["timing_uncertainty_ms"]:
                    missing.append(f"{channel}: output cutoff indistinguishable from normal deadline")
            if (case.phase == "active" and channel in case.stop and detected is not None and off is not None
                    and off + profiles[profile_id]["timing_uncertainty_ms"] < detected):
                missing.append(f"{channel}: output already off before device detected trigger")
            if channel != "move" and (mechanical is not None or distance is not None):
                raise ValueError(f"{trial_id}.{channel}: mechanical stop/distance are for tracks only")
            if channel in case.keep:
                if continued is None:
                    missing.append(f"{channel}: source isolation observation")
                elif not continued:
                    violations.append(f"{channel}: unaffected source interrupted")
                continue
            if continued is not None:
                raise ValueError(f"{trial_id}.{channel}: stopped channel cannot use continued flag")
            if off is None:
                missing.append(f"{channel}: output off timestamp")
            if case.phase == "active" and event is not None and off is not None and off < event:
                raise ValueError(f"{trial_id}.{channel}: active output stopped before trigger")
            if case.phase == "waiting" and event is not None and off is not None and off > event:
                violations.append(f"{channel}: output still on during sequence waiting")
            if channel == "move":
                if mechanical is None:
                    missing.append("move: mechanical stop timestamp")
                if distance is None:
                    missing.append("move: stopping distance")
                if case.phase == "active" and event is not None and mechanical is not None and mechanical < event:
                    raise ValueError(f"{trial_id}: active motion stopped before trigger")
            measurements[channel] = {
                "output_latency_ms": None if off is None or event is None else max(0, off-event),
                "mechanical_latency_ms": None if mechanical is None or event is None else max(0, mechanical-event),
                "stopping_distance_mm": distance,
            }
        recovery = flag(trial["recovery_observed"], f"{trial_id}.recovery_observed")
        resumed = flag(trial["stale_action_resumed"], f"{trial_id}.stale_action_resumed")
        if recovery is not True:
            missing.append("recovery not observed")
        if resumed is True:
            violations.append("stale action resumed")
        elif resumed is None:
            missing.append("stale action recovery unknown")
        rows[profile_id][case_id].append({"id": trial_id, "repeat": trial["repeat"], "evidence_ref": evidence,
                                        "detection_latency_ms": None if detected is None or event is None else detected-event,
                                        "recovery_observation_ms": window,
                                        "missing": missing, "violations": violations, "measurements": measurements})
    summaries = []
    for name, cases in rows.items():
        case_reports = []
        for case_id, trials in cases.items():
            complete = sum(not t["missing"] and not t["violations"] for t in trials)
            violations = [t["id"] for t in trials if t["violations"]]
            # A failure stays visible even if five other repetitions succeeded.
            status = "violations_recorded" if violations else "records_complete" if complete >= REPEATS and complete == len(trials) else "incomplete"
            metrics = {}
            for channel in CASE_BY_ID[case_id].stop:
                metrics[channel] = {key: stats([t["measurements"][channel][key] for t in trials
                                                if t["measurements"][channel][key] is not None])
                                    for key in ("output_latency_ms", "mechanical_latency_ms", "stopping_distance_mm")}
            case_reports.append({"case_id": case_id, "status": status, "recorded": len(trials),
                                 "complete_records": complete, "additional_complete_records_needed": max(0, REPEATS-complete),
                                 "metrics": metrics, "trials": trials})
        summaries.append({"profile": profiles[name], "cases": case_reports,
                          "coverage_complete": all(c["status"] == "records_complete" for c in case_reports)})
    physical = [s for s in summaries if s["profile"]["evidence_kind"] == "physical_observation"]
    return {"schema_version": 2, "matrix_id": "stop-v1", "required_repeats_per_case": REPEATS,
            "required_cases": [{"id": c.id, "event": c.event, "phase": c.phase, "source_by_channel": c.sources,
                                "stop_channels": c.stop, "continue_channels": c.keep} for c in CASES],
            "profiles": summaries, "physical_profiles_with_complete_records": [s["profile"]["id"] for s in physical if s["coverage_complete"]],
            "physical_acceptance": "not_established",
            "limitations": ["source files and clocks are declared by the recorder, not independently authenticated",
                           "coverage and descriptive latency statistics are not stopping-distance or electrical acceptance",
                           "firmware, supply, load, ground, speed and method profiles are not pooled",
                           "no observation proves absence of later replay beyond its stated recovery window",
                           "software simulation never counts as physical coverage; no high-voltage trials"]}


def unique_fields(pairs: list[tuple[str, object]]) -> dict:
    """Reject duplicate JSON keys rather than silently picking the last value."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def initialize(profile: dict) -> dict:
    """Generate unobserved rows for a declared configuration, never measurements."""
    data = {"schema_version": 2, "profiles": [profile], "trials": []}
    analyze(data)  # Validate the declared configuration before creating records.
    for case in CASES:
        for repeat in range(1, REPEATS + 1):
            data["trials"].append({
                "id": f"{profile['id']}-{case.id}-{repeat}", "profile_id": profile["id"],
                "case_id": case.id, "repeat": repeat, "evidence_ref": None, "event_ms": None,
                "device_event_ms": None, "recovered_ms": None, "observed_until_ms": None,
                "channels": {channel: {"source": source, "normal_end": None, "output_off_ms": None,
                                       "mechanical_stop_ms": None, "stopping_distance_mm": None,
                                       "continued_until_own_deadline": None}
                             for channel, source in case.sources.items()},
                "recovery_observed": None, "stale_action_resumed": None,
            })
    return data


def main() -> None:
    """Read observations and write a provenance-bearing report without networking."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, nargs="?")
    parser.add_argument("--init-profile", type=Path, help="generate unobserved rows from one profile JSON object")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.init_profile:
            if args.input or not args.output:
                raise ValueError("--init-profile requires --output and no observations input")
            profile = json.loads(args.init_profile.read_bytes(), object_pairs_hook=unique_fields)
            data = initialize(profile)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x") as stream:
                stream.write(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
            return
        args.input = args.input or ROOT / "docs/validation/stop-trials.json"
        raw = args.input.read_bytes()
        data = json.loads(raw, object_pairs_hook=unique_fields)
        report = analyze(data)
        report["input_sha256"] = hashlib.sha256(raw).hexdigest()
        report["input"] = data
        output = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output:
            if args.output.resolve() == args.input.resolve():
                raise ValueError("report must not overwrite observations")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output)
        else:
            print(output, end="")
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
