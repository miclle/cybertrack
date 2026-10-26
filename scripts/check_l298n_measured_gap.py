"""Read-only assembly study for the reported 30 mm motor-tail gap.

Run build() with FreeCAD. The symmetric tail boxes and cradle are study
allocations, not measured motor geometry or released manufacturing parts.
"""
import hashlib
import json
from pathlib import Path

import FreeCAD as App
import Part

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'hardware/model/CyberTrack.FCStd'
OUT = ROOT / 'hardware/model/drive-fit-fixture/l298n-gap-study'
V = App.Vector
TOL = 0.01


def box(coords):
    x, y, z, X, Y, Z = coords
    return Part.makeBox(X-x, Y-y, Z-z, V(x, y, z))


def bounds(shape):
    b = shape.BoundBox
    return [b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax]


def union(shapes):
    return shapes[0].multiFuse(shapes[1:]).removeSplitter()


def collisions(shape, obstacles):
    result = []
    for name, other in obstacles.items():
        if not shape.BoundBox.intersect(other.BoundBox):
            continue
        common = shape.common(other)
        assert common.isValid(), name
        if common.Volume > TOL:
            result.append({'object': name, 'volume_mm3': common.Volume})
    return result


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    source = App.openDocument(str(SOURCE))
    if source.getObject('L298NTopRetainer'):
        App.closeDocument(source.Name)
        raise ValueError('This historical 27.5 mm study requires its old baseline; use l298n_compact_mount for the current 28.5 mm connected model.')
    physical = {
        o.Name: o.Shape.copy() for o in source.Objects
        if hasattr(o, 'Shape') and not o.Shape.isNull()
        and ((hasattr(o, 'Category') and o.Category != 'clearance')
             or o.Name.startswith('Print'))
        and o.TypeId != 'App::Part'
    }
    # Delivery CAD includes fused print parts as well as retained features.
    # Keep all physical objects, including those without Category.
    old_board = physical['L298NEnvelope']
    old_cradle = physical['L298NCarrier']
    old_hangers = union([
        box((x0, -16, 31.2, x1, -8, 90.1))
        for x0, x1 in [(-23, -17), (17, 23)]
    ] + [
        box((x0, -16, 79, x1, 24.5, 81.5))
        for x0, x1 in [(-23, -17), (17, 23)]
    ])
    # Only remove the old L298N hanger material in this in-memory study.
    old_hangers = old_hangers.common(physical['KeelLid'])
    fixed = {n: s for n, s in physical.items() if not n.startswith('L298N')}
    fixed['KeelLid'] = physical['KeelLid'].cut(old_hangers)
    # Deliberately conservative radial extent; not inferred from the photo.
    tails = Part.makeCompound([
        box((15, -18.5, 31.5, 26.2, 18.5, 68.5)),
        box((-26.2, -18.5, 31.5, -15, 18.5, 68.5)),
    ])
    fixed['CenteredTailStudyKeepout'] = tails
    board = box((-13.75, -21.25, 32, 13.75, 22.25, 78.2))
    rotated_cradle = old_cradle.copy()
    rotated_cradle.rotate(V(0, 0, 0), V(0, 0, 1), 90)
    rotated_cradle.translate(V(9.75, .5, 0))
    flat_board = box((-21.75, -21.85, 70.5, 21.75, 24.35, 98))

    floor = box((-13.75, -22.7, 29.3, 13.75, 24.5, 31.1)).cut(
        box((-10, -19.5, 28, 10, 20.5, 32)))
    guides, pads = [], []
    for x0, x1 in [(-13.75, -10), (10, 13.75)]:
        guides += [box((x0, -23.5, 31.1, x1, -21.5, 62)),
                   box((x0, 22.5, 31.1, x1, 24.5, 80))]
        pads += [box((x0, -21.5, 31.1, x1, -19.5, 32)),
                 box((x0, 20.5, 31.1, x1, 22.5, 32))]
    cradle_unrelieved = union([floor] + guides + pads)
    # Carry relief up the entire front guide so withdrawal clears the hatch.
    # This leaves 1.2 mm guide thickness; strength is not established.
    relief = box((-14, -24, 28, 14, -22.7, 81))
    cradle = cradle_unrelieved.cut(relief).removeSplitter()
    assert cradle.isValid() and len(cradle.Solids) == 1
    assert board.common(cradle).Volume < TOL
    assembly = Part.makeCompound([board, cradle])
    # Orthogonal polyhedra: sweep every horizontal face and include both ends.
    # This preserves the open front/top instead of filling the entire bbox.
    sweep_parts = [assembly]
    end = assembly.copy(); end.translate(V(0, 0, -80)); sweep_parts.append(end)
    for face in assembly.Faces:
        if abs(face.normalAt(0, 0).z) > .99:
            sweep_parts.append(face.extrude(V(0, 0, -80)))
    sweep = union(sweep_parts)
    assert sweep.isValid()
    removed = ['BottomServiceCover'] + [n for n in fixed if n.startswith('BottomCoverScrew')]
    open_fixed = {n: s for n, s in fixed.items() if n not in removed}
    # Continuous axial asymmetry: shifting the gap centre by c leaves
    # clearances 1.25+c and 1.25-c. No symmetry asserted as a measurement.
    offsets = []
    for c in (-11.2, -2, -1.25, 0, 1.25, 2, 11.2):
        offsets.append({'gap_center_x_mm': c, 'minimum_x_clearance_mm': 1.25-abs(c)})
    report = {
        'source': str(SOURCE.relative_to(ROOT)), 'source_sha256': digest,
        'measurement': {'gap_mm': 30, 'endpoints': 'closest tail protrusions including encoders/connectors'},
        'study_assumptions': [
            '30 mm axial gap centred on X=0 only for the nominal study.',
            'Tail exclusion boxes use existing motor radial bounds Y +/-18.5 and Z31.5..68.5; actual encoder/connector profile unknown.',
            'Both motor tails extend inward from the old placeholders; individual extension and centre offset remain unmeasured.',
            'Cradle is a guide/support allocation without retention hardware, measured PCB contacts, terminal/wire or thermal allowances.',
        ],
        'original': {
            'board_bbox_mm': bounds(old_board),
            'board_tail_overlaps': collisions(old_board, {'TailStudy': tails}),
            'hanger_tail_overlaps': collisions(old_hangers, {'TailStudy': tails}),
        },
        'rejected_options': {
            'rotate_existing_cradle': {'bbox_mm': bounds(rotated_cradle), 'overlaps': collisions(rotated_cradle, fixed)},
            'flat_above_motors': {'bbox_mm': bounds(flat_board), 'overlaps': collisions(flat_board, fixed)},
        },
        'candidate': {
            'rotation': '+90 degrees about world Z; local length +Z, width -Y, thickness +X',
            'board_bbox_mm': bounds(board), 'cradle_bbox_mm': bounds(cradle),
            'board_tail_clearance_each_mm_at_centered_gap': 1.25,
            'static_board_overlaps': collisions(board, fixed),
            'static_cradle_overlaps': collisions(cradle, fixed),
            'before_hatch_relief_overlaps': collisions(cradle_unrelieved, fixed),
            'cradle_volume_mm3': cradle.Volume,
            'downward_80mm_continuous_sweep': {
                'method': 'union of horizontal-face extrusions and both endpoints of orthogonal polyhedra',
                'removed_first': removed, 'overlaps': collisions(sweep, open_fixed),
                'includes_retention_hardware_and_wires': False,
            },
            'minimum_distances_mm': {
                n: assembly.distToShape(fixed[n])[0]
                for n in ['CenteredTailStudyKeepout', 'BatteryHatch', 'PrintLowerTub',
                          'KeelLid', 'PowerCableRoute', 'MT3608Envelope', 'EffectTray', 'BottomServiceCover']
            },
            'gap_center_sensitivity': offsets,
            'retention_design_complete': False,
        },
        'physical_fit_verified': False, 'manufacturing_released': False,
        'main_cad_modified': False,
    }
    doc = App.newDocument('L298N30mmGapStudy')
    shapes = {'MotorL': physical['MotorL'], 'MotorR': physical['MotorR'],
              'TailStudyKeepout': tails, 'CandidateL298N': board, 'CandidateCradle': cradle}
    for name, shape in shapes.items():
        obj = doc.addObject('Part::Feature', name)
        obj.Shape = shape
        obj.addProperty('App::PropertyString', 'EvidenceBasis')
        obj.EvidenceBasis = '30 mm gap layout study only; see audit.json assumptions; not a manufacturing model'
    doc.Label = '30 mm 尾部间距布局研究／非制造模型'
    doc.recompute()
    path = OUT / 'L298N-30mm-layout-study.FCStd'
    doc.saveAs(str(path)); App.closeDocument(doc.Name)
    saved = App.openDocument(str(path))
    report['saved_readback'] = []
    for name, expected in shapes.items():
        actual = saved.getObject(name).Shape
        delta = expected.cut(actual).Volume + actual.cut(expected).Volume
        report['saved_readback'].append({'name': name, 'valid': actual.isValid(), 'difference_mm3': delta})
        assert actual.isValid() and delta < 1e-5, name
    App.closeDocument(saved.Name)
    App.closeDocument(source.Name)
    report['source_unchanged_during_study'] = hashlib.sha256(SOURCE.read_bytes()).hexdigest() == digest
    (OUT / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report['candidate'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    build()
