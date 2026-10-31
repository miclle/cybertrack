"""CyberTrack extension: native whole-model snapshots and reversible placement studies.

Run inside FreeCAD via its existing MCP. Meshes are previews, never STEP or
manufacturing acceptance. All edits require a saved independent study document.
"""
import hashlib
import json
import math
import re
import struct
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _directory(inbox, snapshot_id):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', snapshot_id):
        raise ValueError('Invalid snapshot ID')
    return Path(inbox).resolve() / snapshot_id


def _display(doc):
    if doc.Objects and doc.Objects[0].ViewObject is not None:
        return {o.Name: dict(visible=o.ViewObject.Visibility,
                color='#'+''.join(f'{max(0,min(255,round(c*255))):02x}' for c in o.ViewObject.ShapeColor[:3]) if hasattr(o.ViewObject,'ShapeColor') else '#889e96') for o in doc.Objects}
    # Offline preparation reads saved display state, never guesses which
    # construction features were hidden. The first material is the part swatch.
    with zipfile.ZipFile(doc.FileName) as archive:
        root = ET.fromstring(archive.read('GuiDocument.xml'))
        result = {}
        for view in root.findall('.//ViewProvider'):
            visible = view.find("./Properties/Property[@name='Visibility']/Bool")
            material = view.find("./Properties/Property[@name='ShapeAppearance']/MaterialList")
            color = '#889e96'
            if material is not None:
                data = archive.read(material.get('file'))
                if len(data) >= 12 and struct.unpack_from('<I',data)[0] > 0:
                    color = f'#{struct.unpack_from("<I",data,8)[0] >> 8:06x}'
            result[view.get('name')] = dict(visible=visible is not None and visible.get('value')=='true',color=color)
        return result


def _objects(doc):
    display = _display(doc)
    return [o for o in doc.Objects if hasattr(o, 'Shape') and hasattr(o, 'Placement') and not hasattr(o,'Group') and not o.Shape.isNull()
            and display.get(o.Name,{}).get('visible',False) and not any(
                hasattr(parent, 'Group') and not display.get(parent.Name,{}).get('visible',False) for parent in o.InList)]


def _save_copy(doc, path):
    doc.saveCopy(str(path))
    if not doc.Objects or doc.Objects[0].ViewObject is not None:
        return
    # FreeCAD headless saves drop view providers; preserve saved presentation
    # in the independent snapshot without changing its native Document.xml.
    with zipfile.ZipFile(doc.FileName) as source:
        gui = source.read('GuiDocument.xml')
        assets = {e.get('file') for e in ET.fromstring(gui).iter() if e.get('file')}
        # FreeCAD's restore reader consumes registered binary files in archive
        # order. A set iteration puts materials before their XML or out of order,
        # silently replacing saved appearances with default gray in the GUI.
        retained = {'GuiDocument.xml': gui}
        retained.update({name:source.read(name) for name in source.namelist() if name in assets})
    with zipfile.ZipFile(path) as snapshot:
        contents = {name:snapshot.read(name) for name in snapshot.namelist()}
    contents = {name:data for name,data in contents.items() if name not in retained}
    contents.update(retained)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as snapshot:
        for name,data in contents.items(): snapshot.writestr(name,data)


def _properties(obj):
    p = obj.Placement.Base
    return dict(PlacementX=p.x, PlacementY=p.y, PlacementZ=p.z)


def _fingerprint(obj):
    # OCCT tessellation caches are not geometry edits; exclude them so saving,
    # rendering and reopening a document do not invalidate an unchanged part.
    brep = obj.Shape.cleaned().exportBrepToString()
    # BREP topology flags begin with Free/Modified/Checked, transient bookkeeping
    # changed by tessellation and validity checks, not the shape definition.
    brep = re.sub(r'(?m)^[01]{3}([01]{4})$', r'000\1', brep)
    # Normalize sub-nanometre serialization noise in persisted OCCT frames.
    brep = re.sub(r'(?<!\S)[+-]?(?:\d+\.\d*|\d*\.?\d+[eE][+-]?\d+)(?!\S)',
                  lambda m: '0' if round(float(m.group()),9)==0 else format(round(float(m.group()),9),'.9f').rstrip('0').rstrip('.'), brep)
    return _hash((brep+json.dumps(_properties(obj), sort_keys=True)).encode())


def _scene(doc):
    return {o.Name: _fingerprint(o) for o in _objects(doc)}


def _scene_hash(fingerprints):
    return _hash(json.dumps(fingerprints, sort_keys=True, separators=(',', ':')).encode())


def export_assembly(document_name, inbox, snapshot_id, *, kind='snapshot', baseline=None,
                    target=None, before=None, after=None, undo_snapshot_id=None, reference_snapshot_id=None):
    import FreeCAD as App
    doc = App.getDocument(document_name)
    doc.recompute()
    objects = _objects(doc)
    if not objects or len(objects) > 500:
        raise ValueError('Expected 1–500 visible shape objects')
    folder = _directory(inbox, snapshot_id)
    folder.mkdir(parents=True, exist_ok=False)
    parts, fingerprints = [], {}
    reference = {}
    if reference_snapshot_id:
        prior = json.loads((_directory(inbox,reference_snapshot_id)/'manifest.json').read_text())
        if prior['sceneFingerprint'] != baseline:
            raise ValueError('Preview reference differs from baseline')
        reference = {p['id']:p for p in prior['parts']}
    display = _display(doc)
    for obj in objects:
        shape = obj.Shape
        fingerprints[obj.Name] = _fingerprint(obj)
        prior = reference.get(obj.Name)
        if prior and prior['source']['fingerprint'] == fingerprints[obj.Name]:
            # OCCT can choose a different triangulation after reopening unchanged
            # geometry. Retain the verified baseline mesh and face map for it.
            mesh_bytes = (_directory(inbox,reference_snapshot_id)/(obj.Name+'.json')).read_bytes()
            if _hash(mesh_bytes) != prior['meshSha256']:
                raise ValueError('Baseline mesh hash differs: '+obj.Name)
        else:
            positions, indices, faces = [], [], []
            for i, face in enumerate(shape.Faces):
                vertices, triangles = face.tessellate(0.35)
                offset, start = len(positions)//3, len(indices)//3
                positions.extend(round(c,6) for v in vertices for c in (v.x, v.y, v.z))
                indices.extend(offset+j for tri in triangles for j in tri)
                faces.append(dict(id=f'Face{i+1}', type='native', start=start, count=len(triangles)))
            if not indices or len(indices) > 3000000:
                raise ValueError('Empty or excessive mesh: '+obj.Name)
            mesh_bytes = json.dumps(dict(positions=positions, indices=indices, faces=faces), separators=(',', ':')).encode()
        (folder/(obj.Name+'.json')).write_bytes(mesh_bytes)
        color = display[obj.Name]['color']
        b = shape.BoundBox
        parts.append(dict(id=obj.Name, name=obj.Label, kind='native', position=[0,0,0], color=color,
            source=dict(application='FreeCAD', documentName=doc.Name, documentUid=str(doc.Uid),
                        objectName=obj.Name, fingerprint=fingerprints[obj.Name]),
            properties=_properties(obj), meshSha256=_hash(mesh_bytes),
            geometry=dict(valid=shape.isValid(), solids=len(shape.Solids), volumeMm3=shape.Volume,
                faces=len(shape.Faces), boundsMm=[b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax],
                stepRoundTripValid=False, stepBoundsVerified=False)))
    _save_copy(doc,folder/'native.FCStd')
    result = dict(schema='cybertrack-assembly/v1', snapshotId=snapshot_id, kind=kind,
        name='CyberTrack · 整机设计研究', unit='mm', upAxis='Z', parts=parts,
        nativeSha256=_hash((folder/'native.FCStd').read_bytes()),
        sceneFingerprint=_scene_hash(fingerprints), previousSceneFingerprint=baseline,
        target=target, before=before or {}, after=after or {}, undoSnapshotId=undo_snapshot_id)
    (folder/'manifest.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf8')
    return {k: result[k] for k in ('snapshotId','sceneFingerprint','target','before','after')} | {'parts':len(parts)}


def edit_placement(document_name, document_uid, object_name, expected_fingerprint,
                   changes, inbox, baseline_snapshot_id, snapshot_id, *, undo_snapshot_id=None):
    import FreeCAD as App
    doc = App.getDocument(document_name)
    # A study is explicitly marked when copied. Never mutate the production file.
    if not doc.FileName or 'CyberTrackStudySource' not in doc.PropertiesList:
        raise ValueError('Open a marked independent study before editing')
    if Path(doc.FileName).resolve() == Path(doc.CyberTrackStudySource).resolve():
        raise ValueError('Production document is not editable through this adapter')
    if str(doc.Uid) != document_uid:
        raise ValueError('Document identity changed')
    prior = json.loads((_directory(inbox, baseline_snapshot_id)/'manifest.json').read_text())
    if prior['schema'] != 'cybertrack-assembly/v1' or _scene_hash(_scene(doc)) != prior['sceneFingerprint']:
        raise ValueError('Native assembly changed; export and select again')
    obj = doc.getObject(object_name)
    if obj is None or _fingerprint(obj) != expected_fingerprint or object_name not in {p['id'] for p in prior['parts']}:
        raise ValueError('Native target changed')
    if obj.getEditorMode('Placement') or obj.ExpressionEngine or obj.TypeId != 'Part::Feature':
        raise ValueError('Only unconstrained static Part::Feature placement is supported')
    if not changes or set(changes)-{'PlacementX','PlacementY','PlacementZ'}:
        raise ValueError('Specify absolute placement coordinates in mm')
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>10000 for v in changes.values()):
        raise ValueError('Invalid placement coordinate')
    original = obj.Placement
    properties = _properties(obj)
    if all(properties[k] == v for k,v in changes.items()):
        raise ValueError('No placement change')
    before = {k:properties[k] for k in changes}
    doc.openTransaction('CyberTrack placement study')
    try:
        placement = obj.Placement
        base = placement.Base
        for key,value in changes.items():
            setattr(base,key[-1].lower(),value)
        placement.Base = base
        obj.Placement = placement
        doc.recompute()
        if not obj.Shape.isValid() or any(abs(_properties(obj)[k]-v)>1e-9 for k,v in changes.items()):
            raise ValueError('Native placement verification failed')
        result = export_assembly(document_name,inbox,snapshot_id,kind='undo' if undo_snapshot_id else 'edit',
            baseline=prior['sceneFingerprint'],target=object_name,before=before,after=changes,undo_snapshot_id=undo_snapshot_id,reference_snapshot_id=baseline_snapshot_id)
        doc.commitTransaction()
        return result
    except Exception:
        doc.abortTransaction()
        obj.Placement = original
        doc.recompute()
        raise


def undo_placement(document_name, document_uid, inbox, edit_snapshot_id, snapshot_id):
    prior = json.loads((_directory(inbox,edit_snapshot_id)/'manifest.json').read_text())
    if prior['kind'] != 'edit':
        raise ValueError('Undo requires a placement edit')
    target = next(p for p in prior['parts'] if p['id'] == prior['target'])
    return edit_placement(document_name,document_uid,target['id'],target['source']['fingerprint'],
        prior['before'],inbox,edit_snapshot_id,snapshot_id,undo_snapshot_id=edit_snapshot_id)
