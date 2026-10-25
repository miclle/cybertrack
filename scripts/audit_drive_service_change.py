"""Compare a saved0.31 baseline with0.32, rejecting unrelated geometry changes."""
import argparse,hashlib,json
from pathlib import Path
import FreeCAD as A
p=argparse.ArgumentParser(description=__doc__);p.add_argument('baseline',type=Path);p.add_argument('--current',type=Path,default=Path('hardware/model/CyberTrack.FCStd'));p.add_argument('--output',type=Path,default=Path('hardware/model/drive-service-change-audit.json'));args=p.parse_args()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before=A.openDocument(str(args.baseline.resolve()));after=A.openDocument(str(args.current.resolve()))
a={o.Name:o.Shape for o in before.Objects if hasattr(o,'Category')};b={o.Name:o.Shape for o in after.Objects if hasattr(o,'Category')}
allowed={'LowerTub'}
removed={'FrontBulkhead','BatteryRoof','MotorEndPlateL','MotorEndPlateR'}|{n for n in a if n.startswith('MotorEndPlateScrew')}
added=set()
r={'baseline_revision':'0.31','revision':'0.32','baseline_sha256':sha(args.baseline),'source_after_sha256':sha(args.current),'objects':[],'added':sorted(b.keys()-a.keys()),'removed':sorted(a.keys()-b.keys())}
for n in sorted(a.keys()&b.keys()):
 x,y=a[n].cleaned(),b[n].cleaned();same=x.exportBrepToString()==y.exportBrepToString()
 diff=0 if same else x.cut(y).Volume+y.cut(x).Volume
 r['objects'].append({'name':n,'difference_mm3':diff,'changed':diff>1e-5,'authorised':n in allowed})
r['changed']=[x['name'] for x in r['objects'] if x['changed']];r['unchanged_count']=sum(not x['changed'] for x in r['objects'])
r['passed']=set(r['added'])==added and set(r['removed'])==removed and all(not x['changed'] or x['authorised'] for x in r['objects'])
args.output.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='objects'},ensure_ascii=False,indent=2),flush=True)
A.closeDocument(before.Name);A.closeDocument(after.Name)
if not r['passed']:raise SystemExit(1)
