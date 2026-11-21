"""Remove the legacy spark geometry from copies of the v1 FreeCAD files.

Run with FreeCAD Python, passing a scratch directory. Place the v1 source and delivery files
and the three historical snapshots in its baseline/ subdirectory.
The snapshots are front-before (f3a5d45), front-after (2137e10) and
backpack-before (5b120d2), each from hardware/model/CyberTrack.FCStd. Review the
readback before copying the outputs over the production models.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sys

import FreeCAD as App
import Mesh
import MeshPart
import Part

from cad_gui_state import capture, read_material_list, restore, write_material_list

V = App.Vector
TOL = 0.01
REMOVED = ("FrontEffect", "FrontIgnitionRouting", "IgnitionRoute", "IgnitionMOS",
           "BackpackArc", "ArcBottomPad", "CrownEffect")
EDITED_PRINTS = ("PrintLowerTub", "PrintBackpack", "PrintChestGuardL",
                 "PrintChestGuardR", "KeelLid", "PrintCrown")
EDITED_GEOMETRY = (*EDITED_PRINTS, "LowerTub", "ChestGuardL", "ChestGuardR",
                   "BackpackShell", "CrownFinL", "CrownFinR")


def valid(shape):
    assert shape.isValid() and len(shape.Solids) == 1


def changed_volume(a, b):
    return a.cut(b).Volume + b.cut(a).Volume


def changes(doc, reference, drilled, unmounted):
    for name in ("LowerTub", "ChestGuardL", "ChestGuardR"):
        assert changed_volume(doc.getObject(name).Shape, drilled.getObject(name).Shape) < TOL
        doc.getObject(name).Shape = reference.getObject(name).Shape.copy()
    lid = doc.KeelLid
    mounts = drilled.KeelLid.Shape.cut(reference.KeelLid.Shape)
    assert abs(lid.Shape.common(mounts).Volume - mounts.Volume) < TOL
    lid.Shape = lid.Shape.cut(mounts).removeSplitter()
    doc.BackpackShell.Shape = unmounted.BackpackShell.Shape.copy()
    doc.BackpackShell.Label = "背包 · 开放式清水瓶护舱"
    doc.PrintBackpack.Label = "PP03 背包及清水瓶护舱"
    for obj in (doc.BackpackShell, doc.PrintBackpack):
        obj.EvidenceBasis = "v2 取消双侧模块桶座，沿用清水瓶固定和上取路径。"
    doc.PrintCrown.Shapes = [obj for obj in doc.PrintCrown.Shapes
                             if not obj.Name.startswith("CrownEffect")]
    for side, x in (("L", 51.5), ("R", -51.5)):
        guard = doc.getObject("PrintChestGuard" + side)
        name = "ChestGuard" + side
        fill = reference.getObject(name).Shape.cut(drilled.getObject(name).Shape)
        # Preserve the merged print panel's 0.15 mm rear fitting clearance.
        rear_limit = Part.makeBox(170, 10, 80, V(-85, -111.15, 0))
        fill = fill.common(rear_limit)
        guard.Shape = guard.Shape.fuse(fill).removeSplitter()
        assert fill.cut(guard.Shape).Volume < TOL
        fin = doc.getObject("CrownFin" + side)
        outline = [V(x - 8, y, z) for y, z in
                   [(-16, 217), (18, 217), (31, 225), (25, 228), (-8, 225), (-16, 221)]]
        rib = Part.Face(Part.makePolygon(outline + outline[:1])).extrude(V(16, 0, 0))
        assert fin.Shape.cut(rib).Volume < TOL
        fin.Shape = rib
        fin.Label = ("左" if side == "L" else "右") + "冠盖封闭后掠饰翼"
        fin.EvidenceBasis = "v2 封闭原凹槽，作为冠盖造型保留。"
    removed = [o.Name for o in doc.Objects if o.Name.startswith(REMOVED)]
    for name in removed:
        doc.removeObject(name)
    doc.recompute()
    return removed


def export_part(shape, stem, angle=0):
    shape = shape.copy()
    if angle:
        shape.rotate(V(), V(1, 0, 0), angle)
    box = shape.optimalBoundingBox(False)
    shape.translate(V(-box.Center.x, -box.Center.y, -box.ZMin))
    shape.exportBrep(str(stem.with_suffix(".brep")))
    shape.exportStep(str(stem.with_suffix(".step")))
    stl = str(stem.with_suffix(".stl"))
    MeshPart.meshFromShape(Shape=shape, LinearDeflection=.06,
                           AngularDeflection=.12, Relative=False).write(stl)
    mesh = Mesh.Mesh(stl)
    assert mesh.isSolid() and not mesh.hasNonManifolds() and mesh.countComponents() == len(shape.Shells), stem
    exchange = Part.Shape()
    exchange.read(str(stem.with_suffix(".step")))
    valid(exchange)
    return {"facets": mesh.CountFacets, "step_volume_delta_mm3": abs(exchange.Volume - shape.Volume)}


def match_face_materials(state, original, revised):
    """Keep FreeCAD 1.1 per-face appearance on surviving faces."""
    provider = state[0].find(f"./ViewProviderData/ViewProvider[@name='{original.Name}']")
    appearance = provider.find("./Properties/Property[@name='ShapeAppearance']/*")
    filename = appearance.get("file")
    assert appearance.get("version") == "3", original.Name
    materials = read_material_list(state[1][filename])
    if len(materials) < 2:
        return

    def key(face):
        centre = face.CenterOfMass
        return type(face.Surface).__name__, tuple(round(v, 6) for v in
                                                  (centre.x, centre.y, centre.z, face.Area))

    fallback = Counter(materials).most_common(1)[0][0]
    if len(materials) == len(original.Shape.Faces):
        by_face = {key(face): material for face, material in zip(original.Shape.Faces, materials)}
        restored = [by_face.get(key(face), fallback) for face in revised.Shape.Faces]
    else:
        # Some old source views reused the backpack appearance regardless of face count.
        restored = [fallback]
    revised_asset = "V2ShapeAppearance-" + original.Name
    appearance.set("file", revised_asset)
    state[1][revised_asset] = write_material_list(restored)


def main(out):
    historical = [App.openDocument(str(out / "baseline" / (name + ".FCStd"))) for name in
                  ("front-before", "front-after", "backpack-before")]
    paths = [out / "baseline" / name for name in ("CyberTrack-design.FCStd", "CyberTrack.FCStd")]
    source, delivery = [App.openDocument(str(path)) for path in paths]
    copies = [path.with_name("original-" + path.name) for path in paths]
    for path, copy in zip(paths, copies):
        shutil.copyfile(path, copy)
    originals = [App.openDocument(str(path)) for path in copies]
    report = {"removed_source": changes(source, *historical), "exports": {}}
    for name in EDITED_PRINTS:
        original = delivery.getObject(name)
        revised = source.getObject(name)
        valid(revised.Shape)
        # Compare only added material to avoid reporting pre-existing contacts.
        added = revised.Shape.cut(original.Shape)
        original.Shape = revised.Shape.copy()
        if name == "PrintBackpack":
            original.Label, original.EvidenceBasis = revised.Label, revised.EvidenceBasis
        report[name] = {"added_mm3": added.Volume, "new_overlaps": {}}
        for other in delivery.Objects:
            if (other.Name == name or other.Name.startswith(REMOVED)
                    or not hasattr(other, "Shape") or other.isDerivedFrom("App::DocumentObjectGroup")
                    or getattr(other, "Category", "") == "clearance"):
                continue
            if added.Volume > TOL and added.BoundBox.intersect(other.Shape.BoundBox):
                overlap = added.common(other.Shape).Volume
                if overlap > TOL:
                    report[name]["new_overlaps"][other.Name] = overlap
        assert not report[name]["new_overlaps"], (name, report[name])
    report["removed_delivery"] = [o.Name for o in delivery.Objects if o.Name.startswith(REMOVED)]
    for name in report["removed_delivery"]:
        delivery.removeObject(name)
    delivery.recompute()

    for path, original, doc in zip(paths, originals, (source, delivery)):
        state = capture(path)
        for name in EDITED_GEOMETRY:
            previous = original.getObject(name)
            if previous is not None:
                match_face_materials(state, previous, doc.getObject(name))
        destination = out / path.name
        doc.saveAs(str(destination))
        restore(destination, state)
    for doc in originals:
        App.closeDocument(doc.Name)
    objects = [obj for obj in delivery.Objects if hasattr(obj, "Shape")
               and not obj.isDerivedFrom("App::DocumentObjectGroup")
               and getattr(obj, "Category", "") not in ("clearance", "envelope")]
    Part.export(objects, str(out / "CyberTrack.step"))
    for name, basename, angle in (
            ("PrintBackpack", "PP03-base", 0), ("PrintBackpack", "PP03-back", 90),
            ("PrintLowerTub", "PP04-LowerTub", 0), ("PrintCrown", "PP05-Crown", 0),
            ("PrintChestGuardL", "PrintChestGuardL", 0),
            ("PrintChestGuardR", "PrintChestGuardR", 0),
            ("KeelLid", "LC04-KeelLid", 0), ("KeelLid", "LC04-flipped", 180)):
        report["exports"][basename] = export_part(delivery.getObject(name).Shape, out / basename, angle)
    for doc in (source, delivery):
        App.closeDocument(doc.Name)
    for path in paths:
        saved = App.openDocument(str(out / path.name))
        assert not any(o.Name.startswith(REMOVED) for o in saved.Objects)
        for name in EDITED_PRINTS:
            valid(saved.getObject(name).Shape)
        App.closeDocument(saved.Name)
    report["files_sha256"] = {path.name: hashlib.sha256((out / path.name).read_bytes()).hexdigest()
                              for path in [*paths, Path("CyberTrack.step")]}
    report["saved_reopened"] = True
    (out / "cad-readback.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
