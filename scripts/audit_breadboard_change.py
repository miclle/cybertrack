"""Compare saved 0.40 geometry with the pre-change assembly, including head exterior."""
import argparse
import hashlib
import json
from pathlib import Path
import FreeCAD as A
import Part
from breadboard_layout import replaced, MOUNTS, cylinder, check

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('baseline',type=Path)
parser.add_argument('--current',type=Path,default=Path('hardware/model/CyberTrack.FCStd'))
parser.add_argument('--output',type=Path,default=Path('hardware/model/breadboard-change-audit.json'))
args=parser.parse_args()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
hashes=[sha(args.baseline),sha(args.current)]
old=A.openDocument(str(args.baseline.resolve()))
new=A.openDocument(str(args.current.resolve()))
before={o.Name:o for o in old.Objects if hasattr(o,'Category')}
after={o.Name:o for o in new.Objects if hasattr(o,'Category')}
allowed={'HeadShell','ElectronicsTray','PowerCableRoute'}
rows=[]
for name in sorted(before.keys() & after.keys()):
    a=before[name].Shape.cleaned();b=after[name].Shape.cleaned()
    same=a.exportBrepToString()==b.exportBrepToString()
    difference=0.0 if same else a.cut(b).Volume+b.cut(a).Volume
    rows.append({'name':name,'difference_mm3':difference,'expected':'redesigned' if name in allowed else 'unchanged',
                 'passed':name in allowed or difference<=1e-5})
# Changes to HeadShell are confined to internal post cylinders; outside them
# the complete original shell is required to be geometrically identical.
zones=[cylinder(3.61,164,170.01,x,y) for x in (-49.5,49.5) for y in (-30,0)]
zones += [cylinder(3.51,162.99,171.61,x,y) for x,y in MOUNTS]
mask=Part.makeCompound(zones)
a=before['HeadShell'].Shape;b=after['HeadShell'].Shape
outside=a.cut(b).cut(mask).Volume+b.cut(a).cut(mask).Volume
additions=sorted(after.keys()-before.keys());removals=sorted(before.keys()-after.keys())
# Lower power cable must remain identical; only the head-end branch may change.
clip=Part.makeBox(300,300,161,A.Vector(-150,-150,0))
a=before['PowerCableRoute'].Shape.common(clip);b=after['PowerCableRoute'].Shape.common(clip)
cable_difference=a.cut(b).Volume+b.cut(a).Volume
result=check(new)
report={'revision':'0.40','baseline_revision':'0.39','baseline_sha256':hashes[0],'source_sha256':hashes[1],
        'objects':rows,'added':additions,'removed':removals,
        'unchanged_objects':sum(r['expected']=='unchanged' and r['passed'] for r in rows),
        'head_exterior_difference_mm3':outside,'head_exterior_unchanged':outside<=1e-5,
        'head_change_scope':'only old/new internal post cylinders; crown and every other exterior object unchanged',
        'lower_power_cable_difference_mm3':cable_difference,
        'breadboard_check':result,
        'passed':all(r['passed'] for r in rows) and all(n.startswith('Breadboard') for n in additions)
                 and all(replaced(n) for n in removals) and outside<=1e-5 and cable_difference<=1e-5 and result['passed'],
        'manufacturing_released':False,'physical_fit_verified':False}
A.closeDocument(old.Name);A.closeDocument(new.Name)
assert hashes==[sha(args.baseline),sha(args.current)],'Sources changed during audit'
args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('objects','breadboard_check')},ensure_ascii=False,indent=2))
if not report['passed']:raise SystemExit(1)
