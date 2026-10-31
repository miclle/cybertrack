#!/usr/bin/env python3
"""Check the declared source/recorded deployment; never contact a device."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def check(root=ROOT):
    firmware = root / "firmware"
    current = json.loads((firmware / "current.json").read_text())
    overlay = (firmware / "esp32-audio/apply_overlay.py").read_text()
    versions = re.findall(r'set\(PROJECT_VER "(2\.0\.3-ct[^"\s]+)"\)', overlay)
    if versions != [current["source_version"]]:
        raise ValueError("current.json source_version does not match apply_overlay.py")
    role_hash = hashlib.sha256((firmware / "esp32-audio/role-prompt.txt").read_bytes()).hexdigest()
    if role_hash != current["role_sha256"]:
        raise ValueError("role source changed: update candidate hash and deployment relation")
    deployment = json.loads((firmware / current["last_recorded_deployment"]).read_text())
    # A role-only save/restart does not constitute another firmware flash.
    role_sync = json.loads((firmware / current["last_recorded_role_sync"]).read_text()) if current.get("last_recorded_role_sync") else deployment
    evidence = json.loads((firmware / current["software_evidence"]).read_text())
    relation = current["deployment_relation"]
    if relation not in ("matches_recorded_version", "candidate_not_deployed"):
        raise ValueError("unknown deployment relation")
    if relation == "matches_recorded_version":
        if deployment["version"] != current["source_version"] or evidence["version"] != current["source_version"]:
            raise ValueError("declared source/deployment/evidence versions disagree")
        if role_sync["version"] != current["source_version"] or role_sync["platform_role"]["sha256"] != role_hash:
            raise ValueError("role differs from recorded platform synchronization")
    if current["physical_acceptance"] != "incomplete":
        raise ValueError("physical acceptance requires a separately reviewed evidence contract")
    return {"source_version": current["source_version"], "recorded_deployment": deployment["version"],
            "deployment_relation": relation, "role_sha256": role_hash,
            "scope": "metadata consistency only; not live device or source artifact equivalence"}


if __name__ == "__main__":
    print(json.dumps(check(), ensure_ascii=False, indent=2))
