"""Run inside the connected FreeCAD process, through its existing MCP tool.

This adapter exports one native solid and edits existing length properties.
It does not construct geometry or provide a second CAD engine.
"""
import hashlib
import json
import math
import re
import uuid
from pathlib import Path


def _object(document_name, object_name, document_uid=None):
    import FreeCAD as App
    doc = App.getDocument(document_name)
    if document_uid is not None and str(doc.Uid) != document_uid:
        raise ValueError('FreeCAD document identity changed')
    obj = doc.getObject(object_name)
    if obj is None or not hasattr(obj, 'Shape'):
        raise ValueError('Native solid does not exist')
    doc.recompute()
    if not obj.Shape.isValid() or len(obj.Shape.Solids) != 1:
        raise ValueError('Expected one valid native solid')
    return doc, obj


def _properties(obj):
    return {name: float(getattr(obj, name).Value)
            for name in obj.PropertiesList
            if obj.getTypeIdOfProperty(name) == 'App::PropertyLength'}


def fingerprint(obj):
    content = obj.Shape.exportBrepToString() + json.dumps(
        {'properties': _properties(obj), 'expressions': obj.ExpressionEngine}, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def _publish(doc, obj, inbox, snapshot_id, kind, previous=None, before=None, after=None, undo_snapshot_id=None):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', snapshot_id):
        raise ValueError('Invalid snapshot ID')
    output = Path(inbox).resolve() / snapshot_id
    output.mkdir(parents=True, exist_ok=False)
    shape = obj.Shape
    shape.exportStep(str(output / 'model.step'))
    data = (output / 'model.step').read_bytes()
    if len(data) > 8*1024*1024:
        raise ValueError('STEP exceeds 8 MiB')
    faces = []
    for index, face in enumerate(shape.Faces):
        box = face.BoundBox
        faces.append({'id': f'Face{index+1}', 'area': face.Area,
                      'center': list(face.CenterOfMass),
                      'bounds': [box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax]})
    # Snapshot the native document too; never overwrite its working file.
    doc.saveCopy(str(output / 'native.FCStd'))
    manifest = {
        'schema': 'solidcue-freecad/v1', 'snapshotId': snapshot_id, 'kind': kind,
        'source': {'application': 'FreeCAD', 'documentName': doc.Name,
                   'documentUid': str(doc.Uid), 'objectName': obj.Name,
                   'fingerprint': fingerprint(obj)},
        'name': obj.Label, 'unit': 'mm', 'upAxis': 'Z',
        'stepSha256': hashlib.sha256(data).hexdigest(),
        'previousFingerprint': previous, 'before': before or {}, 'after': after or {},
        'properties': _properties(obj), 'faces': faces,
    }
    if undo_snapshot_id:
        manifest['undoSnapshotId'] = undo_snapshot_id
    # Manifest is the completion marker; a partial export cannot be synchronized.
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf8')
    return manifest


def export_snapshot(document_name, object_name, inbox, snapshot_id=None):
    doc, obj = _object(document_name, object_name)
    return _publish(doc, obj, inbox, snapshot_id or str(uuid.uuid4()), 'snapshot')


def edit_properties(document_name, document_uid, object_name, expected_fingerprint,
                    changes, inbox, snapshot_id=None, *, _undo_snapshot_id=None):
    doc, obj = _object(document_name, object_name, document_uid)
    if fingerprint(obj) != expected_fingerprint:
        raise ValueError('Native document changed; export a fresh snapshot and select again')
    if not isinstance(changes, dict) or not changes:
        raise ValueError('Supply explicit native length properties in mm')
    existing = _properties(obj)
    expressions = dict(obj.ExpressionEngine)
    for name, value in changes.items():
        if name not in existing or bool(obj.getEditorMode(name)) or name in expressions:
            raise ValueError('Property is not an editable unbound native length: '+name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError('Length must be finite and positive')
    if all(existing[name] == value for name, value in changes.items()):
        raise ValueError('No change; do not create a new snapshot')
    before = {name: existing[name] for name in changes}
    doc.openTransaction('SolidCue property edit')
    try:
        for name, value in changes.items():
            setattr(obj, name, value)
        doc.recompute()
        if (not obj.Shape.isValid() or len(obj.Shape.Solids) != 1
                or any('Invalid' in str(s) or 'Error' in str(s) for s in obj.State)
                or any(abs(getattr(obj, name).Value-value) > 1e-9 for name,value in changes.items())):
            raise ValueError('Native recompute failed or changed the requested dimension')
        result = _publish(doc, obj, inbox, snapshot_id or str(uuid.uuid4()), 'undo' if _undo_snapshot_id else 'edit',
                          expected_fingerprint, before, changes, _undo_snapshot_id)
        doc.commitTransaction()
        return result
    except Exception:
        doc.abortTransaction()
        doc.recompute()
        raise


def undo_properties(document_name, document_uid, object_name, expected_fingerprint,
                    original_snapshot_id, inbox, snapshot_id=None):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', original_snapshot_id):
        raise ValueError('Invalid original snapshot ID')
    prior = json.loads((Path(inbox)/original_snapshot_id/'manifest.json').read_text())
    if prior['kind'] != 'edit' or prior['source']['documentUid'] != document_uid or prior['source']['objectName'] != object_name:
        raise ValueError('Undo target does not belong to this native object')
    if prior['source']['fingerprint'] != expected_fingerprint:
        raise ValueError('Only the latest unchanged native edit can be restored')
    return edit_properties(document_name, document_uid, object_name, expected_fingerprint,
                           prior['before'], inbox, snapshot_id, _undo_snapshot_id=original_snapshot_id)
