"""Compare a 75 mm DVP module procurement envelope to the saved front-face study."""

import json
import math
import os
import sys

from build_fit import (
    App,
    Gui,
    Part,
    HERE,
    V,
    Y,
    X,
    Z,
    FACE,
    BOARD_TOP,
    axial,
    box,
    flex_geometry,
)

OUTPUT = HERE / "CyberTrack-v2-OV2640-envelope.FCStd"
HEAD, DEPTH, APEX = 9.0, 6.0, 205.0
BACK = FACE + DEPTH


def build():
    Gui.showMainWindow()
    doc = App.openDocument(str(HERE / "CyberTrack-v2-front-camera.FCStd"))
    doc.Label = "CyberTrack v2 · OV2640 75 mm 条件试装"
    # Enlarge the locating pocket and FPC relief around the original optical axis.
    pocket = box(X - 4.75, FACE + 1, Z - 4.75, 9.5, 8, 9.5)
    exit_slot = box(X - 4.25, BACK - 1.5, Z + 3.5, 8.5, 3, 4)
    shell = doc.TrialPP07.Shape.cut(pocket).cut(exit_slot)
    for x, z in [(X - 8.4, Z + 1), (X + 2.3, Z - 7.4)]:
        boss = axial(2.3, BACK - 0.61, 0.61, x, z).cut(
            axial(0.8, BACK - 0.62, 0.63, x, z)
        )
        shell = shell.fuse(boss)
    doc.TrialPP07.Shape = shell.removeSplitter()
    doc.TrialPP07.Label = "PP07 · 9.50 mm 试装座"
    # Square fixed housing begins 1 mm behind the pupil datum; nose is cylindrical.
    doc.CameraBody.Shape = box(
        X - HEAD / 2, FACE + 1, Z - HEAD / 2, HEAD, DEPTH - 1, HEAD
    ).fuse(axial(3.8, FACE, 1))
    doc.CameraBody.Label = "采购边界 · 方框 9 × 9 / 总深 6 / 鼻端 Ø7.6"
    for name in ["Keeper", "KeeperScrews", "HeatSink", "ThermalPad"]:
        obj = doc.getObject(name)
        shape = obj.Shape.copy()
        shape.translate(V(0, DEPTH - 5.4, 0))
        obj.Shape = shape
    doc.Keeper.Shape = doc.Keeper.Shape.cut(
        box(X - 4.25, BACK - 0.1, Z + 3.5, 8.5, 2.1, 4)
    )
    doc.Camera.Label = "03 定焦头部与散热预留包络"
    doc.HeatSink.Label = "另计选装散热片 · 温测前预留"
    ribbon, tail, end = flex_geometry(75, HEAD, BACK - 0.06, APEX, 8)
    doc.Ribbon.Shape = ribbon
    doc.Ribbon.Label = "75 mm 总展开假设 · 8 mm 颈宽 · 两处 R4"
    doc.TailBacking.Shape = tail
    housing = box(X - 7.7, end - 2.75, BOARD_TOP, 15.4, 5.5, 4.85)
    slot = box(X - 6.55, end - 0.30, 180.8, 13.1, 0.67, 5)
    doc.FutureZIF.Shape = housing.cut(slot)
    doc.FutureZIF.Label = "Hirose 顶插座 · 含外壳余量，插口简化"
    slope = math.tan(math.radians(33))
    doc.OpticalCone.Shape = Part.makeCone(
        3.9 + 14 * slope, 3.9, 14, V(X, FACE - 14, Z), Y
    )
    doc.OpticalCone.Label = "66° 检查体 · 视场轴定义待确认"
    doc.recompute()
    doc.saveAs(str(OUTPUT))
    App.closeDocument(doc.Name)
    check(end)


def check(end):
    doc = App.openDocument(str(OUTPUT))
    parts = [
        "CameraBody",
        "HeatSink",
        "ThermalPad",
        "Keeper",
        "KeeperScrews",
        "Ribbon",
        "TailBacking",
        "FutureZIF",
        "OpticalCone",
    ]
    refs = [o.Name for o in doc.Head.Group] + ["TrialPP07"]

    def shape(name):
        return doc.getObject(name).Shape

    board = shape("MainboardA1").Solids
    overlaps = {}
    for i, name in enumerate(parts):
        a = shape(name)
        assert a.isValid() and a.Solids, name
        for other in refs + parts[i + 1 :]:
            candidates = board if other == "MainboardA1" else [shape(other)]
            volume = sum(
                a.common(s).Volume
                for s in candidates
                if a.BoundBox.intersect(s.BoundBox)
            )
            if volume > 1e-5:
                overlaps[name + "/" + other] = round(volume, 5)
    assert set(overlaps) == {"KeeperScrews/TrialPP07"}, overlaps
    for name in ["TrialPP07", "Keeper"]:
        assert shape(name).isValid() and len(shape(name).Solids) == 1, name
    seat = shape("TrialPP07").cut(shape("UncutPP07"))
    for other in doc.Head.Group:
        if seat.BoundBox.intersect(other.Shape.BoundBox):
            assert seat.common(other.Shape).Volume < 1e-5, other.Name
    gaps = {
        a + "/" + b: round(shape(a).distToShape(shape(b))[0], 3)
        for a, b in [
            ("Ribbon", "PrintCrown"),
            ("OpticalCone", "UltrasonicRingR"),
            ("Keeper", "UltrasonicRearEnvelope"),
        ]
    }
    bounds = shape("FutureZIF").BoundBox
    bounds.enlarge(3)
    adjacent = [
        s
        for s in board
        if s.BoundBox.ZMax > BOARD_TOP + 0.01 and bounds.intersect(s.BoundBox)
    ]
    gaps["FutureZIF/adjacent_A1_components"] = round(
        min(shape("FutureZIF").distToShape(s)[0] for s in adjacent), 3
    )
    report = dict(
        units="mm",
        model="procurement envelope, supplier tolerances unverified",
        lens_xyz=[X, FACE, Z],
        head_envelope=[HEAD, HEAD, DEPTH],
        pocket=9.5,
        module_developed_length_assumed=75,
        neck_width_assumed=8,
        bend_radius_assumed=4,
        zif_envelope=[15.4, 5.5, 4.85],
        tip_xyz=[X, round(end, 3), 180.9],
        optical_cone_full_angle_deg=66,
        checked_parts=parts,
        checked_context=refs,
        clearance_mm=gaps,
        overlap_mm3=overlaps,
    )
    (HERE / "ov2640-fit.json").write_text(json.dumps(report, indent=2) + "\n")
    App.closeDocument(doc.Name)


if __name__ == "__main__":
    build()
    if sys.argv[0].endswith("build_ov2640.py"):
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
