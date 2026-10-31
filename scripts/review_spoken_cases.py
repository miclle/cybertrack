#!/usr/bin/env python3
"""Separate transcription, tool calls, and audible replies for the 20 spoken cases."""

import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path
import unicodedata

from evaluate_voice import canonical

BASE = Path(__file__).resolve().parents[1] / "docs/validation"
VOICE = BASE / "voice-cases.json"
INDEX = BASE / "spoken-cases.json"


def normalized(text):
    # Preserve %, decimal points and negative signs, which can change a request.
    text = unicodedata.normalize("NFKC", text).strip()
    return "".join(c for c in text if not c.isspace() and c not in "。,，!?！？“”「」")


def corpus():
    selection = json.loads(INDEX.read_bytes())["case_ids"]
    all_cases = {c["id"]: c for c in json.loads(VOICE.read_bytes())["cases"]}
    if len(selection) != 20 or len(set(selection)) != 20:
        raise ValueError("Expected 20 unique spoken cases")
    return {cid: all_cases[cid] for cid in selection}


def new_sheet(condition):
    return dict(
        input_mode="human_microphone",
        condition=condition,
        run_id=None,
        firmware=None,
        model=None,
        role_sha256=None,
        corpus_sha256=hashlib.sha256(VOICE.read_bytes()).hexdigest(),
        results=[
            dict(
                id=cid,
                input_text=c["text"],
                actual_utterance=None,
                completed=None,
                evidence_ref=None,
                echoed_text=None,
                calls=None,
                receipts=None,
                heard_reply=None,
                reply_matches_expectation=None,
                observation=None,
            )
            for cid, c in corpus().items()
        ],
    )


def review(trace):
    cases = corpus()
    mode = trace["input_mode"]
    if mode not in ("synthetic_opus", "human_microphone"):
        raise ValueError("Text diagnostics cannot be scored as speech")
    if trace["corpus_sha256"] != hashlib.sha256(VOICE.read_bytes()).hexdigest():
        raise ValueError("Voice corpus differs from the recorded revision")
    human = mode == "human_microphone"
    if human and trace["condition"] not in json.loads(INDEX.read_bytes())["conditions"]:
        raise ValueError("Unknown physical listening condition")
    if not human:
        if trace.get("kind") != "captured_tool_calls" or not all(
            re.fullmatch(r"[0-9a-f]{64}", trace.get(key, ""))
            for key in (
                "synthesis_source_sha256",
                "capture_source_sha256",
                "role_sha256",
                "tool_schema_sha256",
            )
        ):
            raise ValueError("Missing capture provenance")
    results = {}
    for row in trace["results"]:
        cid = row["id"]
        if cid in results or cid not in cases or row["input_text"] != cases[cid]["text"]:
            raise ValueError("Duplicate, unknown or changed spoken case")
        case = cases[cid]
        heard = row.get("echoed_text")
        calls = row.get("calls")
        if heard is not None and not isinstance(heard, str):
            raise ValueError("ASR text must be text or null")
        if calls is not None and (
            not isinstance(calls, list)
            or any(
                not isinstance(c, dict)
                or not isinstance(c.get("name"), str)
                or not isinstance(c.get("arguments"), dict)
                for c in calls
            )
        ):
            raise ValueError("Expected captured tool names and argument objects")
        if row.get("completed") is not None and type(row["completed"]) is not bool:
            raise ValueError("Completion must be boolean or null")
        if human:
            used = bool(
                isinstance(row.get("evidence_ref"), str)
                and row["evidence_ref"].strip()
                and isinstance(row.get("actual_utterance"), str)
                and normalized(row["actual_utterance"]) == normalized(case["text"])
            )
            if used and not all(
                isinstance(trace.get(k), str) and trace[k].strip()
                for k in ("run_id", "firmware", "model", "role_sha256")
            ):
                raise ValueError("Identify the observed run, firmware, role and model")
        else:
            up = row.get("uplink", {})
            if (
                [up.get(k) for k in ("codec", "sample_rate_hz", "channels", "frame_ms")]
                != ["opus", 16000, 1, 60]
                or not re.fullmatch(r"[0-9a-f]{64}", up.get("payload_sha256", ""))
                or any(type(up.get(k)) is not int or up[k] <= 0 for k in ("frames", "encoded_bytes"))
            ):
                raise ValueError("Missing synthetic audio evidence")
            used = True
        complete = used and row.get("completed") is True
        if not human and complete and row.get("completion") != "tts_stop":
            raise ValueError("Missing normal end of synthetic conversation")
        match = None
        if complete and calls is not None:
            try:
                match = canonical(calls) == canonical(case["expected_calls"])
            except (ValueError, TypeError, AttributeError):
                match = False
        allowed = case.get("allowed_tools")
        if case["category"] in ("no_action", "clarify"):
            allowed = ["self.tank.get_status"]
        forbidden = (
            used
            and allowed is not None
            and calls is not None
            and any(c["name"].replace("self_tank_", "self.tank.", 1) not in allowed for c in calls)
        )
        item = dict(
            id=cid,
            expected_text=case["text"],
            asr_text=heard,
            completed=complete,
            transcript_matches=(normalized(heard) == normalized(case["text"]))
            if used and heard is not None
            else None,
            calls_match=match,
            forbidden_call_observed=forbidden,
            expected_reply=case["response_expectation"],
            calls=calls,
        )
        if human:
            assessment = row.get("reply_matches_expectation")
            if assessment is not None and (
                type(assessment) is not bool or not isinstance(row.get("heard_reply"), str)
            ):
                raise ValueError("Assess an observed audible reply or explicitly observed silence")
            item.update(
                heard_reply=row.get("heard_reply"),
                reply_matches_expectation=assessment if complete else None,
                receipts=row.get("receipts"),
                evidence_ref=row.get("evidence_ref"),
            )
        else:
            item.update(
                remote_reply="".join(row["replies"]),
                remote_audio_bytes=row["received_audio_bytes_discarded"],
                fixture_results=[r.get("result") for r in row.get("simulated_receipts", [])],
            )
        results[cid] = item

    def count(key, value):
        return sum(r.get(key) is value for r in results.values())

    return dict(
        input_mode=mode,
        condition=trace.get("condition") if human else "digital_synthesis",
        run_id=trace.get("run_id"),
        role_sha256=trace.get("role_sha256"),
        model=trace.get("model"),
        expected=20,
        completed=count("completed", True),
        transcript_observed=sum(r["transcript_matches"] is not None for r in results.values()),
        transcript_matches=count("transcript_matches", True),
        calls_scored=sum(r["calls_match"] is not None for r in results.values()),
        calls_match=count("calls_match", True),
        forbidden_call_cases=[cid for cid, r in results.items() if r["forbidden_call_observed"]],
        reply_assessed=sum(r.get("reply_matches_expectation") is not None for r in results.values()),
        reply_matches=count("reply_matches_expectation", True),
        missing=sorted(cases.keys() - results.keys()),
        not_completed=[cid for cid in cases if not results.get(cid, {}).get("completed")],
        stop_mismatches=[
            cid
            for cid, r in results.items()
            if cases[cid]["category"] == "stop" and r["calls_match"] is False
        ],
        results=list(results.values()),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--capture", type=Path)
    source.add_argument("--new-sheet", choices=json.loads(INDEX.read_bytes())["conditions"])
    args = parser.parse_args()
    try:
        if args.new_sheet:
            result = new_sheet(args.new_sheet)
        else:
            data = args.capture.read_bytes()
            result = review(json.loads(gzip.decompress(data) if args.capture.suffix == ".gz" else data))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as err:
        parser.exit(2, f"{err}\n")
