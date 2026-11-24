"""Stage the A1 electronics and speaker revision on the preceding whole-robot CAD.

Run in FreeCAD's Python environment with an empty output directory. Inputs
are the two pre-revision assemblies, A1 camera fit study and published print jobs.
All geometry uses the assembly frame in millimetres.
"""
from copy import deepcopy
from math import dist
import json
from hashlib import sha256
from types import SimpleNamespace
import sys
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

import FreeCAD as App
from cad_gui_state import capture, restore
import Part

from head_shell_print import TRAY_MOUNTS, print_shape
from retire_ignition_cad import export_part, match_face_materials, valid
from update_backpack_prints import update
from update_pp02 import sha

MODEL = Path(__file__).resolve().parents[1] / "hardware/model"
BOARD_HOLES = [(-44.5, -64), (44.5, -64), (44.5, 9), (-44.49988, -12.5)]
OBSOLETE = ("Breadboard", "EffectMOS", "EffectSupport", "EffectInsert", "EffectTray",
            "EffectScrew", "EffectPort", "EffectTool", "EffectWire", "L298N", "MT3608")
RETIRED_PRINTS = {"LC01-Carrier-upright", "LC02-TopRetainer-flat", "EffectTray",
                  "EffectRetainerLMOS", "EffectRetainerRMOS", "EffectRetainerLBuck", "EffectRetainerRBuck"}
V = App.Vector


def box(x, y, z, w, d, h):
    return Part.makeBox(w, d, h, V(x, y, z))


def vertical(x, y, z, h, r):
    return Part.makeCylinder(r, h, V(x, y, z))


def pcb_frame():
    frame = box(-50.5, -69.5, 171.5, 101, 84, 2.5)
    frame = frame.cut(box(-40, -61, 171, 80, 66, 4))
    for x, y in TRAY_MOUNTS:
        frame = frame.fuse(box(-60 if x < 0 else 50, y - 4, 171.5, 10.5, 8, 2.5))
        frame = frame.cut(vertical(x, y, 171, 4, 1.5))
    for x, y in BOARD_HOLES:
        frame = frame.fuse(vertical(x, y, 173.5, 4.5, 2.5))
        frame = frame.cut(vertical(x, y, 171, 8, 1.05))
    return frame.removeSplitter()


CY, CZ = -23, 188.5
EARS = (CY - 18.4, CY + 18.4)
PORT_Z = (184.5, 189.5, 194.5)


def axial(x0, x1, y, z, r):
    return Part.makeCylinder(r, x1 - x0, V(x0, y, z), V(1, 0, 0))


def handed(shape, side):
    return shape if side == "R" else shape.mirror(V(), V(1, 0, 0))


def speaker():
    # The manufacturer specifies overall dimensions, slot diameter, mouth,
    # pitch and ear thickness. Rectangular tab edges bound the undimensioned profile.
    body = box(-76.5, CY - 14, CZ - 15.5, 14.8, 28, 31)
    for y in EARS:
        first = CY - 21.6 if y < CY else CY + 13.5
        tab = box(-71.5, first, CZ - 4.5, 2, 8.1, 9)
        slot = axial(-72, -69, y, CZ, 2.2)
        mouth = box(-72, y - 4 if y < CY else y, CZ - 1.1, 3, 4, 2.2)
        body = body.fuse(tab.cut(slot.fuse(mouth)))
    return body.removeSplitter()


def seat():
    # The open collar leaves a nominal 1 mm compressed face-gasket space.
    collar = box(-80, CY - 14, CZ - 15.5, 2.5, 28, 31)
    collar = collar.cut(box(-81, CY - 12.75, CZ - 13.75, 5, 25.5, 27.5))
    for y in EARS:
        boss = axial(-80, -71.5, y, CZ, 3.8)
        collar = collar.fuse(boss)
    return collar


def receiver(shape):
    # All three inlets open behind solid bars. Sound turns in the existing
    # air gap and leaves via the original slots; nothing cuts the outer grille.
    ports = [box(-82.1, -19, z - .9, 5.1, 8, 1.8) for z in PORT_Z]
    pilots = [axial(-78.5, -70, y, CZ, 1.2) for y in EARS]
    cut = Part.makeCompound(ports + pilots)
    mount = seat()
    return shape.multiFuse([mount, handed(mount, "L")]).cut(
        Part.makeCompound([cut, handed(cut, "L")])).removeSplitter()


def fasteners():
    parts = []
    for y in EARS:
        screw = axial(-77, -69, y, CZ, 1.45).fuse(axial(-69, -67, y, CZ, 2.8))
        washer = axial(-69.5, -69, y, CZ, 3.5).cut(axial(-70, -68, y, CZ, 1.6))
        parts.extend([screw, washer])
    return Part.makeCompound(parts)


def add(doc, name, label, shape, group=None):
    obj = doc.addObject("Part::Feature", name)
    obj.Label, obj.Shape = label, shape
    if group:
        group.addObject(obj)
    return obj


def retain_stock_shapes(baseline, output):
    # A FreeCAD save can reserialize untouched splines and tread surfaces.
    # Use the original BRep for every retained part except the revised tray and head shell.
    def shape_paths(archive):
        objects = ElementTree.fromstring(archive.read("Document.xml")).findall("./ObjectData/Object")
        result = {}
        for obj in objects:
            shape = obj.find("./Properties/Property[@name='Shape']/Part")
            if shape is not None and shape.get("file"):
                result[obj.get("name")] = shape.get("file")
        return result

    temporary = output.with_suffix(".stock-tmp")
    with ZipFile(baseline) as original, ZipFile(output) as revised, ZipFile(temporary, "w") as saved:
        old, new = shape_paths(original), shape_paths(revised)
        common = (old.keys() & new.keys()) - {"ElectronicsTray", "HeadShell", "PrintHeadShell"}
        copies = {new[name]: old[name] for name in common}
        assert len(copies) == len(common)
        for entry in revised.infolist():
            if entry.filename in copies:
                data = original.read(copies[entry.filename])
            else:
                data = revised.read(entry)
            saved.writestr(entry, data)
    temporary.replace(output)
    return len(common)


def save_revision(doc, path, state):
    # Preserve existing visibility, camera and face materials in headless FreeCAD.
    views = state[0].find("ViewProviderData")
    if len(views) > 1:
        for obj in doc.Objects:
            if views.find(f"ViewProvider[@name='{obj.Name}']") is not None:
                continue
            template = "BreadboardScrew0" if ("Screw" in obj.Name or "Fasteners" in obj.Name) else ("StopBody" if obj.Name.startswith("Speaker") else "UltrasonicPCBEnvelope")
            view = deepcopy(views.find(f"ViewProvider[@name='{template}']"))
            view.set("name", obj.Name)
            view.find("./Properties/Property[@name='Visibility']/Bool").set("value", "true")
            views.append(view)
    path.parent.mkdir(exist_ok=True, parents=True)
    doc.recompute()
    doc.saveAs(str(path))
    App.closeDocument(doc.Name)
    restore(path, state)


def pcb_distance(shape, board):
    bounds = shape.BoundBox
    def lower_bound(solid):
        other = solid.BoundBox
        gaps = [max(0, getattr(bounds, axis + "Min") - getattr(other, axis + "Max"),
                    getattr(other, axis + "Min") - getattr(bounds, axis + "Max")) for axis in "XYZ"]
        return dist((0, 0, 0), gaps)
    nearest = float("inf")
    for limit, solid in sorted(((lower_bound(solid), solid) for solid in board.Solids), key=lambda row: row[0]):
        if limit >= nearest:
            break
        nearest = min(nearest, shape.distToShape(solid)[0])
    return nearest


def assert_hollow(space, objects):
    for obj in objects:
        if space.BoundBox.intersect(obj.Shape.BoundBox):
            overlap = space.common(obj.Shape).Volume
            assert overlap < .001, (obj.Name, overlap)


def check_top_option(doc):
    # This is a fit alternative; no top-facing driver is added to the assembly.
    envelope = box(-22.1, -36, 197.7, 44.2, 32, 15.8)
    ray = Part.makeLine(V(0, -20, 213), V(0, -20, 240))
    roof = doc.PrintCrown.Shape.common(ray).Edges
    assert len(roof) == 1
    return {"front_centre_xyz_mm": [0, -20, 213],
            "expanded_envelope_clearance_to_crown_mm": round(envelope.distToShape(doc.PrintCrown.Shape)[0], 3),
            "expanded_envelope_clearance_to_A1_mm": round(pcb_distance(envelope, doc.MainboardA1.Shape), 3),
            "solid_above_diaphragm_z_range_mm": [roof[0].BoundBox.ZMin, roof[0].BoundBox.ZMax]}


def check_fit(doc):
    head = doc.PrintHeadShell.Shape
    fixed = [o for o in doc.Objects if hasattr(o, "Shape") and not o.isDerivedFrom("App::DocumentObjectGroup")
             and o.Name not in {"SpeakerL", "SpeakerR", "SpeakerFasteners", "MainboardA1", "PrintHeadShell"}]
    a2 = App.openDocument(str(MODEL / "studies/front-camera/CyberTrack-A2-front-camera.FCStd"))
    gaps = {}
    for side in ("L", "R"):
        limit = handed(box(-77, CY - 22.1, CZ - 16, 15.8, 44.2, 32), side)
        assert_hollow(limit, fixed)
        assert head.common(doc.getObject("Speaker" + side).Shape).Volume < .001
        gaps[side] = {name: round(limit.distToShape(doc.getObject(name).Shape)[0], 3) for name in
                      ("PowerCableRoute", "StopSignalRoute", "PrintCrown", "ElectronicsTray")}
        gaps[side]["MainboardA1"] = round(pcb_distance(limit, doc.MainboardA1.Shape), 3)
        gaps[side]["MainboardA2"] = round(pcb_distance(limit, a2.MainboardA2.Shape), 3)
        for name in ("CameraBody", "Ribbon", "FPCWithdrawn", "LatchTool", "TailTool"):
            gaps[side][name] = round(limit.distToShape(a2.getObject(name).Shape)[0], 3)
        assert min(gaps[side].values()) > 0
        for z in PORT_Z:
            # Check a continuous passage with finite cross section, the uncut
            # opaque bar above the inlet and its adjacent original slot.
            channel = [box(-84, -16.5, z-.6, 7.4, 1.2, 1.2),
                       box(-84, -16.5, z-3.1, 1.2, 1.2, 3.7),
                       box(-92, -16.5, z-3.1, 9, 1.2, 1.2)]
            for piece in channel:
                assert head.common(handed(piece, side)).Volume < .001, (side, z)
            shield = handed(box(-86.5, -19, z-.9, 1, 8, 1.8), side)
            assert abs(head.common(shield).Volume - shield.Volume) < .001, (side, z, "grille")
    App.closeDocument(a2.Name)
    frame = doc.ElectronicsTray.Shape
    board = doc.MainboardA1.Shape.Solids
    assert all(solid.common(frame).Volume < .001 for solid in board if frame.BoundBox.intersect(solid.BoundBox))
    for screw in doc.BoardFasteners.Shape.Solids:
        assert all(screw.common(solid).Volume < .001 for solid in board if screw.BoundBox.intersect(solid.BoundBox))
    return {"speakers": 2, "mono_parallel_nominal_ohms": 4, "per_side_clearances_mm": gaps,
            "allowance_each_side_mm": 0.5, "hidden_ports_per_ear": len(PORT_Z),
            "hidden_port_dimensions_mm": [8, 1.8], "existing_grille_paths_checked_per_ear": 3,
            "outer_grilles_unchanged": True, "board_frame_intersection_mm3": 0,
            "board_fastener_intersection_mm3": 0, "listening_test_distances_m": [.3, .5],
            "listening_test_completed": False}


def revise(doc, board, source):
    shape_group = doc.Component if source else None
    for i in range(4):
        old = doc.getObject("BreadboardScrew" + str(i))
        add(doc, "MainboardTrayScrew" + str(i), f"主板框架 · 头壳固定螺钉 {i + 1}",
            old.Shape.copy(), shape_group)
    for name in [o.Name for o in doc.Objects if o.Name.startswith(OBSOLETE)]:
        doc.removeObject(name)
    tray = doc.ElectronicsTray
    tray.Shape, tray.Label = pcb_frame(), "A1 主板 · 四柱开框托架"
    tray.Label2 = "96 × 80 mm A1 主板框架"
    doc.UltrasonicWireSpace.EvidenceBasis = "传感器至头舱侧边的规划走廊，主板 J3 配对插头与余线须在实物上核对。"
    tray.EvidenceBasis = "A1 四个 Ø2.8 孔，板底 Z178，四个框架侧耳复用 PP07 支座。"
    add(doc, "MainboardA1", "定制主 PCB · A1 原生装配 STEP", board, shape_group)
    if source:
        doc.HeadShell.Shape = receiver(doc.HeadShell.Shape)
    doc.PrintHeadShell.Shape = receiver(doc.PrintHeadShell.Shape)
    doc.PrintHeadShell.EvidenceBasis = "左右耳内侧安装座及遮蔽声口；声音经原耳罩条缝排出。"
    for side, label in (("L", "左"), ("R", "右")):
        add(doc, "Speaker" + side, label + "耳 · PUI ASE02808MR-LW150-R", handed(speaker(), side), shape_group)
    hardware = fasteners()
    add(doc, "SpeakerFasteners", "左右扬声器 · 四组紧固件", Part.makeCompound(
        [hardware, handed(hardware, "L")]), shape_group)
    substrate, = [s for s in board.Solids if s.BoundBox.XLength > 95 and s.BoundBox.YLength > 79]
    top = substrate.BoundBox.ZMax
    screws = [vertical(x, y, top - 5, 5, 1.25).fuse(vertical(x, y, top, 1.5, 2.2)) for x, y in BOARD_HOLES]
    add(doc, "BoardFasteners", "A1 主板 · 四颗 Ø2.5 × 5 螺钉候选", Part.makeCompound(screws),
        shape_group)
    doc.recompute()
    valid(tray.Shape)
    valid(doc.PrintHeadShell.Shape)
    valid(doc.SpeakerL.Shape)
    valid(doc.SpeakerR.Shape)


def main(out):
    study = App.openDocument(str(MODEL / "studies/front-camera/CyberTrack-v2-front-camera.FCStd"))
    board = study.MainboardA1.Shape.copy()
    App.closeDocument(study.Name)
    report = {"board": "A1", "speaker_candidate": "PUI ASE02808MR-LW150-R",
              "physical_fit_verified": False, "slicing_validated": False}
    if any(out.iterdir()):
        raise ValueError("The staging directory must be empty")
    for path in ("source/CyberTrack-design.FCStd", "CyberTrack.FCStd"):
        doc = App.openDocument(str(MODEL / path))
        state = capture(MODEL / path)
        exterior = {obj.Name: sha256(obj.Shape.exportBrepToString().encode()).hexdigest()
                    for obj in (doc.PrintCrown,)}
        original = SimpleNamespace(Name="PrintHeadShell", Shape=doc.PrintHeadShell.Shape.copy())
        revise(doc, board, path.startswith("source/"))
        match_face_materials(state, original, doc.PrintHeadShell)
        for delta in (original.Shape.cut(doc.PrintHeadShell.Shape), doc.PrintHeadShell.Shape.cut(original.Shape)):
            for solid in delta.Solids:
                b = solid.BoundBox
                assert max(abs(b.XMax), abs(b.XMin)) <= 82.00001
                assert min(abs(b.XMax), abs(b.XMin)) > 70
                assert b.YMin > -46 and b.YMax < 1 and b.ZMin > 172 and b.ZMax < 205
        save_revision(doc, out / path, state)
        count = retain_stock_shapes(MODEL / path, out / path)
        report.setdefault("byte_identical_retained_shapes", {})[path] = count
        doc = App.openDocument(str(out / path))
        for name, digest in exterior.items():
            assert sha256(doc.getObject(name).Shape.exportBrepToString().encode()).hexdigest() == digest, name
        report.setdefault("original_exterior_brep_sha256", {})[path] = exterior
        assert not any(o.Name.startswith(OBSOLETE) for o in doc.Objects)
        assert len(doc.MainboardA1.Shape.Solids) == 656
        if path.startswith("source/"):
            editable = doc.PrintHeadShell.Shape.copy()
            App.closeDocument(doc.Name)
    assert abs(editable.Volume - doc.PrintHeadShell.Shape.Volume) < 0.001
    report.update(check_fit(doc))
    report["top_firing_alternative"] = check_top_option(doc)
    step = out / "CyberTrack.step"
    objects = [o for o in doc.Objects if hasattr(o, "Shape") and not o.isDerivedFrom("App::DocumentObjectGroup")
               and (getattr(o, "Category", "") not in ("clearance", "envelope")
                    or o.Name in ("WaterHoseRoute", "BubbleGunHoseRoute", "WaterModule", "BubbleModule"))]
    Part.export(objects, str(step))
    exchange = Part.read(str(step))
    assert len(exchange.Solids) == sum(len(o.Shape.Solids) for o in objects)
    report["step_solids"] = len(exchange.Solids)
    prints = out / "print-parts"
    prints.mkdir()
    report["print_exports"] = {}
    for obj, stem in [(doc.PrintHeadShell, "PP07-HeadShell"), (doc.ElectronicsTray, "Head-ElectronicsTray")]:
        report["print_exports"][stem] = export_part(obj.Shape, prints / stem)
        (prints / (stem + ".brep")).unlink()
    solo = App.openDocument(str(MODEL / "print-parts/PP07-HeadShell.FCStd"))
    solo.HeadShell.Shape = print_shape(doc.PrintHeadShell.Shape)[0]
    solo_path = prints / "PP07-HeadShell.FCStd"
    save_revision(solo, solo_path, capture(MODEL / "print-parts/PP07-HeadShell.FCStd"))
    solo = App.openDocument(str(solo_path))
    valid(solo.HeadShell.Shape)
    App.closeDocument(solo.Name)
    App.closeDocument(doc.Name)
    report["projects"] = []
    for rel in ("lean-print/CyberTrack-Lean-6plates.3mf", "print-ready/CyberTrack-Ready-6plates.3mf"):
        target = out / rel
        target.parent.mkdir()
        replacements = {"PP07-Tray.stl": prints / "Head-ElectronicsTray.stl"} if rel.startswith("lean-print/") else {}
        replacements["PP07-upright.stl"] = prints / "PP07-HeadShell.stl"
        row = update(MODEL / rel, destination=target, removed_names=RETIRED_PRINTS, replacements=replacements)
        with ZipFile(target) as archive:
            row["requires_reslice_plates"] = [i for i in range(1, 7) if f"Metadata/plate_{i}.gcode" not in archive.namelist()]
        report["projects"].append(row)
    report["saved_reopened"] = True
    report["files_sha256"] = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()}
    (out / "pcb-speaker-fit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
