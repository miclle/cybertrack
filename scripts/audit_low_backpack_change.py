"""Compare saved assembly against a pre-task snapshot; fail on unrelated geometry edits."""
import argparse
import hashlib
import json
from pathlib import Path
import FreeCAD as A

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('baseline',type=Path)
parser.add_argument('--current',type=Path,default=Path('hardware/model/CyberTrack.FCStd'))
parser.add_argument('--output',type=Path,default=Path('hardware/model/bottle-backpack-change-audit.json'))
args=parser.parse_args()
before=A.openDocument(str(args.baseline.resolve()));after=A.openDocument(str(args.current.resolve()))
a={o.Name:o.Shape for o in before.Objects if hasattr(o,'Category')}
b={o.Name:o.Shape for o in after.Objects if hasattr(o,'Category')}
allowed={'BackpackShell','BackpackSpine',
         'WaterHoseRoute','WaterGunHoseClearance','BubbleGunHoseRoute','BubbleGunHoseClearance'}
for prefix in ('Water','Bubble'):
    allowed.update(prefix+s for s in ('Module','Pod','PodCap','ServiceLid','CapGrip','LidMark','FillPlug','FillSeal',
                                      'RetentionBand','StrapClosure','StrapAccessSpace','BottomPad','SidePad0','SidePad1','TopPad','BottleRemovalSpace','FingerSpace','DipTubeSpace'))
    for side in ('L','R'):
        allowed.update([prefix+'CapTool'+side,prefix+'PodScrew'+side,prefix+'PodInsert'+side,'FillInsert'+prefix+side,'FillScrew'+prefix+side])
for side in ('L','R'):
    allowed.update('Pack'+s+side for s in ('Frame','Inset','Mark'))
    allowed.update('PackLouver'+side+str(i) for i in range(3))
rows=[]
for n in sorted(a.keys() & b.keys()):
    x,y=a[n].cleaned(),b[n].cleaned()
    same=x.exportBrepToString()==y.exportBrepToString()
    delta=0.0 if same else x.cut(y).Volume+y.cut(x).Volume
    rows.append({'name':n,'difference_mm3':delta,'changed':delta>1e-5})
changed=[r['name'] for r in rows if r['changed']]
added=sorted(b.keys()-a.keys());removed=sorted(a.keys()-b.keys())
unexpected=sorted((set(changed)|set(added)|set(removed))-allowed)
report={'baseline_revision':'0.35','revision':'0.36','baseline_sha256':hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
        'source_after_sha256':hashlib.sha256(args.current.read_bytes()).hexdigest(),
        'changed':changed,'added':added,'removed':removed,'unexpected':unexpected,
        'unchanged_count':sum(not r['changed'] for r in rows),'objects':rows,'passed':not unexpected}
args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='objects'},indent=2))
A.closeDocument(before.Name);A.closeDocument(after.Name)
if unexpected:raise SystemExit(1)
