"""Build the camera trial in assembly coordinates with FreeCAD's bundled Python."""

import json
import math
import os
import sys
import tempfile
import zipfile
from pathlib import Path

import FreeCAD as App
import Part

HERE = Path(__file__).resolve().parent
HARDWARE = HERE.parents[2]
V = App.Vector
Y = V(0, 1, 0)
X = -31.0
Z = 190.0
FACE = -80.0
BACK = FACE + 5.4
FLEX_Y = BACK - 0.06
APEX = 203.5
RADIUS = 4.0
TIP_Z = 180.9
BOARD_TOP = 179.69369
BOSSES = [(X - 8.4, Z + 1.0), (X + 2.3, Z - 7.4)]
# The drawing does not specify which axis its 69° field describes.
FOV_SLOPE = math.tan(math.radians(69 / 2))


def box(x, y, z, width, depth, height):
    return Part.makeBox(width, depth, height, V(x, y, z))


def axial(radius, y, length, x=X, z=Z):
    return Part.makeCylinder(radius, length, V(x, y, z), Y)


def camera_shell(shell):
    # The shell receives the seat on its existing inner wall. The front shoulder
    # captures the fixed frame, leaving the motor/lens nose free in the aperture.
    seat = box(X - 6, -79.9, Z - 6.3, 12, 5.55, 12.6)
    seat = seat.multiFuse(
        [axial(2.3, -79.9, 5.55, x, z) for x, z in BOSSES]
        + [box(X - 8.4, -79.9, Z - 0.6, 3.5, 5.55, 3.2)]
    )
    socket = box(X - 4.48, -79.0, Z - 4.48, 8.96, 8.0, 8.96)
    exit_slot = box(X - 3.65, BACK - 0.65, Z + 3.5, 7.3, 2, 4)
    bore = Part.makeCone(4.15 + 12 * FOV_SLOPE, 4.15, 12, V(X, FACE - 12, Z), Y)
    window = bore.fuse(axial(4.15, FACE, 2.0))
    pilots = [axial(0.8, -77.9, 4.1, x, z) for x, z in BOSSES]
    cut_tools = window.multiFuse([socket, exit_slot] + pilots)
    formed = shell.fuse(seat).cut(cut_tools).removeSplitter()
    # Relieve the seat to the fixed rear face of the camera and the screw bosses.
    return formed.cut(box(X - 11, BACK, Z - 10, 18, 2.1, 16.4)).removeSplitter()


def flex_geometry(length=70.5, head=8.5, flex_y=FLEX_Y, apex=APEX, width=6.0,
                  tip_z=TIP_Z, end_land=3.5):
    # Neutral line leaves the camera upwards. Both 90° bends are cylindrical,
    # so the ribbon never twists or bends in its own plane.
    z0 = Z + head / 2
    zb = apex - RADIUS
    flat = length - head - (zb - z0) - (zb - tip_z) - math.pi * RADIUS
    y1 = flex_y + RADIUS
    y2 = y1 + flat
    end = y2 + RADIUS
    half = 0.06

    def arc(cy, a, b, radius):
        def point(t):
            t = math.radians(t)
            return V(
                X - width / 2, cy + radius * math.cos(t), zb + radius * math.sin(t)
            )

        return Part.Arc(point(a), point((a + b) / 2), point(b)).toShape()

    def bend(cy, a, b):
        out = arc(cy, a, b, RADIUS + half)
        inner = arc(cy, b, a, RADIUS - half)
        p, q = out.Vertexes
        r, s = inner.Vertexes
        wire = Part.Wire(
            [
                out,
                Part.makeLine(q.Point, r.Point),
                inner,
                Part.makeLine(s.Point, p.Point),
            ]
        )
        return Part.Face(wire).extrude(V(width, 0, 0))

    shoulder = 2.0
    stem = box(X - width / 2, flex_y - half, z0, width, 2 * half, zb - z0)
    top = box(X - width / 2, y1, apex - half, width, flat, 2 * half)
    down = box(
        X - width / 2,
        end - half,
        tip_z + end_land + shoulder,
        width,
        2 * half,
        zb - tip_z - end_land - shoulder,
    )
    points = [
        V(X + dx, end - half, tip_z + dz)
        for dx, dz in [
            (-6.25, 0),
            (6.25, 0),
            (6.25, end_land),
            (width / 2, end_land + shoulder),
            (-width / 2, end_land + shoulder),
            (-6.25, end_land),
        ]
    ]
    tail = Part.Face(Part.makePolygon(points + [points[0]])).extrude(V(0, 2 * half, 0))
    ribbon = stem.multiFuse(
        [bend(y1, 180, 90), top, bend(y2, 90, 0), down, tail]
    ).removeSplitter()
    stiffener = box(X - 6.25, end + half, tip_z, 12.5, 0.18, end_land)
    return ribbon, stiffener, end


def calculate():
    source = App.openDocument(str(HARDWARE / "model/CyberTrack.FCStd"))
    names = [
        "PrintHeadShell",
        "PrintCrown",
        "ElectronicsTray",
        "UltrasonicPCBEnvelope",
        "UltrasonicRearEnvelope",
        "UltrasonicTopConnector",
        "UltrasonicWireSpace",
        "UltrasonicRingL",
        "UltrasonicRingR",
        "UltrasonicFaceL",
        "UltrasonicFaceR",
        "CrownScrewRFront",
        "WaterHoseRoute",
        "BubbleGunHoseRoute",
        "PowerCableRoute",
        "StopSignalRoute",
    ]
    parts = {name: source.getObject(name).Shape.copy() for name in names}
    App.closeDocument(source.Name)
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(HARDWARE / "pcb/CyberTrack-A1-STEP.zip") as archive:
            filename = archive.extract("CyberTrack-A1.step", tmp)
        board = Part.read(filename)
    board.translate(V(-48, -67.5, 178))
    parts["MainboardA1"] = board
    return parts


def build():
    import FreeCADGui as Gui

    Gui.showMainWindow()
    refs = calculate()
    doc = App.newDocument("FrontCamera")
    doc.Label = "CyberTrack v2 · 右前脸摄像头试装"

    def group(name, label):
        obj = doc.addObject("App::DocumentObjectGroup", name)
        obj.Label = label
        return obj

    assembly = group("Head", "01 头舱与 A1 主板")
    mount = group("Mount", "02 开窗、固定座与压片")
    module = group("Camera", "03 Seeed 114993115 与热界面")
    flex = group("Cable", "04 排线与下一版连接器占位")
    guides = group("Checks", "05 检查几何（按需显示）")

    def feature(parent, name, label, shape, color, visible=True):
        if shape.isNull() or not shape.isValid() or not shape.Solids:
            raise ValueError("Invalid solid: " + name)
        obj = doc.addObject("Part::Feature", name)
        obj.Label = label
        obj.Shape = shape
        parent.addObject(obj)
        obj.ViewObject.ShapeColor = color
        obj.ViewObject.DisplayMode = "Flat Lines"
        obj.ViewObject.Visibility = visible
        return obj

    shell = refs.pop("PrintHeadShell")
    slate = (0.35, 0.42, 0.5)
    for name, s in refs.items():
        feature(
            assembly,
            name,
            "A1 已发布工程板" if name == "MainboardA1" else name,
            s,
            (0.16, 0.45, 0.34) if name == "MainboardA1" else slate,
            name
            not in (
                "PrintCrown",
                "WaterHoseRoute",
                "BubbleGunHoseRoute",
                "PowerCableRoute",
                "StopSignalRoute",
                "UltrasonicWireSpace",
            ),
        )
    formed = camera_shell(shell)
    shell_obj = feature(
        mount, "TrialPP07", "PP07 试装版 · 喇叭口与一体座", formed, slate
    )
    shell_obj.ViewObject.Transparency = 55
    feature(guides, "UncutPP07", "原 PP07 对照", shell, slate, False)
    fov = Part.makeCone(3.9 + 14 * FOV_SLOPE, 3.9, 14, V(X, FACE - 14, Z), Y)
    feature(guides, "OpticalCone", "69° 光路检查体", fov, (0.99, 0.8, 0.2), False)
    body = box(X - 4.25, -79.0, Z - 4.25, 8.5, 4.4, 8.5).fuse(axial(3.8, FACE, 1))
    feature(
        module,
        "CameraBody",
        "8.5 × 8.5 · 固定框与 AF 前端简化",
        body,
        (0.16, 0.16, 0.19),
    )
    # The open rear fork bears on the fixed rear perimeter.
    # The two arms stay clear of the small sink and the upward FPC exit.
    cap = box(X - 8.4, BACK, Z - 5.6, 13.7, 1.8, 11.2)
    cap = cap.multiFuse(
        [axial(2.3, BACK, 1.8, x, z) for x, z in BOSSES]
        + [box(X + 0.7, BACK, Z - 7.4, 3.2, 1.8, 2.2)]
    )
    cap = cap.cut(box(X - 3.7, BACK - 0.1, Z - 3.7, 7.4, 2.0, 10))
    cap = cap.cut(
        Part.makeCompound([axial(1.1, BACK - 0.1, 2, x, z) for x, z in BOSSES])
    ).removeSplitter()
    feature(mount, "Keeper", "可拆后压片 · FPC 上出槽", cap, (0.23, 0.65, 0.69))
    screws = Part.makeCompound(
        [
            axial(1.0, BACK - 3.2, 5, x, z).fuse(axial(1.75, BACK + 1.8, 1.2, x, z))
            for x, z in BOSSES
        ]
    )
    feature(
        mount,
        "KeeperScrews",
        "2 × ST2 × 5 螺钉包络（候选）",
        screws,
        (0.72, 0.75, 0.77),
    )
    tape = box(X - 3.5, BACK, Z - 3, 7, 0.15, 6)
    sink = box(X - 3.5, BACK + 0.15, Z - 3, 7, 7, 6)
    feature(module, "ThermalPad", "0.15 mm 导热胶层假设", tape, (0.88, 0.84, 0.8))
    feature(module, "HeatSink", "7 × 6 × 7 散热片外包络", sink, (0.65, 0.68, 0.74))
    ribbon, stiffener, end_y = flex_geometry()
    feature(
        flex, "Ribbon", "70.5 mm 展开总长 · 两处 R4 转弯", ribbon, (0.87, 0.46, 0.14)
    )
    feature(
        flex, "TailBacking", "排线插端补强 · 总厚 0.30 mm", stiffener, (0.25, 0.45, 0.7)
    )
    connector = box(X - 7.55, end_y - 1.48, BOARD_TOP, 15.1, 3.0, 3.0)
    connector = connector.cut(box(X - 6.55, end_y - 0.30, TIP_Z - 0.1, 13.1, 0.67, 3.0))
    feature(
        flex,
        "FutureZIF",
        "下一版顶插 24P ZIF 空间 · A1 未装",
        connector,
        (0.9, 0.84, 0.68),
    )
    doc.recompute()
    Gui.activeDocument().activeView().viewAxonometric()
    Gui.activeDocument().activeView().fitAll()
    doc.saveAs(str(HERE / "CyberTrack-v2-front-camera.FCStd"))
    App.closeDocument(doc.Name)
    verify(end_y)


def verify(end_y):
    path = HERE / "CyberTrack-v2-front-camera.FCStd"
    doc = App.openDocument(str(path))

    def shape(name):
        return doc.getObject(name).Shape

    live = [
        "CameraBody",
        "HeatSink",
        "ThermalPad",
        "Keeper",
        "KeeperScrews",
        "Ribbon",
        "TailBacking",
        "FutureZIF",
    ]
    refs = [o.Name for o in doc.Head.Group]
    board_solids = shape("MainboardA1").Solids
    hits = {}
    for i, name in enumerate(live):
        a = shape(name)
        for other in refs + ["TrialPP07", "OpticalCone"] + live[i + 1 :]:
            b = shape(other)
            if not a.BoundBox.intersect(b.BoundBox):
                continue
            if other == "MainboardA1":
                near = [s for s in board_solids if s.BoundBox.intersect(a.BoundBox)]
                if not near:
                    continue
                b = Part.makeCompound(near)
            volume = a.common(b).Volume
            if volume > 1e-5:
                hits[f"{name}/{other}"] = round(volume, 5)
    for name in ["TrialPP07", "Keeper"]:
        assert len(shape(name).Solids) == 1 and shape(name).isValid(), name
    optical = shape("OpticalCone").common(shape("TrialPP07")).Volume
    unexpected = {k: v for k, v in hits.items() if k != "KeeperScrews/TrialPP07"}
    for name in refs:
        target = shape(name)
        cone = shape("OpticalCone")
        if (
            cone.BoundBox.intersect(target.BoundBox)
            and cone.common(target).Volume > 1e-5
        ):
            raise ValueError("Blocked sightline: " + name)
    if unexpected or optical > 1e-5 or "KeeperScrews/TrialPP07" not in hits:
        raise ValueError((hits, optical))
    pairs = [
        ("Keeper", "UltrasonicRearEnvelope"),
        ("Ribbon", "PrintCrown"),
        ("HeatSink", "UltrasonicRearEnvelope"),
        ("OpticalCone", "UltrasonicRingR"),
    ]
    clearances = {
        f"{a}/{b}": round(shape(a).distToShape(shape(b))[0], 3) for a, b in pairs
    }
    sink = shape("HeatSink")
    near = sink.BoundBox
    near.enlarge(10)
    clearances["HeatSink/MainboardA1"] = round(
        min(sink.distToShape(b)[0] for b in board_solids if near.intersect(b.BoundBox)),
        3,
    )

    connector = shape("FutureZIF")
    nearby = connector.BoundBox
    nearby.enlarge(3)
    neighbors = [
        s
        for s in board_solids
        if s.BoundBox.ZMax > BOARD_TOP + 0.01 and nearby.intersect(s.BoundBox)
    ]
    clearances["FutureZIF/adjacent_A1_components"] = round(
        min(connector.distToShape(s)[0] for s in neighbors), 3
    )
    axis = Part.makeLine(V(X, FACE - 30, Z), V(X, BACK + 2, Z))
    wall = shape("UncutPP07").common(axis).BoundBox
    recess = FACE - wall.YMin
    seat = shape("TrialPP07").cut(shape("UncutPP07"))
    for name in refs:
        target = shape(name)
        if (
            seat.BoundBox.intersect(target.BoundBox)
            and seat.common(target).Volume > 1e-5
        ):
            raise ValueError("Camera seat interference: " + name)

    report = {
        "units": "mm",
        "lens_center_xyz": [X, FACE, Z],
        "fov_full_angle_deg": 69,
        "lens_recess_from_original_wall": round(recess, 3),
        "window_throat_diameter": 8.3,
        "window_diameter_at_outer_wall_plane": round(
            8.3 + 2 * recess * math.tan(math.radians(34.5)), 3
        ),
        "fpc_developed_module_length": 70.5,
        "fpc_exposed_length": 62.0,
        "fpc_neutral_bend_radius": RADIUS,
        "assumed_future_zif_tip_xyz": [X, round(end_y, 3), TIP_Z],
        "pcb_solid_count": len(shape("MainboardA1").Solids),
        "clearances_mm": clearances,
        "checked_shapes": live,
        "checked_context": refs,
        "overlap_mm3": hits,
        "optical_cone_shell_overlap_mm3": round(optical, 6),
        "pp07_solid_count": len(shape("TrialPP07").Solids),
        "keeper_solid_count": len(shape("Keeper").Solids),
    }
    (HERE / "fit-check.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    )
    App.closeDocument(doc.Name)


if __name__ == "__main__":
    build()
    # Embedded FreeCAD GUI teardown can crash after native documents are closed.
    # Follow the project's CLI exporters; leave the interactive application running.
    if (
        Path(sys.executable).name.startswith("python")
        and Path(sys.argv[0]).resolve() == Path(__file__).resolve()
    ):
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
