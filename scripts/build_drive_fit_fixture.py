"""Export a lightweight, one-piece drive fit fixture from the saved chassis.

Run build() from FreeCAD, with this directory on sys.path.
Does not regenerate or modify the main assembly.
The fixture tests interface fit, not the strength or service access of the tub.
"""
import hashlib
import json
from pathlib import Path

import FreeCAD as App
import Mesh
import MeshPart
import Part

from drive_mount import HOLES, box, cx, side_shape, union
from drive_mount_check import capsule_drop

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'hardware/model/drive-fit-fixture'
SOURCE = ROOT / 'hardware/model/CyberTrack.FCStd'
TOL = 1e-5


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    OUT.mkdir(exist_ok=True)
    source_hash = digest(SOURCE)
    source = App.openDocument(str(SOURCE))
    original = source.getObject('PrintLowerTub').Shape.copy()
    # Preserve both actual interfaces independently, including their holes,
    # counterbores and end faces. No scaling or hole compensation.
    masks = [side_shape(box(73, -35.1, 30.4, 87, 35.1, 72), s)
             for s in (-1, 1)]
    sides = [original.common(mask).removeSplitter() for mask in masks]
    assert all(s.isValid() and len(s.Solids) == 1 for s in sides)
    functional_masks = [side_shape(box(73, -20.7, 32, 77, 20.7, 72), s)
                        for s in (-1, 1)]
    functional_masks += [side_shape(cx(5.5, 73, 87, y, 37.4), s)
                         for s in (-1, 1) for y in (-28.1, 28.1)]
    beams = [box(-77, y, 30.4, 77, y + 8, 38.4) for y in (-40, 32)]
    # Local end blocks reinforce the beam/post junction without closing the
    # downward motor slot or obstructing screw insertion from inside the frame.
    ends = [side_shape(box(65, y, 30.4, 77, y + 10, 44.4), s)
            for s in (-1, 1) for y in (-40, 30)]
    ties = union(beams + ends)
    corridors = [side_shape(cx(3.1, 0, 73.1, y, 37.4), s)
                 for s in (-1, 1) for y in (-28.1, 28.1)]
    ties = ties.cut(Part.makeCompound(corridors))
    # Protect the motor plates and complete post cores. Allow the larger R7
    # post roots to blend into the new beams, avoiding tangent internal voids.
    ties = ties.cut(Part.makeCompound(functional_masks))
    frame = union(sides + [ties])
    assert frame.isValid() and len(frame.Solids) == 1

    checks = []

    def check(name, value):
        checks.append({'name': name, 'volume_mm3': value, 'passed': value <= TOL})
        assert value <= TOL, (name, value)

    for i, expected in enumerate(sides):
        check('retained_source_interface_' + str(i), expected.cut(frame).Volume)
    for i, mask in enumerate(functional_masks):
        expected = original.common(mask)
        actual = frame.common(mask)
        check('interface_symmetric_difference_' + str(i),
              actual.cut(expected).Volume + expected.cut(actual).Volume)
    for side, sign in [('L', 1), ('R', -1)]:
        for i, (y, z) in enumerate(HOLES[:4]):
            land = side_shape(cx(2.4, 73.1, 76.9, y, z).cut(
                cx(1.8, 73.1, 76.9, y, z)), sign)
            check('motor_land_' + side + str(i), land.cut(frame).Volume)
        # Continuous conservative downward envelope after removing the serviced
        # track, coupler and motor screws; no wiring is represented here.
        removal = union([capsule_drop(26.2, 49, 0, 50, 16),
                         capsule_drop(49, 73, 0, 50, 18.5),
                         capsule_drop(73, 79, 0, 57, 6),
                         capsule_drop(73, 95, 0, 57, 3)])
        check('motor_downward_envelope_' + side,
              frame.common(side_shape(removal, sign)).Volume)
    for i, tool in enumerate(corridors):
        check('track_screw_loading_corridor_' + str(i), frame.common(tool).Volume)

    refs = [o for o in source.Objects if hasattr(o, 'Shape') and
            (getattr(o, 'Category', '') == 'drive' or
             o.Name.startswith(('MotorFaceScrew', 'TrackMountScrew')))]
    assert len(refs) == 42, len(refs)
    for o in refs:
        if frame.BoundBox.intersect(o.Shape.BoundBox):
            check('static_fit_' + o.Name, frame.common(o.Shape).Volume)

    doc = App.newDocument('CyberTrackDriveFitFixture')
    obj = doc.addObject('PartDesign::Feature', 'DriveFitFrame')
    obj.Label = 'VF01 电机与履带装配验证框架 · 打印1件'
    obj.Shape = frame
    obj.addProperty('App::PropertyString', 'SourceSHA256', 'Evidence')
    obj.SourceSHA256 = source_hash
    obj.addProperty('App::PropertyString', 'Scope', 'Evidence')
    obj.Scope = '接口装配验证；非正式底盘；承载、打印和实物配合未验收'
    group = doc.addObject('App::DocumentObjectGroup', 'References')
    group.Label = '装配参考 · 不打印'
    for ref in refs:
        copy = doc.addObject('PartDesign::Feature', ref.Name)
        copy.Label = ref.Label
        copy.Shape = ref.Shape.copy()
        group.addObject(copy)
        copy.Visibility = False
    obj.Visibility = True
    doc.recompute()
    native_path = OUT / 'CyberTrack-drive-fit.FCStd'
    doc.saveAs(str(native_path))
    App.closeDocument(doc.Name)
    reopened = App.openDocument(str(native_path))
    saved = reopened.getObject('DriveFitFrame').Shape
    check('saved_frame_symmetric_difference',
          saved.cut(frame).Volume + frame.cut(saved).Volume)
    for ref in refs:
        back = reopened.getObject(ref.Name).Shape
        same = (back.cleaned().exportBrepToString() ==
                ref.Shape.cleaned().exportBrepToString())
        check('saved_reference_' + ref.Name,
              0.0 if same else back.cut(ref.Shape).Volume + ref.Shape.cut(back).Volume)

    local = saved.copy()
    local.translate(App.Vector(0, 0, -30.4))
    mesh = MeshPart.meshFromShape(Shape=local, LinearDeflection=.08,
                                  AngularDeflection=.15, Relative=False)
    stl_path = OUT / 'VF01-DriveFitFrame.stl'
    mesh.write(str(stl_path))
    back = Mesh.Mesh(str(stl_path))
    assert back.isSolid() and not back.hasNonManifolds()
    assert back.countComponents() == 1 and len(saved.Shells) == 1
    b = local.BoundBox
    report = {
        'source': str(SOURCE.relative_to(ROOT)), 'source_sha256': source_hash,
        'source_object': 'PrintLowerTub', 'fixture_id': 'VF01',
        'coordinate_system': 'X left, Y rear, Z up; front -Y; millimetres',
        'interface_clip_positive_xyz_mm': [[73, 87], [-35.1, 35.1], [30.4, 72]],
        'interface_clip_negative': 'mirror mask across X=0; copy actual source geometry',
        'protected_interfaces': 'motor plates X73..77/Y+-20.7/Z32..72; R5.5 post cores X73..87/Y+-28.1/Z37.4; both sides',
        'post_root_changes': 'new beam end blocks blend into R7 roots outside protected R5.5 cores',
        'crossbeams': {'x_mm': [-77, 77], 'y_mm': [[-40, -32], [32, 40]],
                       'z_mm': [30.4, 38.4]},
        'end_blocks': {'positive_x_mm': [65, 77], 'mirrored': True,
                       'y_mm': [[-40, -30], [30, 40]], 'z_mm': [30.4, 44.4]},
        'original_volume_mm3': original.Volume, 'fixture_volume_mm3': saved.Volume,
        'solid_volume_reduction_percent': 100 * (1 - saved.Volume / original.Volume),
        'stl_translation_xyz_mm': [0, 0, -30.4],
        'stl_size_xyz_mm': [b.XLength, b.YLength, b.ZLength],
        'solids': len(saved.Solids), 'cad_valid': saved.isValid(),
        'stl_closed': back.isSolid(), 'stl_nonmanifold': back.hasNonManifolds(),
        'stl_components': back.countComponents(), 'stl_facets': back.CountFacets,
        'reference_objects': [o.Name for o in refs], 'checks': checks,
        'files_sha256': {p.name: digest(p) for p in (native_path, stl_path)},
        'passed': True, 'physical_fit_verified': False, 'sliced': False,
        'limits': ['CAD material reduction is not a measured filament or time saving',
                   'No stiffness, strength, loaded driving or full chassis access validation',
                   'Print supports, process tolerances and screw engagement remain unverified'],
    }
    assert digest(SOURCE) == source_hash, 'Main assembly changed while exporting'
    (OUT / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    App.closeDocument(reopened.Name)
    App.closeDocument(source.Name)
    print(json.dumps({k: report[k] for k in ('stl_size_xyz_mm', 'fixture_volume_mm3',
          'solid_volume_reduction_percent', 'passed')}, ensure_ascii=False))


if __name__ == '__main__':
    build()
