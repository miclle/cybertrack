"""Read the audited Lean project and slice its uncached plates in a temporary directory."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "hardware/model/lean-print/CyberTrack-Lean-6plates.3mf"
RELEASE = ROOT / "hardware/model/print-ready/release-check.json"
DEFAULT_SLICER = "/Applications/BambuStudio.app/Contents/MacOS/BambuStudio"


def metadata(element):
    return {item.get("key"): item.get("value") for item in element.findall("metadata")}


def estimate(slicer):
    release = json.loads(RELEASE.read_text())
    project = ROOT / PROJECT
    digest = hashlib.sha256(project.read_bytes()).hexdigest()
    expected = next(p for p in release["projects"] if p["project"] == PROJECT)
    if not release["passed"] or digest != expected["sha256"]:
        raise ValueError("Refresh the print release audit for this project first")
    plates = []
    with ZipFile(project) as archive, tempfile.TemporaryDirectory() as workspace:
        settings = json.loads(archive.read("Metadata/project_settings.config"))
        layout = ET.fromstring(archive.read("Metadata/model_settings.config"))
        for plate in layout.findall("plate"):
            index = int(metadata(plate)["plater_id"])
            instances = plate.findall("model_instance")
            member = f"Metadata/plate_{index}.gcode"
            diagnostics = []
            if index in expected["requires_reslice_plates"]:
                dest = Path(workspace) / str(index)
                dest.mkdir()
                proc = subprocess.run([slicer, "--orient", "0", "--arrange", "0", "--slice",
                                       str(index), "--outputdir", str(dest), str(project)],
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, check=True, timeout=600)
                diagnostics = [line.split("]   ", 1)[-1] for line in proc.stdout.splitlines()
                               if "[error]" in line or "[warning]" in line]
                result = json.loads((dest / "result.json").read_text())
                stats, = result["sliced_plates"]
                if (result["return_code"] or stats["id"] != index
                        or len(stats["objects"]) != len(instances)):
                    raise ValueError(f"Unexpected slicing result on plate {index}")
                if stats["warning_message"]:
                    diagnostics.append(stats["warning_message"])
                gcode = (dest / Path(member).name).read_bytes()
                source = "fresh_slice"
            else:
                gcode = archive.read(member)
                if hashlib.md5(gcode).hexdigest() != archive.read(member + ".md5").decode().lower():
                    raise ValueError(f"Cached G-code checksum mismatch on plate {index}")
                source = "project_cache"
            header = gcode[:4096].decode("utf-8", errors="replace")
            grams = re.search(r"total filament weight \[g\] : ([\d.]+)", header)
            duration = re.search(r"total estimated time: (?:(\d+)h )?(?:(\d+)m )?(\d+)s", header)
            if not grams or not duration:
                raise ValueError(f"Missing slicer estimates on plate {index}")
            hours, minutes, seconds = map(int, duration.groups(default="0"))
            plates.append(dict(plate=index, parts=len(instances), source=source,
                               slicer=header.splitlines()[1].removeprefix("; "),
                               estimated_g=float(grams[1]), estimated_s=3600*hours+60*minutes+seconds,
                               diagnostics=diagnostics))
    if (len(plates) != expected["plate_count"]
            or sum(p["parts"] for p in plates) != expected["print_parts"]):
        raise ValueError("Plate or part count differs from release audit")
    return dict(project=PROJECT, sha256=digest, printer=settings["printer_settings_id"],
                filament=settings["filament_settings_id"], plates=plates,
                estimated_g=round(sum(p["estimated_g"] for p in plates), 2),
                estimated_s=sum(p["estimated_s"] for p in plates))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slicer", default=DEFAULT_SLICER, help="Bambu Studio CLI executable")
    print(json.dumps(estimate(parser.parse_args().slicer), indent=2, ensure_ascii=False))
