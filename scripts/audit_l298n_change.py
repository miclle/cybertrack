"""Compare the saved pre-L298N assembly and the current scoped layout change."""
import argparse
import hashlib
import json
from pathlib import Path
import FreeCAD as App

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('baseline', type=Path)
parser.add_argument('--current', type=Path, default=Path('hardware/model/CyberTrack.FCStd'))
parser.add_argument('--output', type=Path, default=Path('hardware/model/l298n-change-audit.json'))
args = parser.parse_args()
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
before = App.openDocument(str(args.baseline.resolve()))
after = App.openDocument(str(args.current.resolve()))
a = {o.Name:o.Shape for o in before.Objects if hasattr(o,'Category')}
b = {o.Name:o.Shape for o in after.Objects if hasattr(o,'Category')}
rows = []
for name in sorted(a.keys() & b.keys()):
    x,y = a[name].cleaned(),b[name].cleaned()
    same = x.exportBrepToString()==y.exportBrepToString()
    delta = 0 if same else x.cut(y).Volume+y.cut(x).Volume
    rows.append({'name':name,'difference_mm3':delta,'changed':delta>1e-5})
changed = [r['name'] for r in rows if r['changed']]
report = {'baseline_revision':'0.32','revision':'0.33',
          'baseline_sha256':sha(args.baseline),'source_after_sha256':sha(args.current),
          'added':sorted(b.keys()-a.keys()),'removed':sorted(a.keys()-b.keys()),
          'changed':changed,'unchanged_count':sum(not r['changed'] for r in rows),'objects':rows,
          'passed':b.keys()-a.keys()=={'L298NEnvelope'} and not a.keys()-b.keys() and changed==['PowerCableRoute']}
args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='objects'},indent=2))
App.closeDocument(before.Name)
App.closeDocument(after.Name)
if not report['passed']:raise SystemExit(1)
