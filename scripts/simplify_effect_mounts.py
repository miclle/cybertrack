"""Remove chassis buck mounts and screw retainers; retain the existing lid interfaces.

The two buck modules are integrated into the guns by the user. Their new local
positions are not measured and are deliberately not invented in the CAD model.
"""
import hashlib
import json
from pathlib import Path

import FreeCAD as A
import Part
import Mesh
import MeshPart
from breadboard_layout import box
from update_pp02 import shape_rows, signature, same

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'hardware/model'
OUT = MODEL / 'lean-print'
RETAINERS = ['EffectRetainerLMOS', 'EffectRetainerLBuck',
             'EffectRetainerRMOS', 'EffectRetainerRBuck', 'IgnitionMOSRetainer']
CHANGED = ('EffectTray', 'IgnitionMOSCarrier')


def obsolete(name):
    return (name.startswith(('EffectRetainer', 'IgnitionMOSRetainer'))
            or name in ('EffectBuckL', 'EffectBuckR', 'EffectSupportLBuck',
                        'EffectSupportRBuck', 'EffectWireSideL', 'EffectWireSideR')
            or name.startswith(('EffectPortLBuck', 'EffectPortRBuck')))


def apply(doc):
    tray = doc.getObject('EffectTray')
    # Remove the unused front board bay, retaining both side arms and all four
    # original mounting ears. No change to the already sliced lid is needed.
    s = tray.Shape.cut(box(-40.5, -60, 66.4, 40.5, -42.25, 72))
    for x in (-43.5, -2.5, 2.5, 43.5):
        # Slightly overcut the old radius to avoid a zero-thickness tangency
        # where the two central posts met; PCB contact faces are elsewhere.
        s = s.cut(Part.makeCylinder(2.55, 1.7, A.Vector(x, -32.25, 68.5)))
    tray.Shape = s.removeSplitter()
    tray.Label = '效果 MOS 胶固承板 · 双板／四点安装'
    tray.EvidenceBasis = '2026-10-26 用户将两块降压板集成于枪体；取消底盘降压位及全部MOS压框，保留四个顶盖安装耳和MOS板边承托；热熔胶保持与温升待实测。'
    carrier = doc.getObject('IgnitionMOSCarrier')
    s = carrier.Shape
    for x0, x1 in ((18, 24), (-24, -18)):
        s = s.cut(box(x0, -83.6, 54.4, x1, -77.4, 58.2))
    carrier.Shape = s.removeSplitter()
    carrier.Label = '点火 MOS 胶固托架 · 两点吊装'
    carrier.EvidenceBasis = '2026-10-26 取消压框和压框螺柱；两点吊装接口、板底支承及板端空间保持，用户采用热熔胶固定；机械保持和温升未验。'
    removed = [o.Name for o in doc.Objects if obsolete(o.Name)]
    for name in removed:
        doc.removeObject(name)
    doc.recompute()
    for name in CHANGED:
        s = doc.getObject(name).Shape
        assert s.isValid() and len(s.Solids) == 1, name
    return removed


def check(doc):
    physical = [o for o in doc.Objects if hasattr(o, 'Shape')
                and not o.isDerivedFrom('App::DocumentObjectGroup')
                and getattr(o, 'Category', '') != 'clearance']
    hits = {}
    for name in CHANGED:
        s = doc.getObject(name).Shape
        hits[name] = []
        for o in physical:
            if o.Name == name or not s.BoundBox.intersect(o.Shape.BoundBox):
                continue
            v = s.common(o.Shape).Volume
            if v > .01:
                hits[name].append([o.Name, v])
    assert not any(hits.values()), hits
    return {'passed': True, 'overlaps': hits, 'physical_fit_verified': False,
            'adhesive_retention_verified': False}


def main():
    OUT.mkdir(exist_ok=True)
    report = {'removed_print_parts': RETAINERS, 'documents': {}, 'parts': {},
              'gun_buck_positions_measured': False, 'changed_print_parts': list(CHANGED)}
    offsets = json.loads((MODEL / 'completion-print/geometry-audit.json').read_text())['parts']
    for label, path in [('delivery', MODEL / 'CyberTrack.FCStd'),
                        ('source', MODEL / 'source/CyberTrack-design.FCStd')]:
        d = A.openDocument(str(path))
        before = shape_rows(d)
        old = {n: d.getObject(n).Shape.copy() for n in CHANGED}
        removed = apply(d)
        audit = check(d)
        for name, row in before.items():
            if name not in removed and name not in CHANGED:
                assert same(row, signature(d.getObject(name).Shape)), (label, name)
        for name in CHANGED:
            s = d.getObject(name).Shape
            assert s.cut(old[name]).Volume < .001, (name, 'must only remove material')
            if label == 'delivery':
                t = s.copy()
                t.translate(A.Vector(*offsets[name]['translation']))
                t.exportBrep(str(OUT / (name+'.brep')))
                t.exportStep(str(OUT / (name+'.step')))
                mesh = MeshPart.meshFromShape(Shape=t, LinearDeflection=.035,
                                              AngularDeflection=.08, Relative=False)
                mesh.write(str(OUT / (name+'.stl')))
                back = Mesh.Mesh(str(OUT / (name+'.stl')))
                assert back.isSolid() and back.countComponents() == 1 and not back.hasNonManifolds(), name
                step = Part.Shape(); step.read(str(OUT / (name+'.step')))
                delta = step.cut(t).Volume + t.cut(step).Volume
                assert delta < .01
                report['parts'][name] = {'old_volume_mm3': old[name].Volume,
                    'volume_mm3': s.Volume, 'removed_volume_mm3': old[name].Volume-s.Volume,
                    'manifold': True, 'components': 1, 'step_delta_mm3': delta,
                    'translation': offsets[name]['translation']}
        expected = shape_rows(d)
        d.save(); A.closeDocument(d.Name)
        d = A.openDocument(str(path)); actual = shape_rows(d)
        assert actual.keys() == expected.keys() and all(same(v, actual[n]) for n, v in expected.items())
        report['documents'][label] = {'removed': removed, 'objects': len(actual),
            'other_geometry_preserved': len(before)-len(removed)-len(CHANGED),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'check': audit}
        if label == 'delivery':
            Part.export([o for o in d.Objects if hasattr(o, 'Shape')
                and not o.isDerivedFrom('App::DocumentObjectGroup')
                and getattr(o, 'Category', '') not in ('clearance', 'envelope')], str(MODEL / 'CyberTrack.step'))
        A.closeDocument(d.Name)
    (OUT / 'geometry-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
