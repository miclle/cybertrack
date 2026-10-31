#!/usr/bin/env python3
"""Review raw family draft edit captures. Text and receipt timing are separate signals."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re

CORPUS = Path(__file__).resolve().parents[1] / "docs/validation/draft-edit-variants.json"
ENGLISH = re.compile(r"\b[A-Za-z]+(?:['’][A-Za-z]+)?\s+[A-Za-z]+", re.ASCII)
TOOL = re.compile(r"(?:self[._]tank[._]\w+|\b(?:get_status|replace_step|remove_step|steps_json|draft_saved)\b)", re.ASCII)


def review(trace):
    corpus = json.loads(CORPUS.read_bytes())
    if (trace["kind"] != "captured_tool_calls" or trace["corpus_sha256"] != hashlib.sha256(CORPUS.read_bytes()).hexdigest()
            or trace["input_mode"] != "raw_text_diagnostic" or trace["fixture_version"] != "draft_host"):
        raise ValueError("Expected raw family draft inputs with firmware host receipts")
    rows = []
    for case, row in zip(corpus["cases"], trace["results"], strict=True):
        if (row["id"] != case["id"] or row["input_text"] != case["text"] or not row["completed"]
                or row["completion"] != "tts_stop" or row["echoed_text"] != case["text"]):
            raise ValueError("Incomplete or mismatched family draft conversation")
        events = row["timeline"]
        replies = row["replies"]
        calls = [c["name"].replace("self_tank_", "self.tank.", 1) for c in row["calls"]]
        receipt_indexes = [i for i, e in enumerate(events) if e["event"] == "tool_reply_sent"]
        receipts = row["simulated_receipts"]
        edit_reply = None
        for tool, i, receipt in zip(calls, receipt_indexes, receipts, strict=True):
            if events[i]["name"].replace("self_tank_", "self.tank.", 1) != tool:
                raise ValueError("Receipt does not match tool call")
            if tool == "self.tank.compose" and not events[i]["is_error"] and receipt.get("result") == "draft_saved":
                edit_reply = i
        sentence_indexes = [i for i, e in enumerate(events) if e["event"] == "tts_sentence_start"]
        if [events[i]["reply_index"] for i in sentence_indexes] != list(range(len(replies))):
            raise ValueError("Missing sentence boundary")
        text = "".join(replies)
        rows.append({
            "id": case["id"], "calls": calls,
            "results": [r.get("result") for r in receipts],
            "before_saved_segments": None if edit_reply is None else sum(i < edit_reply for i in sentence_indexes),
            "audio_before_saved": None if edit_reply is None else any(
                e["event"] == "first_audio" for e in events[:edit_reply]),
            "english_phrase": bool(ENGLISH.search(text)), "tool_word": bool(TOOL.search(text)),
            "reply_characters": len(text), "reply": text,
        })
    return {"run_id": trace["run_id"], "role_sha256": trace["role_sha256"],
            "schema_sha256": trace["tool_schema_sha256"], "host_sha256": trace["host_replay_sha256"],
            "rows": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", nargs="+", type=Path)
    results = []
    for path in parser.parse_args().captures:
        raw = path.read_bytes()
        results.append(review(json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)))
    print(json.dumps(results, ensure_ascii=False, indent=2))
