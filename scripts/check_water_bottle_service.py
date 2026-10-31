"""Check the retained water bottle's vertical service path in the delivery FCStd."""
import hashlib
import json
from pathlib import Path

import FreeCAD
import Part

MODEL = Path(__file__).resolve().parents[1] / "hardware/model/CyberTrack.FCStd"
LIFT_MM = 150
TOL_MM3 = 0.01


def review(doc):
    body = doc.WaterModule.Shape
    box = body.optimalBoundingBox(False)
    base = FreeCAD.Vector(box.Center.x, box.Center.y, box.ZMin)
    radius = box.XLength / 2
    cylinder = Part.makeCylinder(radius, box.ZLength, base)
    if body.cut(cylinder).Volume + cylinder.cut(body).Volume > TOL_MM3:
        raise ValueError("The saved bottle is no longer a vertical cylinder; revise the sweep")
    sweep = Part.makeCylinder(radius, box.ZLength + LIFT_MM, base)
    released = [doc.WaterRetentionBand.Name, doc.WaterStrapClosure.Name]
    hose = doc.WaterHoseRoute.Name
    checked = 0
    hits = {}
    for obj in doc.Objects:
        if (obj.isDerivedFrom("App::DocumentObjectGroup") or not hasattr(obj, "Shape")
                or obj.Shape.isNull() or getattr(obj, "Category", "") == "clearance"
                or obj.Name in [doc.WaterModule.Name, *released]):
            continue
        checked += 1
        if not sweep.BoundBox.intersect(obj.Shape.BoundBox):
            continue
        volume = sweep.common(obj.Shape).Volume
        if volume > TOL_MM3:
            hits[obj.Name] = round(volume, 4)
    return {
        "model": MODEL.name,
        "sha256": hashlib.sha256(MODEL.read_bytes()).hexdigest(),
        "bottle_diameter_height_mm": [round(2 * radius, 3), round(box.ZLength, 3)],
        "axis": "+Z",
        "travel_mm": LIFT_MM,
        "swept_z_mm": [round(box.ZMin, 3), round(box.ZMax + LIFT_MM, 3)],
        "released_first": released,
        "checked_fixed_shapes_with_hose": checked,
        "volume_threshold_mm3": TOL_MM3,
        "with_hose_overlaps_mm3": hits,
        "after_hose_removal_overlaps_mm3": {k: v for k, v in hits.items() if k != hose},
        "pass": set(hits) == {hose},
    }


if __name__ == "__main__":
    doc = FreeCAD.openDocument(str(MODEL))
    try:
        report = review(doc)
        print(json.dumps(report, indent=2))
    finally:
        FreeCAD.closeDocument(doc.Name)
    raise SystemExit(0 if report["pass"] else 1)
