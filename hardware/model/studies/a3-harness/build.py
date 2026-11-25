"""Run with FreeCAD Python. Dimensions and clearances are in millimetres."""
from copy import deepcopy
import hashlib
import json
from math import sqrt
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from pathlib import Path
import sys

import FreeCAD as App
import Part
import Import

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(HERE.parent / "front-camera"))
from build_fit import camera_shell
from water_gun_mount import rounded_route
from cad_gui_state import capture, read_material_list, restore, write_material_list

ORIGINAL = [(0, 6, 84), (0, 6, 166), (60, 6, 166), (60, 6, 194)]
A3 = [(0, 6, 84), (0, 6, 159), (63, 9, 159), (63, 9, 197)]
PARTS = ("KeelLid", "NeckCableBridge", "PrintNeck", "PrintHeadShell", "ElectronicsTray")
GROUPS = [
    ("J8/J10", 4, 2.10), ("J11/J12", 4, 1.60), ("J13/J14", 4, 1.42),
    ("J6/J9/J16", 6, 1.20), ("J18/J19", 8, 0.80),
]
SOURCE = ROOT / "hardware/model/CyberTrack.FCStd"


def contacts(shape, obstacles):
    hits = {}
    for name, solid in obstacles.items():
        if shape.BoundBox.intersect(solid.BoundBox):
            volume = shape.common(solid).Volume
            if volume > 0.01:
                hits[name] = round(volume, 3)
    return hits


def feature(doc, name, label, shape):
    obj = doc.addObject("Part::Feature", name)
    obj.Label = label
    obj.Shape = shape


def inspect_board(study, gauge, obstacles, report):
    package = ROOT / "hardware/pcb/CyberTrack-A3-STEP.zip"
    with TemporaryDirectory() as folder, ZipFile(package) as archive:
        step = archive.extract("CyberTrack-A3.step", folder)
        source = App.newDocument("A3BoardSource")
        Import.insert(step, source.Name)
    root, = source.RootObjects
    board = {}
    for obj in root.Group:
        name = obj.Label.split("~")[0]
        solid = obj.Shape.copy()
        solid.translate(App.Vector(-48, -67.5, 178))
        board[name] = solid
    App.closeDocument(source.Name)
    scene = {k: v for k, v in obstacles.items() if k != "MainboardA1"}
    new_parts = {"U19", "U20", "U21", "J18", "J19", "J20", "J21", "R35", "C41"}
    new_parts.update(f"R{i}" for i in range(55, 60))
    new_parts.update(f"C{i}" for i in range(60, 67))
    report["a3_step_sha256"] = hashlib.sha256(package.read_bytes()).hexdigest()
    report["a3_new_and_moved_parts_contact_mm3"] = {
        r: hits for r in sorted(new_parts) if (hits := contacts(board[r], scene))
    }
    report["gauge_to_a3_board_contacts_mm3"] = contacts(gauge, board)
    assert not report["a3_new_and_moved_parts_contact_mm3"] and not report["gauge_to_a3_board_contacts_mm3"]
    report["encoder_plug_checks"] = {}
    for ref in ("J18", "J19"):
        bounds = board[ref].BoundBox
        # Budget the 7 mm wide four-way housing plus side clearance and a vertical extraction stroke.
        service = Part.makeBox(5, 8, 12, App.Vector(bounds.Center.x - 2.5, bounds.Center.y - 4, bounds.ZMax))
        hits = contacts(service, scene) | contacts(service, {k: v for k, v in board.items() if k != ref})
        assert not hits, (ref, hits)
        report["encoder_plug_checks"][ref] = {"envelope_xyz_mm": [5, 8, 12], "contacts_mm3": hits}
        feature(study, ref + "Service", ref + " 插头与上拔余量", service)
    camera = App.openDocument(str(HERE.parent / "front-camera/CyberTrack-A2-front-camera.FCStd"))
    changed = {k: board[k] for k in new_parts}
    report["a2_camera_service_contacts_with_new_parts_mm3"] = {
        n: contacts(camera.getObject(n).Shape, changed)
        for n in ("J17Housing", "LatchSweep", "LatchTool", "TailTool", "Ribbon", "TailBacking", "FPCWithdrawn")
    }
    assert not any(report["a2_camera_service_contacts_with_new_parts_mm3"].values())
    App.closeDocument(camera.Name)
    # Keep the routing study compact. The complete assembly is in the separate STEP.
    shown = sorted(new_parts | {"Board", "J8", "J9", "J10", "J11", "J12", "J13", "J14", "J16", "J17"})
    feature(study, "BoardAndConnectors", "A3 板框、接口与运动反馈器件", Part.makeCompound([board[k] for k in shown]))


def save_views(path):
    state, assets = capture(SOURCE)
    providers = state.find("ViewProviderData")
    originals = {v.get("name"): v for v in providers}
    styles = {"Gauge14": "PowerCableRoute", "BoardAndConnectors": "MainboardA1",
              "J18Service": "StopSignalRoute", "J19Service": "StopSignalRoute"}
    for name, source in styles.items():
        view = deepcopy(originals[source])
        view.set("name", name)
        providers.append(view)
    visible = {"NeckCableBridge", "Gauge14", "BoardAndConnectors", "ElectronicsTray"}
    for view in providers:
        name = view.get("name")
        if name not in (*PARTS, *styles):
            continue
        props = view.find("Properties")
        props.find("Property[@name='Visibility']/Bool").set("value", str(name in visible).lower())
        material = props.find("Property[@name='ShapeAppearance']/MaterialList")
        key = f"A3-{name}-appearance"
        assets[key] = write_material_list(read_material_list(assets[material.get("file")])[:1])
        material.set("file", key)
    state.find("Camera").set("settings", "OrthographicCamera { position 144.34 -162.34 291.34 "
                             "orientation 0.707107 0.707107 0 0.955317 focalDistance 250 "
                             "nearDistance 50 farDistance 480 height 170 }")
    restore(path, (state, assets))


def build():
    base = App.openDocument(str(SOURCE))
    obstacles = {
        o.Name: o.Shape for o in base.Objects
        if hasattr(o, "Shape") and not o.Shape.isNull()
        and getattr(o, "Category", "") != "clearance"
        and o.Name not in ("PowerCableRoute", "StopSignalRoute")
    }
    report = {"source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              "frame": "+X left, +Y aft, +Z up", "upper_trunk_wires": GROUPS,
              "count": sum(q for _, q, _ in GROUPS), "stock_intersections_mm3": {}}
    areas = sum(q * od**2 for _, q, od in GROUPS)
    report["sizing"] = [
        {"packing": f, "bare_bundle_mm": round(sqrt(areas/f), 2),
         "jacketed_mm": round(sqrt(areas/f) + .8, 2),
         "minimum_service_bore_mm": round(sqrt(areas/f) + .8 + 1.5, 2)}
        for f in (.55, .65, .75)
    ]
    report["chassis_box_trials_mm3"] = {}
    for cy, z in [(-57, 54), (-35, 69.5)]:
        # Board and fitted devices bounded by a horizontal service-free box, without cable tails.
        envelope = Part.makeBox(96, 80, 18.5, App.Vector(-48, cy - 40, z))
        report["chassis_box_trials_mm3"][f"center_xy_0_{cy}_bottom_z_{z}"] = contacts(envelope, obstacles)
    for d in (10, 12, 14):
        report["stock_intersections_mm3"][d] = contacts(rounded_route(ORIGINAL, d/2, 10), obstacles)
    gauge = rounded_route(A3, 7, 28)
    cutter = rounded_route(A3, 7.25, 28)
    report["proposed_path_xyz"] = A3
    report["centerline_bend_radius_mm"] = 28
    report["bore_mm"] = 14.5
    report["gauge_mm"] = 14
    report["before_changes_mm3"] = contacts(gauge, obstacles)
    study = App.newDocument("A3Harness")
    feature(study, "Gauge14", "Ø14 连续通规 · 底盘汇合点至头舱分线点", gauge)
    shapes = {}
    for name in PARTS:
        old = obstacles[name]
        blank = old
        if name == "PrintHeadShell":
            blank = camera_shell(old)
        elif name == "NeckCableBridge":
            blank = old.fuse(Part.makeCylinder(9, 2, App.Vector(0, 6, 107)))
        part = blank.cut(cutter).removeSplitter()
        if name == "PrintNeck" and len(part.Solids) == 2:
            # Widening the saddle detaches the tip of the old bore wall.
            retained, chip = sorted(part.Solids, key=lambda s: s.Volume, reverse=True)
            assert chip.Volume < 2 and cutter.BoundBox.intersect(chip.BoundBox)
            report["removed_detached_saddle_tip_mm3"] = round(chip.Volume, 3)
            part = retained
        assert part.isValid() and len(part.Solids) == len(old.Solids), name
        obstacles[name] = part
        shapes[name] = {"solids": len(part.Solids), "net_volume_change_mm3": round(part.Volume-old.Volume, 2)}
        feature(study, name, base.getObject(name).Label, part)
    report["revised_parts"] = shapes
    report["after_changes_mm3"] = contacts(gauge, obstacles)
    assert not report["after_changes_mm3"], report["after_changes_mm3"]
    report["minimum_to_board_hardware_mm"] = {
        name: round(obstacles[name].distToShape(gauge)[0], 2)
        for name in ("MainboardA1", "BoardFasteners", "SpeakerL", "SpeakerR")
    }
    inspect_board(study, gauge, obstacles, report)
    study.recompute()
    path = HERE / "CyberTrack-A3-neck.FCStd"
    study.saveAs(str(path))
    App.closeDocument(study.Name)
    save_views(path)
    check = App.openDocument(str(path))
    assert all(check.getObject(n).Shape.isValid() for n in (*PARTS, "Gauge14", "BoardAndConnectors"))
    camera = App.openDocument(str(HERE.parent / "front-camera/CyberTrack-A2-front-camera.FCStd"))
    shell = check.PrintHeadShell.Shape
    # Enclose the window, seat and both keeper pilots, clear of later ear and neck changes.
    region = Part.makeBox(26, 25, 24, App.Vector(-45, -96, 177))
    reference = camera.TrialPP07.Shape.common(region)
    actual = shell.common(region)
    report["camera_mount_difference_from_a2_mm3"] = round(
        actual.cut(reference).Volume + reference.cut(actual).Volume, 6)
    report["camera_shell_contacts_mm3"] = contacts(shell, {
        n: camera.getObject(n).Shape for n in ("OpticalCone", "CameraBody", "Keeper", "Ribbon")
    })
    assert report["camera_mount_difference_from_a2_mm3"] < 0.01 and not report["camera_shell_contacts_mm3"]
    assert not contacts(check.Gauge14.Shape, {"PrintHeadShell": shell})
    App.closeDocument(camera.Name)
    App.closeDocument(check.Name)
    (HERE / "clearance.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(report["sizing"], shapes, report["minimum_to_board_hardware_mm"])


if __name__ == "__main__":
    build()
