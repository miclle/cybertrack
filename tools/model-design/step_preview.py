"""Validate an external STEP and resolve its faces to native snapshot face IDs."""
import json
import shutil
import sys
from pathlib import Path
import cadquery as cq
from geometry import bounds, check_bounds, tessellate_faces


def import_snapshot(source, output, revision, restore_step=None):
    source, output = Path(source), Path(output)
    manifest = json.loads((source/'manifest.json').read_text())
    shape = cq.importers.importStep(str(source/'model.step')).val()
    if not shape.isValid() or len(shape.Solids()) != 1:
        raise ValueError('STEP must contain one valid solid')
    if restore_step:
        original=cq.importers.importStep(restore_step).val()
        check_bounds(bounds(shape),bounds(original))
        if shape.cut(original).Volume()+original.cut(shape).Volume() > 1e-5:
            raise ValueError('Native restore does not match original STEP geometry')
    native_faces = manifest['faces']
    if len(native_faces) != len(shape.Faces()):
        raise ValueError('STEP changed native face topology')
    ids = []
    for face in shape.Faces():
        candidates = [native for native in native_faces
                      if abs(native['area']-face.Area()) < 1e-5
                      and max(abs(a-b) for a,b in zip(native['center'], face.Center().toTuple())) < 1e-5
                      and max(abs(a-b) for a,b in zip(native['bounds'], bounds(face))) < 1e-5]
        if len(candidates) != 1 or candidates[0]['id'] in ids:
            raise ValueError('Native face mapping is ambiguous; snapshot not published')
        ids.append(candidates[0]['id'])
    mesh = tessellate_faces(shape)
    for face, native_id in zip(mesh['faces'], ids):
        face['id'] = native_id
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(source/'model.step', output/'external-01.step')
    shutil.copyfile(source/'model.step', output/'assembly.step')
    # Validate a second read of the exact artifact used by export.
    reloaded = cq.importers.importStep(str(output/'external-01.step')).val()
    check_bounds(bounds(reloaded), bounds(shape))
    if not reloaded.isValid() or abs(reloaded.Volume()-shape.Volume()) > 1e-5:
        raise ValueError('Copied STEP validation failed')
    summary = {'valid': True, 'solids': 1, 'volumeMm3': shape.Volume(),
               'faces': len(ids), 'boundsMm': bounds(shape),
               'stepRoundTripValid': True, 'stepBoundsVerified': True}
    result = {'revision': revision, 'engine': 'FreeCAD STEP / OpenCascade validation',
              'parts': {'external-01': summary}, 'meshes': {'external-01': mesh}}
    (output/'preview.json').write_text(json.dumps(result), encoding='utf8')
    return {key: value for key, value in result.items() if key != 'meshes'}


if __name__ == '__main__':
    request = json.load(sys.stdin)
    print(json.dumps(import_snapshot(request['source'],request['output'],request['revision'],request.get('restoreStep'))))
