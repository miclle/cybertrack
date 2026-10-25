"""Verify that 0.44 adds only the measured booster and two wiring budgets."""
import argparse
import hashlib
import json
from pathlib import Path
import FreeCAD as A
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('baseline',type=Path);args=p.parse_args()
root=Path(__file__).resolve().parents[1];folder=root/'hardware/model';current=folder/'CyberTrack.FCStd'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
old=A.openDocument(str(args.baseline.resolve()));new=A.openDocument(str(current))
before={o.Name:o for o in old.Objects if hasattr(o,'Category')};after={o.Name:o for o in new.Objects if hasattr(o,'Category')}
rows=[]
for n,o in before.items():
 t=after[n];s=o.Shape
 delta=0 if s.exportBrepToString()==t.Shape.exportBrepToString() else s.cut(t.Shape).Volume+t.Shape.cut(s).Volume
 rows.append(dict(name=n,difference_mm3=delta,passed=delta<1e-5 and o.Label==t.Label and o.Category==t.Category))
added=sorted(after.keys()-before.keys());removed=sorted(before.keys()-after.keys())
r=dict(revision='0.44',baseline_revision='0.43',baseline_sha256=sha(args.baseline),source_sha256=sha(current),
       added=added,removed=removed,objects=rows,unchanged_objects=sum(x['passed'] for x in rows),
       passed=not removed and added==['MT3608Envelope','MT3608WireSpaceFront','MT3608WireSpaceRear'] and all(x['passed'] for x in rows))
(folder/'mt3608-change-audit.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in r.items() if k!='objects'},indent=2))
assert r['passed']
