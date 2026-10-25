"""Verify 0.40 -> 0.41 changes against an explicit saved baseline."""
import argparse
import hashlib
import json
from pathlib import Path
import FreeCAD as A
from breadboard_layout import box
from ultrasonic_integration import NAMES, PROBES

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('baseline',type=Path)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
current=root/'hardware/model/CyberTrack.FCStd'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
hashes=[sha(args.baseline),sha(current)]
old=A.openDocument(str(args.baseline.resolve()))
new=A.openDocument(str(current))
before={o.Name:o.Shape for o in old.Objects if hasattr(o,'Category')}
after={o.Name:o.Shape for o in new.Objects if hasattr(o,'Category')}
rows=[]
for n,s in before.items():
    expected=s.copy();kind='unchanged'
    if n in PROBES:expected.translate(A.Vector(0,3.5,0));kind='probe +Y3.5 only'
    if n=='ElectronicsTray':expected=expected.cut(box(-24.5,-73,171,24.5,-70.5,178));kind='front relief 49x2 only'
    t=after[n]
    same=expected.exportBrepToString()==t.exportBrepToString()
    delta=0 if same else expected.cut(t).Volume+t.cut(expected).Volume
    rows.append({'name':n,'expected':kind,'difference_mm3':delta,'passed':delta<1e-5})
added=sorted(after.keys()-before.keys());removed=sorted(before.keys()-after.keys())
report={'revision':'0.41','baseline_revision':'0.40','baseline_sha256':hashes[0],'source_sha256':hashes[1],
        'objects':rows,'added':added,'removed':removed,
        'unchanged_objects':sum(r['expected']=='unchanged' and r['passed'] for r in rows),
        'head_shell_unchanged':next(r['passed'] for r in rows if r['name']=='HeadShell'),
        'head_fascia_and_crown_unchanged':all(r['passed'] for r in rows if r['expected']=='unchanged'),
        'probe_exposure_changed':True,
        'passed':all(r['passed'] for r in rows) and added==sorted(NAMES) and not removed,
        'physical_fit_verified':False}
A.closeDocument(new.Name);A.closeDocument(old.Name)
assert hashes==[sha(args.baseline),sha(current)]
(root/'hardware/model/ultrasonic-integration-change-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='objects'},indent=2))
if not report['passed']:raise SystemExit(1)
