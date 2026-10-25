"""Check 0.42 -> 0.43 board-fixture scope and retain the original lid skin."""
import argparse,hashlib,json
from pathlib import Path
import FreeCAD as A
from breadboard_layout import box
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('baseline',type=Path);p.add_argument('original_lid',type=Path);args=p.parse_args()
root=Path(__file__).resolve().parents[1];model=root/'hardware/model';current=model/'CyberTrack.FCStd'
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
hashes=[sha(args.baseline),sha(args.original_lid),sha(current)]
history=json.loads((model/'effects-change-audit.json').read_text())
assert hashes[0]==history['source_sha256'] and hashes[1]==history['baseline_sha256']
old=A.openDocument(str(args.baseline.resolve()));base=A.openDocument(str(args.original_lid.resolve()));new=A.openDocument(str(current))
before={o.Name:o.Shape for o in old.Objects if hasattr(o,'Category')};after={o.Name:o.Shape for o in new.Objects if hasattr(o,'Category')}
mask=box(-51,-54,68.4,-35,-20,92).fuse(box(35,-54,68.4,51,-20,92))
rows=[]
for n,s in before.items():
 t=after[n]
 if n.startswith('Effect'):
  rows.append({'name':n,'expected':'board fixture and wire allocation may change','passed':t.isValid()})
 elif n=='KeelLid':
  change=s.cut(t).fuse(t.cut(s));outside=change.cut(mask).Volume
  removed_skin=base.getObject('KeelLid').Shape.cut(t).Volume
  rows.append({'name':n,'expected':'local inner mount bosses only','outside_zone_mm3':outside,'original_lid_removed_mm3':removed_skin,'passed':outside<1e-5 and removed_skin<1e-5})
 else:
  equal=s.exportBrepToString()==t.exportBrepToString();delta=0 if equal else s.cut(t).Volume+t.cut(s).Volume
  rows.append({'name':n,'expected':'unchanged','difference_mm3':delta,'passed':delta<1e-5})
added=sorted(after.keys()-before.keys());removed=sorted(before.keys()-after.keys())
r={'revision':'0.43','baseline_revision':'0.42','baseline_sha256':hashes[0],'original_lid_sha256':hashes[1],'source_sha256':hashes[2],
   'objects':rows,'added':added,'removed':removed,'unchanged_objects':sum(x['expected']=='unchanged' and x['passed'] for x in rows),
   'head_and_backpack_unchanged':all(x['passed'] for x in rows if x['name'] in ('HeadShell','BackpackShell') or x['name'].startswith(('Arc','BackpackArc'))),
   'front_slope_outer_skin_retained':next(x['passed'] for x in rows if x['name']=='KeelLid'),
   'passed':not removed and all(n.startswith('Effect') for n in added) and all(x['passed'] for x in rows),'physical_fit_verified':False}
for d in (new,base,old):A.closeDocument(d.Name)
assert hashes==[sha(args.baseline),sha(args.original_lid),sha(current)]
(model/'effect-board-change-audit.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in r.items() if k!='objects'},indent=2))
if not r['passed']:raise SystemExit(1)
