#!/usr/bin/env python3
"""Export the pinned local Xiaozhi source and its original component cache."""
import argparse
import hashlib
import io
from pathlib import Path
import shutil
import subprocess
import tarfile
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REVISION = "e8ed16bb42ed9b199cbc9376011653e5037de8d8"
ORIGINAL_ELF_SHA256 = "f7e8809ce981ee4182fb6c3eb15b20aa785111c7f1e4b1e2f059e4debc813b45"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path)
    args = parser.parse_args()
    upstream = args.upstream.resolve()
    target = ROOT / "build/xiaozhi-audio-src"
    if target.exists():
        parser.error("Build export already exists; use a fresh directory after preserving needed results")
    if hashlib.sha256((upstream / "build/xiaozhi.elf").read_bytes()).hexdigest() != ORIGINAL_ELF_SHA256:
        parser.error("Original ELF does not match the backed-up audio board")
    if (upstream / "sdkconfig").read_bytes() != (HERE / "sdkconfig.baseline").read_bytes():
        parser.error("Original sdkconfig differs from the verified baseline")
    archive = subprocess.check_output(["git", "-C", str(upstream), "archive", REVISION])
    target.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        source.extractall(target, filter="data")
    shutil.copy2(HERE / "sdkconfig.baseline", target / "sdkconfig")
    shutil.copy2(HERE / "dependencies.lock", target / "dependencies.lock")
    shutil.copytree(upstream / "managed_components", target / "locked_components")
    # Keep the original versions even if the remote registry has removed them.
    manifest_path = target / "main/idf_component.yml"
    manifest = yaml.safe_load(manifest_path.read_text())
    lock = yaml.safe_load((HERE / "dependencies.lock").read_text())
    for name, entry in lock["dependencies"].items():
        if entry["source"]["type"] != "service":
            continue
        directory = name.replace("/", "__")
        component = target / "locked_components" / directory
        if (component / ".component_hash").read_text().strip() != entry["component_hash"]:
            raise RuntimeError(f"Original component cache hash mismatch: {name}")
        manifest["dependencies"][name] = {"override_path": f"../locked_components/{directory}"}
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    subprocess.run(["python3", str(HERE / "apply_overlay.py"), str(target)], check=True)


if __name__ == "__main__":
    main()
