"""Check 0.41 -> 0.42 scope, with additive mounting material only."""
import argparse,hashlib,json
from pathlib import Path
import FreeCAD as A
import Part
from breadboard_layout import box
from effects_mount import PREFIXES,MOUNTS,zc,mirror

p=argparse.ArgumentParser(description=__doc__);p.add_argument('baseline',type=Path);args=p.parse_args()
root=Path(__file__).resolve().parents[1];current=root/'hardware/model/CyberTrack.FCStd'
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
hashes=[sha(args.baseline),sha(current)]
old=A.openDocument(str(args.baseline.resolve()));new=A.openDocument(str(current))
before={o.Name:o.Shape for o in old.Objects if hasattr(o,'Category')}
after={o.Name:o.Shape for o in new.Objects if hasattr(o,'Category')}
masks={'KeelLid':Part.makeCompound([zc(3.51,68.49,87.01,x,y) for x,y in MOUNTS]),
       'BackpackShell':box(56.9,62.4,51.4,80.1,107.6,118.1).fuse(mirror(box(56.9,62.4,51.4,80.1,107.6,118.1),-1))}
rows=[]
for n,s in before.items():
    t=after[n]
    if n in masks:
        removed=s.cut(t).Volume;outside=t.cut(s).cut(masks[n]).Volume
        rows.append({'name':n,'expected':'additive local mounting bosses only','removed_mm3':removed,'outside_allowed_zone_mm3':outside,'passed':removed<1e-5 and outside<1e-5})
    else:
        same=s.exportBrepToString()==t.exportBrepToString();delta=0 if same else s.cut(t).Volume+t.cut(s).Volume
        rows.append({'name':n,'expected':'unchanged','difference_mm3':delta,'passed':delta<1e-5})
added=sorted(after.keys()-before.keys());removed=sorted(before.keys()-after.keys())
report={'revision':'0.42','baseline_revision':'0.41','baseline_sha256':hashes[0],'source_sha256':hashes[1],
        'objects':rows,'added':added,'removed':removed,'unchanged_objects':sum(r['expected']=='unchanged' and r['passed'] for r in rows),
        'passed':all(r['passed'] for r in rows) and not removed and all(n.startswith(PREFIXES) for n in added),
        'head_shell_unchanged':next(r['passed'] for r in rows if r['name']=='HeadShell'),
        'front_slope_outer_skin_retained':next(r['passed'] for r in rows if r['name']=='KeelLid'),
        'physical_fit_verified':False}
A.closeDocument(new.Name);A.closeDocument(old.Name)
assert hashes==[sha(args.baseline),sha(current)]
(root/'hardware/model/effects-change-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='objects'},indent=2))
if not report['passed']:raise SystemExit(1)
