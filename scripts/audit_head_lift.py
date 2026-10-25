"""Compare 0.37 against saved 0.36: rigid head translation and scoped neck/cable edits."""
import argparse
import hashlib
import json
from pathlib import Path
import FreeCAD as A
from head_lift import head_members, LIFT, check

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('baseline',type=Path)
p.add_argument('--current',type=Path,default=Path('hardware/model/CyberTrack.FCStd'))
p.add_argument('--output',type=Path,default=Path('hardware/model/head-lift-change-audit.json'))
a=p.parse_args()
old=A.openDocument(str(a.baseline.resolve()));new=A.openDocument(str(a.current.resolve()))
before={o.Name:o.Shape for o in old.Objects if hasattr(o,'Category')}
after={o.Name:o.Shape for o in new.Objects if hasattr(o,'Category')}
head={o.Name for o in head_members(new)}
neck={n for n in before if n.startswith('Neck') and n!='NeckCableBridge'}
allowed=neck|{'PowerCableRoute'}
rows=[]
for n in sorted(before.keys() & after.keys()):
    original=before[n].cleaned();actual=after[n].cleaned()
    expected=original.copy()
    if n in head:expected.translate(A.Vector(0,0,LIFT))
    delta=expected.cut(actual).Volume+actual.cut(expected).Volume
    rows.append({'name':n,'expectation':'rigid +25 Z' if n in head else 'neck/cable redesign' if n in allowed else 'unchanged',
                 'difference_from_expected_mm3':delta,'passed':n in allowed or delta<=1e-5})
added=sorted(after.keys()-before.keys());removed=sorted(before.keys()-after.keys())
contacts=[]
for left,right in [('NeckYokeL','NeckHeadSaddle'),('NeckYokeR','NeckHeadSaddle'),
                   ('NeckStayL','NeckHeadSaddle'),('NeckStayR','NeckHeadSaddle'),
                   ('NeckStaySleeveL','NeckPedestal'),('NeckStaySleeveR','NeckPedestal'),
                   ('NeckHeadSaddle','HeadShell'),('NeckPedestal','KeelLid')]:
    x,y=after[left],after[right]
    area=sum(f.common(g).Area for f in x.Faces for g in y.Faces if f.BoundBox.intersect(g.BoundBox))
    contacts.append({'a':left,'b':right,'nominal_contact_area_mm2':area,'passed':area>1e-5})
r={'baseline_revision':'0.36','revision':'0.37','baseline_sha256':hashlib.sha256(a.baseline.read_bytes()).hexdigest(),
   'source_after_sha256':hashlib.sha256(a.current.read_bytes()).hexdigest(), 'head_lift_mm':LIFT,
   'rigid_head_count':len(head),'unchanged_count':len(before.keys()-head-allowed),
   'redesigned_or_repositioned_neck_and_cable':sorted(allowed),'added':added,'removed':removed,
   'clearances_before':check(old)['clearances'],'clearances_after':check(new)['clearances'],
   'support_face_contacts':contacts,'objects':rows,'passed':all(c['passed'] for c in contacts) and not added and not removed and all(r['passed'] for r in rows)}
a.output.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in r.items() if k!='objects'},indent=2))
A.closeDocument(old.Name);A.closeDocument(new.Name)
if not r['passed']:raise SystemExit(1)
