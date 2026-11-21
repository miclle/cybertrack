"""Stage v2's direct-fit bottles, CAD exports and print projects in a scratch directory.

Run with FreeCAD Python on the preceding v2 two-bottle revision, passing an
empty output directory. Copy the verified files to the matching paths under
hardware/model and retire the exports listed in the readback.
"""

from collections import Counter
import json
from pathlib import Path
import sys
from zipfile import ZipFile

import FreeCAD as App
import Part

from cad_gui_state import capture, restore
from check_print_project_preservation import read
from check_water_bottle_service import TOL_MM3, review
from restore_liquid_supply import HOSES, RETIRED
from retire_ignition_cad import changed_volume, export_part, match_face_materials, valid
from update_backpack import BOTTLE, MODEL, sha
from update_backpack_prints import update
from update_pp02 import same, shape_rows

V = App.Vector
BOTTLES = ("Water", "Bubble")
RETIRED_SUFFIXES = tuple(name.removeprefix("Bubble") for name in BOTTLE if name != "BubbleModule")
REMOVED = {bottle + suffix for bottle in BOTTLES for suffix in RETIRED_SUFFIXES}
PRINT_REMOVED = {bottle + suffix for bottle in BOTTLES for suffix in ("Pod", "LidMark")}
FLOOR_Z = 34
DROP = 6
HOSE_OLD_Z = 154.5


def add_material(obj, additions):
    previous = obj.Shape
    assert all(previous.common(fill).Volume < TOL_MM3 for fill in additions), obj.Name
    obj.Shape = previous.multiFuse(additions).removeSplitter()
    valid(obj.Shape)
    assert abs(obj.Shape.Volume - previous.Volume - sum(fill.Volume for fill in additions)) < TOL_MM3


def shift_down(obj):
    shifted = obj.Shape.copy()
    shifted.translate(V(0, 0, -DROP))
    obj.Shape = shifted


def revise(doc, design):
    removed = REMOVED | {name + "StrapAccessSpace" for name in BOTTLES} if design else REMOVED
    assert all(doc.getObject(name) for name in removed)
    # Use the original flat wet-bay floor and rear wall. Fill only their former
    # bottle hardware features, preserving the PP03/PP04 mounting interface.
    floor = [Part.makeCylinder(2.1, 3, V(x, 65, 31)) for x in (-45, -11, 11, 45)]
    wall = [Part.makeBox(28, 3, 24, V(x - 14, 92, 100)) for x in (28, -28)]
    edited = {"PrintBackpack", "PrintLowerTub"}
    if design:
        add_material(doc.LowerTub, floor)
        add_material(doc.BackpackShell, wall)
        doc.BackpackShell.Label = "背包 · 开放式双瓶直放舱"
        doc.BackpackShell.EvidenceBasis = "清水与泡泡液瓶直接放入，原绑带缺口封平。"
        edited.update(("LowerTub", "BackpackShell"))
    else:
        add_material(doc.PrintLowerTub, floor)
        add_material(doc.PrintBackpack, wall)
    doc.PrintBackpack.Label = "PP03 背包及双瓶直放舱"
    doc.PrintBackpack.EvidenceBasis = "清水与泡泡液瓶直接放入，原绑带缺口封平。"
    doc.PrintLowerTub.EvidenceBasis += " 双瓶直接落在湿舱底面，原四个底托嵌件孔封平。"

    for bottle, hose, x, radius in zip(BOTTLES, HOSES, (28, -28), (2.5, 2)):
        module = doc.getObject(bottle + "Module")
        assert abs(module.Shape.BoundBox.ZMin - (FLOOR_Z + DROP)) < 1e-5
        shift_down(module)
        add_material(doc.getObject(hose), [Part.makeCylinder(radius, DROP, V(x, 65, HOSE_OLD_Z - DROP))])
        edited.update((module.Name, hose))
        if design:
            clearance = doc.getObject(bottle + "GunHoseClearance")
            add_material(clearance, [Part.makeCylinder(4, DROP, V(x, 65, HOSE_OLD_Z - DROP))])
            edited.add(clearance.Name)
            for suffix in ("BottleRemovalSpace", "DipTubeSpace"):
                space = doc.getObject(bottle + suffix)
                shift_down(space)
                edited.add(space.Name)
            fingers = doc.getObject(bottle + "FingerSpace")
            box = fingers.Shape.optimalBoundingBox(False)
            # Keep finger access above the continuous back wall and beside the cap.
            rim = doc.BackpackShell.Shape.BoundBox.ZMax
            fingers.Shape = Part.makeBox(box.XLength, box.YLength, box.ZMax - DROP - rim,
                                         V(box.XMin, box.YMin, rim))
            fingers.Label = ("清水" if bottle == "Water" else "泡泡液") + " · 后缘上方抓取空间"
            edited.add(fingers.Name)
    for name in sorted(removed):
        doc.removeObject(name)
    doc.recompute()
    return removed, edited


def stage_native(relative, out, design):
    path = MODEL / relative
    doc = App.openDocument(str(path))
    before = shape_rows(doc)
    state = capture(path)
    original_shapes = {obj.Name: obj.Shape.copy() for obj in doc.Objects
                       if obj.Name in before and obj.Name not in REMOVED}
    removed, edited = revise(doc, design)
    # Face-color arrays must track the new topology. Translated bottle faces
    # retain their original order and style.
    for name in edited - {bottle + "Module" for bottle in BOTTLES}:
        match_face_materials(state, type_view(name, original_shapes[name]), doc.getObject(name))
    expected = shape_rows(doc)
    unchanged = set(before) - removed - edited
    assert before.keys() - expected.keys() == removed and not expected.keys() - before.keys()
    assert all(same(before[name], expected[name]) for name in unchanged)
    for name in unchanged:
        current = doc.getObject(name).Shape
        original = original_shapes[name]
        if current.exportBrepToString() != original.exportBrepToString():
            assert changed_volume(current, original) < TOL_MM3, name
    for name in edited:
        valid(doc.getObject(name).Shape)
    # Verify that added material in the two printed solids stays out of all
    # delivered components and device envelopes.
    if not design:
        for name in ("PrintLowerTub", "PrintBackpack", *HOSES):
            added = doc.getObject(name).Shape.cut(original_shapes[name])
            for obj in doc.Objects:
                if (obj.Name == name or obj.Name not in expected
                        or getattr(obj, "Category", "") == "clearance"):
                    continue
                if added.BoundBox.intersect(obj.Shape.BoundBox):
                    assert added.common(obj.Shape).Volume < TOL_MM3, (name, obj.Name)
    dest = out / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.saveAs(str(dest))
    App.closeDocument(doc.Name)
    gui = restore(dest, state)
    reopened = App.openDocument(str(dest))
    actual = shape_rows(reopened)
    assert actual.keys() == expected.keys()
    assert all(same(actual[name], expected[name]) for name in actual)
    assert not any(obj.Name.startswith(RETIRED) for obj in reopened.Objects)
    for name in edited:
        valid(reopened.getObject(name).Shape)
    return reopened, {"removed": sorted(removed), "edited": sorted(edited), "unaffected_shapes": len(unchanged),
                      "baseline_sha256": sha(path), "sha256": sha(dest), "gui": gui}


def type_view(name, shape):
    from types import SimpleNamespace

    return SimpleNamespace(Name=name, Shape=shape)


def service(doc):
    rows = {}
    floor = doc.PrintLowerTub.Shape
    for bottle, hose in zip(BOTTLES, HOSES):
        body = doc.getObject(bottle + "Module").Shape
        bottom = next(face for face in body.Faces if abs(face.BoundBox.ZMax - FLOOR_Z) < 1e-5)
        contact = bottom.common(floor).Area
        assert contact > bottom.Area - 1e-5, (bottle, contact, bottom.Area)
        gap = doc.getObject(hose).Shape.distToShape(body)[0]
        assert abs(gap - .5) < 1e-5
        row = review(doc, bottle)
        assert row["pass"] and not row["released_first"], row
        rows[bottle] = {**row, "floor_contact_mm2": round(contact, 4), "cap_to_hose_gap_mm": gap}
    return rows


def export_changed_parts(doc, out):
    exports = {}
    for assembly_name, stem, angle in (
        ("PrintBackpack", "remaining-print/PP03-base", 0),
        ("PrintBackpack", "remaining-print/PP03-back", 90),
        ("PrintLowerTub", "print-parts/PP04-LowerTub", 0),
    ):
        path = out / stem
        path.parent.mkdir(exist_ok=True)
        exports[stem] = export_part(doc.getObject(assembly_name).Shape, path, angle)
        assert exports[stem]["step_volume_delta_mm3"] < TOL_MM3
    return exports


def stage_print(relative, out):
    src = MODEL / relative
    dst = out / relative
    dst.parent.mkdir(exist_ok=True)
    replacements = {"PP03-base": out / "remaining-print/PP03-base.stl",
                    "PP04-LowerTub.stl": out / "print-parts/PP04-LowerTub.stl"}
    row = update(src, removed_names=PRINT_REMOVED, replacements=replacements, destination=dst)
    meshes, settings, process, plates = read(src)
    new_meshes, new_settings, new_process, new_plates = read(dst)
    removed = PRINT_REMOVED & settings.keys()
    assert set(row["removed"]) == removed
    assert new_meshes.keys() == {key for key in meshes if key[0] not in removed}
    for key, mesh in new_meshes.items():
        if key[0] not in replacements:
            assert mesh == meshes[key], key
    assert new_settings == {name: props for name, props in settings.items() if name not in removed}
    assert new_process == process
    assert new_plates == [{**plate, "objects": [name for name in plate["objects"] if name not in removed]}
                          for plate in plates]
    with ZipFile(src) as old, ZipFile(dst) as new:
        row["cached_plates"] = [i for i in range(1, len(plates) + 1)
                                if f"Metadata/plate_{i}.gcode" in new.namelist()]
        for i in row["cached_plates"]:
            for ext in ("gcode", "gcode.md5"):
                member = f"Metadata/plate_{i}.{ext}"
                assert new.read(member) == old.read(member)
    row["requires_reslice_plates"] = [i for i in range(1, len(plates) + 1) if i not in row["cached_plates"]]
    return row


def main(out):
    design, design_report = stage_native("source/CyberTrack-design.FCStd", out, True)
    delivery, delivery_report = stage_native("CyberTrack.FCStd", out, False)
    for name in ("PrintBackpack", "PrintLowerTub", *HOSES, *(bottle + "Module" for bottle in BOTTLES)):
        assert changed_volume(design.getObject(name).Shape, delivery.getObject(name).Shape) < TOL_MM3, name
    services = service(delivery)
    exports = export_changed_parts(delivery, out)
    for ext in ("stl", "step"):
        (out / "print-parts" / f"PP03-Backpack.{ext}").write_bytes(
            (out / "remaining-print" / f"PP03-base.{ext}").read_bytes())
    (out / "print-parts/PP04-LowerTub.brep").unlink()
    assembly = [obj for obj in delivery.Objects
                if hasattr(obj, "Shape") and not obj.isDerivedFrom("App::DocumentObjectGroup")
                and (obj.Name in (*HOSES, "WaterModule", "BubbleModule")
                     or getattr(obj, "Category", "") not in ("clearance", "envelope"))]
    step = out / "CyberTrack.step"
    Part.export(assembly, str(step))
    exchange = Part.read(str(step))
    expected_solids = sum(len(obj.Shape.Solids) for obj in assembly)
    assert len(exchange.Solids) == expected_solids, (len(exchange.Solids), expected_solids)
    App.closeDocument(design.Name)
    App.closeDocument(delivery.Name)

    projects = [stage_print(relative, out) for relative in (
        "lean-print/CyberTrack-Lean-6plates.3mf", "print-ready/CyberTrack-Ready-6plates.3mf")]
    retired = {str(path.relative_to(MODEL)): sha(path)
               for name in sorted(PRINT_REMOVED)
               for path in sorted((MODEL / "completion-print").glob(f"{name}.*"))}
    files = {str(path.relative_to(out)): sha(path) for path in sorted(out.rglob("*")) if path.is_file()}
    report = {"saved_reopened": True, "source": design_report, "delivery": delivery_report,
              "bottle_service": services, "step_solids": len(exchange.Solids),
              "step_invalid_solids": Counter(solid.isValid() for solid in exchange.Solids).get(False, 0),
              "exports": exports, "retired_exports": retired, "files_sha256": files,
              "projects": projects, "physical_fit_verified": False, "slicing_validated": False}
    (out / "bottle-backpack-direct-fit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
