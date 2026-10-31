#!/usr/bin/env python3
"""Check the declared source/recorded deployment; never contact a device."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def image_identity(record, image=None):
    """Return only distributable fields; deployment records may identify the board."""
    size, digest = record["bytes"], record["sha256"]
    if type(size) is not int or size <= 0 or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("invalid application image identity")
    if image is not None:
        data = image.read_bytes()
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"application image does not match its record: {image.name}")
    return {"bytes": size, "sha256": digest}


def check(root=ROOT, source_bin=None, deployed_bin=None):
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
    synced_role_hash = role_sync["platform_role"]["sha256"]
    evidence = json.loads((firmware / current["software_evidence"]).read_text())
    relation = current["deployment_relation"]
    if relation not in ("matches_recorded_version", "candidate_not_deployed"):
        raise ValueError("unknown deployment relation")
    if evidence["version"] != current["source_version"]:
        raise ValueError("software evidence version does not match source_version")
    if role_sync["version"] != deployment["version"]:
        raise ValueError("role differs from last recorded deployment version")
    source_image = image_identity(evidence.get("esp_idf_build") or evidence["artifact"], source_bin)
    deployed_image = image_identity(deployment["flash"], deployed_bin)
    if relation == "matches_recorded_version":
        if deployment["version"] != current["source_version"] or source_image != deployed_image:
            raise ValueError("declared source/deployment/evidence versions disagree")
        if synced_role_hash != role_hash:
            raise ValueError("role differs from recorded platform synchronization")
    if current["physical_acceptance"] != "incomplete":
        raise ValueError("physical acceptance requires a separately reviewed evidence contract")
    return {"source_version": current["source_version"], "recorded_deployment": deployment["version"],
            "source_image": source_image, "deployed_image": deployed_image,
            "local_source_image_checked": source_bin is not None, "local_deployed_image_checked": deployed_bin is not None,
            "physical_acceptance": current["physical_acceptance"], "deployment_relation": relation, "role_sha256": role_hash,
            "recorded_platform_role_sha256": synced_role_hash, "role_matches_recorded_sync": role_hash == synced_role_hash,
            "scope": "recorded identities; supplied local images checked by size and SHA-256; no device access"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-bin", type=Path, help="compare a local application image to the source build record")
    parser.add_argument("--deployed-bin", type=Path, help="compare a local application image to the last flash record")
    args = parser.parse_args()
    try:
        result = check(source_bin=args.source_bin, deployed_bin=args.deployed_bin)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
