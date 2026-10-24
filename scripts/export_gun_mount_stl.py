"""Export revision 0.18 gun mounts for fit trials, without changing the assembly.

Run with FreeCAD's bundled Python. Only the four rigid mount parts are exported; liners, screws, inserts, guns,
shoulder rails and service volumes are not print parts. STL coordinates are millimetres, with each part seated at Z=0.
"""
import argparse
import subprocess
import tempfile
import hashlib
import json
from pathlib import Path
import FreeCAD as App
import Mesh
import MeshPart

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'hardware/model'
OUT = MODEL / 'print-trials/gun-mounts-0.18'
V = App.Vector
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

PARTS = [
    ('bubble-gun-bracket.stl', '泡泡枪整体圆环与阶梯槽支架', 'bubble',
     ['BubbleGunCradle', 'BubbleGunRing'] + ['BubbleGunSlotWall'+str(i) for i in range(1, 7)], None),
    ('water-gun-bracket.stl', '水枪底托与尾线导向鞍', 'water',
     ['WaterGunCradle', 'WaterGunLeadGuide'], None),
    ('water-gun-front-cap.stl', '水枪前压盖', 'water', ['WaterGunCap1'], ((1, 0, 0), 180)),
    ('water-gun-rear-cap.stl', '水枪后压盖', 'water', ['WaterGunCap2'], ((1, 0, 0), 180)),
]


def bbox(shape):
    b = shape.optimalBoundingBox(False)
    return [b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax]


def export_parts(source, report, revision):
    digest = sha(source)
    assert report['design_revision'] == '0.18', 'Review the print-part selection for a new revision'
    assert digest in report['files_sha256'].values(), 'Assembly report does not match the saved source'
    pitch = report['gun_pitch']
    doc = App.openDocument(str(source))
    rows = []
    try:
        for filename, label, kind, names, rotation in PARTS:
            shapes = []
            for name in names:
                obj = doc.getObject(name)
                assert obj is not None and obj.Category == 'structure', name
                shape = obj.Shape.copy()
                shape.translate(-V(*pitch['translation_world_mm'][kind]))
                shape.rotate(V(*pitch['pivot_world_mm'][kind]), V(1, 0, 0),
                             -pitch['rotation_about_X_degrees'])
                shapes.append(shape)
            merged = shapes[0].multiFuse(shapes[1:]).removeSplitter() if len(shapes) > 1 else shapes[0]
            assert merged.isValid() and len(merged.Solids) == 1, filename
            # Joining touching CAD objects must not change their material volume.
            assert abs(merged.Volume - sum(s.Volume for s in shapes)) < 1e-4, filename
            if rotation:
                axis, angle = rotation
                merged.rotate(V(), V(*axis), angle)
            bounds = bbox(merged)
            offset = [-v for v in bounds[:3]]
            merged.translate(V(*offset))
            bounds = bbox(merged)
            assert max(abs(v) for v in bounds[:3]) < 1e-6
            mesh = MeshPart.meshFromShape(Shape=merged, LinearDeflection=0.03,
                                          AngularDeflection=0.10, Relative=False)
            path = OUT / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            mesh.write(str(path))
            readback = Mesh.Mesh(str(path))
            closed = readback.isSolid()
            nonmanifold = readback.hasNonManifolds()
            self_intersection = readback.hasSelfIntersections()
            components = readback.countComponents()
            assert closed and not nonmanifold and not self_intersection and components == 1, filename
            assert readback.Volume > 0, filename
            b = readback.BoundBox
            mesh_bounds = [b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax]
            bbox_delta = max(abs(a-b) for a, b in zip(bounds, mesh_bounds))
            volume_error = abs(readback.Volume-merged.Volume)/merged.Volume
            assert bbox_delta < 0.05 and volume_error < 0.005, (filename, bbox_delta, volume_error)
            rows.append({
                'file': filename, 'label': label, 'quantity': 1, 'source_objects': names,
                'role': 'rigid_fit_trial',
                'inverse_pitch_kind': kind, 'additional_rotation_axis_angle': rotation,
                'translation_to_origin_mm': offset, 'size_xyz_mm': bounds[3:],
                'solid_count': 1, 'cad_volume_mm3': merged.Volume,
                'facets': readback.CountFacets, 'mesh_components': components,
                'closed': closed, 'nonmanifold': nonmanifold, 'self_intersection': self_intersection,
                'mesh_volume_mm3': readback.Volume, 'relative_volume_error': volume_error,
                'bbox_error_mm': bbox_delta, 'sha256': sha(path),
            })
            print(filename, [round(v, 3) for v in bounds[3:]], readback.CountFacets, flush=True)
    finally:
        App.closeDocument(doc.Name)
    assert sha(source) == digest, 'Export modified the source assembly'
    result = {
        'source': 'hardware/model/CyberTrack.FCStd', 'source_sha256': digest,
        'source_git_commit': revision, 'source_snapshot': 'committed Git blob; concurrent working tree changes excluded',
        'assembly_revision': '0.18', 'units': 'mm; STL has no embedded unit declaration',
        'mesh_tolerance': {'linear_deflection_mm': 0.03, 'angular_deflection_rad': 0.10},
        'orientation': 'inverse assembly elevation, optional flat-face rotation, then translate minimum XYZ to zero; no scaling',
        'excluded': 'guns, soft liners, fasteners, inserts, hoses, wires, shoulder rails/posts and clearance volumes',
        'source_unchanged': True, 'physical_fit_verified': False, 'manufacturing_released': False,
        'parts': rows,
    }
    (OUT / 'readback.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', default='HEAD', help='Committed revision to export; resolved once before reading')
    args = parser.parse_args()
    git = lambda *a: subprocess.check_output(['git', '-C', str(ROOT), *a])
    revision = git('rev-parse', '--verify', args.revision+'^{commit}').decode().strip()
    report = json.loads(git('show', revision+':hardware/model/readback.json'))
    with tempfile.TemporaryDirectory(prefix='cybertrack-gun-stl-') as directory:
        source = Path(directory) / 'CyberTrack.FCStd'
        source.write_bytes(git('show', revision+':hardware/model/CyberTrack.FCStd'))
        export_parts(source, report, revision)


if __name__ == '__main__':
    main()
