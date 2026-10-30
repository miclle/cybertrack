"""Run with FreeCAD's Python. Work only on independent CyberTrack study files."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import uuid

ROOT = Path(__file__).resolve().parents[1]


def create_box_study(object_name):
    """Parameterize a verified axis-aligned box; refuse all other shapes."""
    import FreeCAD as App
    import Part
    source = ROOT / "hardware/model/CyberTrack.FCStd"
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    directory = ROOT / "output/solidcue/studies" / uuid.uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    # Disk hash provenance must never be attributed to an unsaved in-memory model.
    existing = next((d for d in App.listDocuments().values() if d.FileName and Path(d.FileName).resolve() == source), None)
    if existing is not None:
        raise ValueError("production document is already open; use a separate FreeCAD Python process")
    doc = App.openDocument(str(source))
    try:
        obj = doc.getObject(object_name)
        if obj is None or not hasattr(obj, "Shape") or not obj.Shape.isValid() or len(obj.Shape.Solids) != 1:
            raise ValueError("select an existing valid single solid")
        shape = obj.Shape.copy()
        b = shape.BoundBox
        box = Part.makeBox(b.XLength, b.YLength, b.ZLength, App.Vector(b.XMin, b.YMin, b.ZMin))
        difference = shape.cut(box).Volume + box.cut(shape).Volume
        if difference > 1e-7:
            raise ValueError("object is not an axis-aligned box; do not replace its design with a bounding box")
        label = obj.Label
    finally:
        App.closeDocument(doc.Name)
    study = App.newDocument("CyberTrackStudy_" + uuid.uuid4().hex[:10])
    item = study.addObject("Part::Box", "StudyPart")
    item.Label = label + " · 独立参数研究"
    item.Length, item.Width, item.Height = b.XLength, b.YLength, b.ZLength
    item.Placement.Base = App.Vector(b.XMin, b.YMin, b.ZMin)
    study.recompute()
    if not item.Shape.isValid() or item.Shape.cut(shape).Volume + shape.cut(item.Shape).Volume > 1e-7:
        App.closeDocument(study.Name)
        raise ValueError("parameterized study does not preserve the source geometry")
    study.saveAs(str(directory / "study.FCStd"))
    provenance = {"source": "hardware/model/CyberTrack.FCStd", "source_sha256": original_hash,
                  "source_object": object_name, "study_object": item.Name,
                  "coordinate_system": "mm; X left, Y rear, Z up; front -Y; no transform",
                  "geometry_equivalence_volume_mm3": difference,
                  "production_model_modified": False, "physical_fit": "not tested"}
    if hashlib.sha256(source.read_bytes()).hexdigest() != original_hash:
        raise ValueError("source file changed during study creation")
    (directory / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
    return study, item, directory


def verify_native_roundtrip(object_name):
    """Real FreeCAD edit/undo evidence, independent of UI and model inference."""
    import FreeCAD as App
    from solidcue import configuration, verified_source
    lock, source, _ = configuration()
    verified_source(lock, source)
    bridge = runpy.run_path(str(source / "freecad_bridge.py"))
    doc, obj, directory = create_box_study(object_name)
    inbox = directory / "cad-inbox"
    inbox.mkdir()
    try:
        original = obj.Shape.copy()
        initial = bridge["export_snapshot"](doc.Name, obj.Name, str(inbox), "baseline")
        edited = bridge["edit_properties"](doc.Name, str(doc.Uid), obj.Name,
            initial["source"]["fingerprint"], {"Length": float(obj.Length.Value) + 1.0}, str(inbox), "edit")
        if obj.Shape.cut(original).Volume + original.cut(obj.Shape).Volume <= 1e-7:
            raise ValueError("edit did not change geometry")
        stale_rejected = False
        try:
            bridge["edit_properties"](doc.Name, str(doc.Uid), obj.Name,
                initial["source"]["fingerprint"], {"Length": 9}, str(inbox), "stale")
        except ValueError:
            stale_rejected = True
        restored = bridge["undo_properties"](doc.Name, str(doc.Uid), obj.Name,
            edited["source"]["fingerprint"], "edit", str(inbox), "restored")
        difference = obj.Shape.cut(original).Volume + original.cut(obj.Shape).Volume
        if not stale_rejected or difference > 1e-7:
            raise ValueError("stale guard or native restore failed")
        doc.save()
        report = {"scope": "native FreeCAD headless; not desktop card, user intent or physical acceptance",
                  "upstream_revision": lock["revision"], "freecad_version": App.Version(),
                  "source_object": object_name, "stale_edit_rejected": stale_rejected,
                  "restored_geometry_difference_mm3": difference,
                  "baseline_properties": initial["properties"], "edited_properties": edited["properties"],
                  "restored_properties": restored["properties"], "study_directory": str(directory)}
        (directory / "native-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        return report
    finally:
        App.closeDocument(doc.Name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--object", required=True, help="existing single box-like object; inspected first")
    parser.add_argument("--verify", action="store_true", help="perform +1mm edit and undo only in the new study")
    args = parser.parse_args()
    if args.verify:
        print(json.dumps(verify_native_roundtrip(args.object), ensure_ascii=False, indent=2))
    else:
        doc, obj, directory = create_box_study(args.object)
        print(json.dumps({"document": doc.Name, "object": obj.Name, "directory": str(directory)}, ensure_ascii=False))
