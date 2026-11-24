"""Rebuild the A2 service study from the native board's component STEP export."""

import json
import os
import sys
from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui
import Import
import Part
from build_fit import APEX, BOARD_TOP, FACE, HERE, V, X, Z, box, flex_geometry

ORIGIN = V(-48, -67.5, 178)
J17_Y = -40.5
SLOT_Y = J17_Y - 0.62  # Section registration estimate relative to pad array centre.
SEATED_Z = BOARD_TOP + 1.75  # Nominal seating plane for the service model.
LIFT = 6.0
MODEL = HERE / "CyberTrack-A2-front-camera.FCStd"


def add(doc, group, name, label, shape, color, visible=False):
    obj = doc.addObject("Part::Feature", name)
    group.addObject(obj)
    obj.Label = label
    obj.Shape = shape
    obj.ViewObject.ShapeColor = color
    obj.ViewObject.Visibility = visible
    return obj


def build(step):
    Gui.showMainWindow()
    source = App.newDocument("BoardImport")
    Import.insert(str(step.resolve()), source.Name)
    (root,) = source.RootObjects
    (socket,) = [o for o in root.Group if o.Label.startswith("J17~")]
    opened = socket.Shape.copy()
    bounds = opened.BoundBox
    assert abs(bounds.XLength - 15.4) < 0.02 and abs(bounds.ZLength - 5.5) < 0.03
    assert abs(bounds.Center.x - 17) < 0.005 and abs(bounds.Center.y - 27) < 0.005
    opened.translate(ORIGIN)
    # The latch projects towards the rear at full lift on the 180-degree footprint.
    upper = opened.common(box(X - 8, J17_Y - 4, BOARD_TOP + 4.75, 16, 8, 0.12))
    assert upper.BoundBox.Center.y > J17_Y + 0.4, upper.BoundBox

    others = [o for o in root.Group if o != socket and o.Shape.Solids]
    # Some STEP exports substitute a 0.762 mm reference cube for a missing
    # component. Cover those five footprint courtyards at package maximum height.
    packages = {
        "U1": (8.35, 53.8, 19.3, 26.1, 3.5),
        "U12": (34.9, 13.7, 8.2, 8.2, 1.3),
        "U13": (13.9, 36.4, 8.2, 8.2, 1.3),
        "U14": (23.4, 43.4, 8.2, 8.2, 1.3),
        "U15": (31.0, 58.5, 4.0, 4.0, 1.2),
    }
    board_shapes = []
    obstacles = []
    replacements = []
    for o in others:
        name = o.Label.split("~")[0]
        shape = o.Shape.copy()
        bb = shape.BoundBox
        if all(
            abs(length - 0.762) < 0.005
            for length in (bb.XLength, bb.YLength, bb.ZLength)
        ):
            x, y, width, depth, height = packages[name]
            shape = box(x, y, BOARD_TOP - ORIGIN.z, width, depth, height)
            replacements.append(name)
        shape.translate(ORIGIN)
        board_shapes.append(shape)
        for solid in shape.Solids:
            if solid.BoundBox.ZMax > BOARD_TOP + 0.03:
                obstacles.append((name, solid))
    board = Part.makeCompound(board_shapes)
    App.closeDocument(source.Name)
    doc = App.openDocument(str(HERE / "CyberTrack-v2-front-camera.FCStd"))
    doc.Label = "CyberTrack A2 · 右前脸摄像头插拔"
    doc.Head.Label = "头舱与 A2 主板"
    doc.Cable.Label = "原装排线与 J17"
    doc.removeObject("MainboardA1")
    add(
        doc,
        doc.Head,
        "MainboardA2",
        "A2 主板与器件（J17 单列）",
        board,
        (0.16, 0.45, 0.34),
        True,
    )
    doc.removeObject("FutureZIF")
    z = BOARD_TOP
    # Schematic solids for the housing and latch. The independent clearance envelope
    # covers the entire dimensional drawing, including the intermediate position.
    housing = box(X - 7.7, J17_Y - 1.9, z, 15.4, 3.8, 3.1)
    opening = box(X - 6.52, SLOT_Y - 0.27, SEATED_Z - 0.2, 13.04, 0.70, 3.2)
    housing = housing.cut(opening)
    closed = box(X - 6.9, SLOT_Y + 0.46, z + 3.1, 13.8, 1.58, 0.5)
    upright = opened
    add(
        doc,
        doc.Cable,
        "J17Housing",
        "J17 FH12-24S-0.5SVA(54) · 图纸简化外壳",
        housing,
        (0.84, 0.76, 0.60),
        True,
    )
    add(doc, doc.Cable, "J17Closed", "闭锁 · 3.60 mm", closed, (0.26, 0.21, 0.18), True)
    add(
        doc,
        doc.Checks,
        "J17Upright",
        "J17 开锁 · A2 原生 STEP 实体",
        upright,
        (0.26, 0.21, 0.18),
    )
    envelope = box(X - 7.9, J17_Y - 3.0, z + 2.7, 15.8, 6, 3.0)
    add(
        doc,
        doc.Checks,
        "LatchSweep",
        "锁扣全行程保守包络 · 含 0.2 mm 高度余量",
        envelope,
        (0.8, 0.4, 0.1),
    )
    # Tool columns represent two thin blunt tips flanking the latch centre.
    jaws = Part.makeCompound(
        [box(X + dx - 0.5, J17_Y + 1.15, z + 3.59, 1, 1, 58) for dx in (-4.8, 4.8)]
    )
    grip = Part.makeCompound(
        [box(X + dx, SLOT_Y - 0.28, z + 4.7, 0.7, 0.60, 59) for dx in (-7.0, 6.30)]
    )
    add(
        doc,
        doc.Checks,
        "LatchTool",
        "锁扣操作 · 双端各 1 × 1 mm，自上方进入",
        jaws,
        (0.2, 0.6, 0.7),
    )
    add(
        doc,
        doc.Checks,
        "TailTool",
        "补强段两侧夹持 · 上方双薄爪通道",
        grip,
        (0.2, 0.6, 0.7),
    )
    _, _, raw = flex_geometry(apex=APEX, tip_z=SEATED_Z, end_land=4.0)
    seated_apex = APEX + (raw - SLOT_Y) / 2

    def cable(lift):
        ribbon, end, y = flex_geometry(
            apex=seated_apex + lift / 2, tip_z=SEATED_Z + lift, end_land=4.0
        )
        assert abs(y - SLOT_Y) < 1e-7 and ribbon.isValid() and end.isValid()
        return ribbon, end

    ribbon, end = cable(0)
    doc.Ribbon.Shape = ribbon
    doc.TailBacking.Shape = end
    withdraw = Part.makeCompound(list(cable(LIFT)))
    add(
        doc,
        doc.Checks,
        "FPCWithdrawn",
        "排线竖直拔出 6 mm · 等长 R4 路径",
        withdraw,
        (0.8, 0.48, 0.13),
    )
    for obj in doc.Checks.Group:
        obj.ViewObject.Visibility = False
    doc.recompute()
    Gui.activeDocument().activeView().viewAxonometric()
    Gui.activeDocument().activeView().fitAll()
    doc.saveAs(str(MODEL))
    App.closeDocument(doc.Name)

    doc = App.openDocument(str(MODEL))
    zparts = [
        (o.Name, o.Shape)
        for o in doc.Head.Group
        if o.Name not in ("PrintCrown", "MainboardA2")
    ]
    fixed = (
        obstacles
        + zparts
        + [
            (n, doc.getObject(n).Shape)
            for n in ("TrialPP07", "Keeper", "KeeperScrews", "HeatSink", "ThermalPad")
        ]
    )

    def nearest(shape, group):
        best = (float("inf"), "")
        for name, other in group:
            if (shape.BoundBox.Center - other.BoundBox.Center).Length > (
                shape.BoundBox.DiagonalLength + other.BoundBox.DiagonalLength
            ) / 2 + best[0]:
                continue
            d = shape.distToShape(other)[0]
            if d < best[0]:
                best = (d, name)
        return [round(best[0], 4), best[1]]

    local = box(X - 13, J17_Y - 8, z, 26, 16, 68).BoundBox
    nearby = [(n, s) for n, s in fixed if local.intersect(s.BoundBox)]
    shell = [
        (n, s)
        for n, s in fixed
        if n
        in (
            "TrialPP07",
            "UltrasonicRearEnvelope",
            "UltrasonicPCBEnvelope",
            "UltrasonicWireSpace",
            "Keeper",
            "HeatSink",
        )
    ]
    sweep = []
    for i in range(13):
        lift = i * 0.5
        r, b = cable(lift)
        area = r.BoundBox
        area.enlarge(5)
        candidates = [(n, s) for n, s in fixed if area.intersect(s.BoundBox)]
        found = nearest(Part.makeCompound([r, b]), candidates)
        sweep.append([lift, *found])
    clear = {
        n: nearest(doc.getObject(n).Shape, nearby + shell)
        for n in ("J17Housing", "LatchSweep", "LatchTool", "TailTool")
    }
    clear["seated_FPC_to_crown"] = nearest(
        doc.Ribbon.Shape, [("PrintCrown", doc.PrintCrown.Shape)]
    )
    clear["withdrawn_FPC_to_crown"] = nearest(
        doc.FPCWithdrawn.Shape, [("PrintCrown", doc.PrintCrown.Shape)]
    )
    clear["withdrawn_tip_above_latch_envelope"] = round(SEATED_Z + LIFT - (z + 5.7), 4)
    clear["seated_FPC_overlap_open_STEP_mm3"] = round(
        Part.makeCompound([doc.Ribbon.Shape, doc.TailBacking.Shape])
        .common(opened)
        .Volume,
        6,
    )
    clear["grip_to_upright"] = nearest(
        doc.TailTool.Shape, [("J17Upright", doc.J17Upright.Shape)]
    )
    clear["sink_to_A2_components"] = nearest(doc.HeatSink.Shape, obstacles)
    report = {
        "units": "mm",
        "source_STEP_components_or_groups_excluding_J17": len(others),
        "package_envelopes_for_reference_cubes": sorted(replacements),
        "connector": "FH12-24S-0.5SVA(54)",
        "board_xy": [17, 27],
        "board_rotation_deg": 180,
        "J17_pin1_direction": "-X",
        "module_pin1_direction": "+X",
        "module_pin_to_socket_pin": "25 minus module pin",
        "optical_axis_xyz": [X, FACE, Z],
        "board_top_z": z,
        "slot_y_estimate": SLOT_Y,
        "seated_tip_z_estimate": SEATED_Z,
        "fpc_free_length": 62,
        "stiffener_length": 4,
        "static_bend_radius_assumption": 4,
        "seated_apex_z": seated_apex,
        "withdrawal": LIFT,
        "min_clearances_mm_and_neighbor": clear,
        "withdrawal_step_mm_clearance_neighbor": sweep,
        "method": "Saved and reopened FCStd; access from above with crown removed. Drawing-based connector envelope; tool shapes are design allowances. Step samples maintain developed length, with fixed camera end. No physical insertion-force or contact qualification.",
    }
    assert clear["seated_FPC_overlap_open_STEP_mm3"] < 1e-5
    assert all(value[0] > 0 for value in clear.values() if isinstance(value, list))
    assert min(row[1] for row in sweep) > 0
    # The tool tips overlap the stiffener vertically before the cable moves.
    assert SEATED_Z + 4 - (z + 4.7) > 1.0
    (HERE / "a2-service-check.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    )
    print(report, flush=True)
    App.closeDocument(doc.Name)


if __name__ == "__main__":
    build(Path(sys.argv[1]))
    sys.stdout.flush()
    os._exit(0)
