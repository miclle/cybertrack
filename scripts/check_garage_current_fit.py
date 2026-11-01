"""Check saved current robot against the saved printed garage, without saving CAD.

Run with FreeCAD's Python runtime. Output must be a new directory; historical
reports and embedded robot snapshots are not silently replaced.
"""
import argparse
import json
from pathlib import Path

import FreeCAD as App
import Part

import container_garage as base
import container_garage_print as printed


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    source = base.ROOT / "hardware/model/CyberTrack.FCStd"
    garage = printed.TARGET
    inputs = [source, garage, Path(__file__), Path(base.__file__), Path(printed.__file__),
              base.ROOT / "hardware/model/container-garage/parameters.json"]
    identities = {str(p.relative_to(base.ROOT)): base.sha(p) for p in inputs}
    robot_doc, garage_doc = None, None
    try:
        robot_doc = App.openDocument(str(source))
        garage_doc = App.openDocument(str(garage))
        replaced = {name for obj in robot_doc.Objects if hasattr(obj, "SourceFeatures") for name in obj.SourceFeatures}
        selected, excluded = [], []
        for obj in robot_doc.Objects:
            reason = ("container" if obj.TypeId in ("App::Part", "App::DocumentObjectGroup") else
                      "no_shape" if not hasattr(obj, "Shape") or obj.Shape.isNull() else
                      "merged_source" if obj.Name in replaced else
                      "clearance" if getattr(obj, "Category", "") == "clearance" else None)
            if reason:
                excluded.append({"object": obj.Name, "reason": reason})
                continue
            shape = obj.Shape.copy()
            # Honor parent placements; shape already carries the object's placement.
            parent = obj.getGlobalPlacement().multiply(obj.Placement.inverse())
            shape.Placement = parent.multiply(shape.Placement)
            if not shape.isValid():
                raise ValueError("Invalid source geometry: " + obj.Name)
            selected.append((obj.Name, getattr(obj, "Category", ""), shape))
        if not selected:
            raise ValueError("No robot geometry selected")
        base.OUT = printed.OUT = output
        base.P.update(revision="current-robot-fit-20261101", inner_height=246,
                      door_top_gap=1, door_tip_thickness=2)
        base.open_angle.cache_clear()
        base._TARGET_BOUNDS = {}
        base._LAST_BROAD_PHASE = [None, None]
        # Preserve the existing candidate's parked Y rather than optimizing placement.
        park_y = garage_doc.Pose.RobotY.Value
        garage_doc.Pose.LockAngle = 90
        garage_doc.recompute()
        fixed = [(o.Name, o.Category, o.Shape.copy()) for o in garage_doc.GarageFixed.Group]
        doors = [(o.Name, "door", o.Shape.copy()) for o in garage_doc.Door.Group]
        lock = garage_doc.L01.Shape.copy()
        lock.Placement = garage_doc.Lock.Placement.multiply(lock.Placement)
        fixed.append(("ReleasedCam", "cam", lock))
        if not all(s.isValid() for _, _, s in fixed + doors):
            raise ValueError("Invalid saved garage geometry")
        base.PARK_Y = park_y
        base.DETACHED = {"fixed": fixed, "door": doors, "robot": selected,
                         "source_hash": base.sha(source), "park_y": park_y}
        rows = [{"object": n, "category": c, "bbox_mm": base.exact_bounds(s), "volume_mm3": s.Volume}
                for n, c, s in selected]
        old_names = {o.SourceObject for o in garage_doc.Robot.Group if hasattr(o, "SourceObject")}
        base.dump("inputs.json", {"sha256": identities, "freecad_version": App.Version(),
                                  "selected": rows, "excluded": excluded,
                                  "old_embedded_robot_objects": len(old_names),
                                  "removed_since_embedded_snapshot": sorted(old_names - {n for n, _, _ in selected}),
                                  "added_since_embedded_snapshot": sorted({n for n, _, _ in selected} - old_names),
                                  "saved_robot_snapshot_updated": False})
        printed.install_cavity_broad_phase()
        base.validate()
        base.counterexamples()
        result = base.RESULT
        result.update(input_sha256=identities, saved_robot_snapshot_updated=False,
                      fasteners_in_motion_check=False, source_bbox_method="optimalBoundingBox(False,False)")
        result["closed_clearances_mm"]["front_header_top"] = result["closed_clearances_mm"].pop("top")
        result["sources_unchanged"] = all(base.sha(base.ROOT / rel) == digest for rel, digest in identities.items())
        if not result["sources_unchanged"]:
            raise ValueError("Input changed during validation")
        base.dump("spatial-validation.json", result)
        print(json.dumps({"passed": result["passed"], "source_objects": len(selected),
                          "door_angles": len(result["door_motion"]["angles_deg"]),
                          "path_samples": len(result["robot_path"]["samples"]),
                          "clearances_mm": result["closed_clearances_mm"],
                          "continuous_bounds": result["continuous_bounds"]}))
        return 0 if result["passed"] else 1
    finally:
        if garage_doc:
            App.closeDocument(garage_doc.Name)
        if robot_doc:
            App.closeDocument(robot_doc.Name)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", required=True, type=Path)
    raise SystemExit(main(cli.parse_args().output.resolve()))
