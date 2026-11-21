"""Stage the historical bottle holder and its marker in both current print projects."""

from copy import deepcopy
import json
from math import hypot
from pathlib import Path
import sys
import uuid
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from check_print_project_preservation import read
from print_project_3mf import PN, archive_write, meta, relxml, setmeta, sha, tag, xml

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "hardware/model"
OBJECTS = ("BubblePod", "BubbleLidMark")
MODEL_XML = "3D/3dmodel.model"
SETTINGS_XML = "Metadata/model_settings.config"
RELS = "3D/_rels/3dmodel.model.rels"


def load(path):
    with ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def bounds(points):
    return tuple(min(v[i] for v in points) for i in range(3)) + tuple(max(v[i] for v in points) for i in range(3))


def add_parts(current, historical, target, plate_number, target_centres=None):
    files = load(current)
    old = load(historical)
    root = ET.fromstring(files[MODEL_XML])
    settings = ET.fromstring(files[SETTINGS_XML])
    old_root = ET.fromstring(old[MODEL_XML])
    old_settings = ET.fromstring(old[SETTINGS_XML])
    plate = settings.findall("plate")[plate_number - 1]
    resources, build = root.find(tag("resources")), root.find(tag("build"))
    relationships = ET.fromstring(files[RELS])
    id_num = 1 + max(int(obj.get("id")) for k, v in files.items() if k.endswith(".model")
                     for obj in ET.fromstring(v).iter(tag("object")))
    ids = [int(meta(node)["identify_id"]) for node in settings.findall(".//model_instance")]
    identify_id = 1 + max(ids)
    before, obj_settings, process, plates = read(current)
    old_meshes, *_ = read(historical)
    local_positions = {}
    for name in OBJECTS:
        setting = deepcopy(next(obj for obj in old_settings.findall("object") if meta(obj)["name"] == name))
        original_id = setting.get("id")
        parent = deepcopy(old_root.find(f"{tag('resources')}/{tag('object')}[@id='{original_id}']"))
        instance = deepcopy(old_root.find(f"{tag('build')}/{tag('item')}[@objectid='{original_id}']"))
        part = setting.find("part")
        component = parent.find(f"{tag('components')}/{tag('component')}")
        path_key = f"{{{PN}}}path"
        submodel = ET.fromstring(old[component.get(path_key).lstrip("/")])
        child = submodel.find(f"{tag('resources')}/{tag('object')}")
        parent_id, child_id = str(id_num), str(id_num + 1)
        id_num += 2
        for elem in (parent, setting):
            elem.set("id", parent_id)
        for elem in (child, part):
            elem.set("id", child_id)
        instance.set("objectid", parent_id)
        component.set("objectid", child_id)
        asset = f"3D/Objects/v2-liquid-{name}.model"
        component.set(path_key, "/" + asset)
        for index, element in enumerate((parent, instance, component, child, part)):
            key = f"{{{PN}}}UUID" if element is not part else "uuid"
            if key in element.attrib:
                element.set(key, str(uuid.uuid5(uuid.NAMESPACE_URL, f"cybertrack/v2/{name}/{index}")))
        record = next(points for (obj, _), (points, _, _, _) in old_meshes.items() if obj == name)
        old_bounds = bounds(record)
        tr = list(map(float, instance.get("transform").split()))
        origin = ((plate_number - 1) % 3 * 307.2, -((plate_number - 1) // 3) * 307.2)
        if target_centres:
            for axis, coordinate in enumerate(target_centres[name]):
                tr[9 + axis] += origin[axis] + coordinate - (old_bounds[axis] + old_bounds[axis + 3]) / 2
        instance.set("transform", " ".join(map(str, tr)))
        local_positions[name] = [round(tr[i + 9] - origin[i], 3) for i in (0, 1)]
        files[asset] = xml(submodel)
        ET.SubElement(relationships, "Relationship", Target="/" + asset, Id=f"liquid-{name}",
                      Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel")
        resources.append(parent)
        build.append(instance)
        settings.insert(list(settings).index(settings.find("plate")), setting)
        row = ET.SubElement(plate, "model_instance")
        for key, value in (("object_id", parent_id), ("instance_id", 0), ("identify_id", identify_id)):
            setmeta(row, key, value)
        identify_id += 1
    assert f"Metadata/plate_{plate_number}.gcode" not in files, "Clear the old toolpath before restoring parts"
    for item in list(plate.findall("metadata")):
        if item.get("key") in ("thumbnail_file", "thumbnail_no_light_file", "top_file", "pick_file"):
            files.pop(item.get("value"), None)
            plate.remove(item)
    files[MODEL_XML], files[SETTINGS_XML], files[RELS] = xml(root), xml(settings), relxml(relationships)
    archive_write(target, files)
    after, new_settings, retained_process, final_plates = read(target)
    assert all(after[key] == value for key, value in before.items())
    assert all(new_settings[key] == value for key, value in obj_settings.items())
    assert retained_process == process
    assert [row for i, row in enumerate(final_plates, 1) if i != plate_number] == [
        row for i, row in enumerate(plates, 1) if i != plate_number]
    plated = final_plates[plate_number - 1]["objects"]
    assert set(plated) == set(plates[plate_number - 1]["objects"]) | set(OBJECTS)
    separation = {}
    for name in OBJECTS:
        key = next(key for key in after if key[0] == name)
        assert after[key][1:] == old_meshes[key][1:]
        box = bounds(after[key][0])
        assert all(origin[i] <= box[i] and box[i + 3] <= origin[i] + 256 for i in (0, 1))
        assert abs(box[2]) < .01, (name, box)
        gaps = []
        for (other, _), (points, _, _, _) in after.items():
            if other == name or other not in plated:
                continue
            other_box = bounds(points)
            gaps.append(hypot(*(max(0, box[i] - other_box[i+3], other_box[i] - box[i+3]) for i in (0, 1))))
        separation[name] = round(min(gaps), 3)
        assert separation[name] >= 4, (name, separation)
    return {"path": str(current.relative_to(ROOT)), "sha256": sha(target.read_bytes()),
            "print_parts": len(new_settings), "part_names": list(new_settings),
            "restored_parts": list(OBJECTS), "plate": plate_number, "local_placements_mm": local_positions,
            "minimum_xy_bounding_box_gap_mm": separation, "existing_instances_preserved": True}


def main(out):
    projects = (
        ("lean-print/CyberTrack-Lean-6plates.3mf", 3, None),
        ("print-ready/CyberTrack-Ready-6plates.3mf", 5, {"BubblePod": (150, 46), "BubbleLidMark": (194, 75)}),
    )
    results = [add_parts(MODEL / name, out / "baseline/lean.3mf", out / Path(name).name, plate, centres)
               for name, plate, centres in projects]
    (out / "liquid-print-readback.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
