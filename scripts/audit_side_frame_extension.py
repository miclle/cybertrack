"""Verify the two 0.49 side-frame extensions against the saved 0.48 assembly."""
import argparse,hashlib,json
from pathlib import Path
import FreeCAD as App

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('baseline',type=Path)
args=parser.parse_args()
out=Path(__file__).resolve().parents[1]/'hardware/model';cad=out/'CyberTrack.FCStd'
old=App.openDocument(str(args.baseline.resolve()));new=App.openDocument(str(cad))
before={o.Name:o for o in old.Objects if hasattr(o,'Category')}
after={o.Name:o for o in new.Objects if hasattr(o,'Category')}
expected={'KeelSideFrameL','KeelSideFrameR'}
rows=[];frames=[]
for name,o in before.items():
    p=after.get(name)
    if p is None:rows.append(dict(name=name,passed=False,missing=True));continue
    same=o.Shape.cleaned().exportBrepToString()==p.Shape.cleaned().exportBrepToString()
    delta=0 if same else o.Shape.cut(p.Shape).Volume+p.Shape.cut(o.Shape).Volume
    changed=delta>1e-5
    rows.append(dict(name=name,difference_mm3=delta,changed=changed,
        passed=(changed if name in expected else not changed) and o.Category==p.Category and o.Label==p.Label))
    if name not in expected:continue
    added=p.Shape.cut(o.Shape);removed=o.Shape.cut(p.Shape).Volume
    overlaps=[];near=[];area=App.BoundBox(added.BoundBox);area.enlarge(8)
    for key,other in after.items():
        if key==name or not area.intersect(other.Shape.BoundBox):continue
        v=p.Shape.common(other.Shape).Volume if p.Shape.BoundBox.intersect(other.Shape.BoundBox) else 0
        if v>.01:overlaps.append(dict(object=key,category=other.Category,volume_mm3=v))
        near.append(dict(object=key,category=other.Category,distance_mm=added.distToShape(other.Shape)[0]))
    bb=p.Shape.optimalBoundingBox(False);ob=o.Shape.optimalBoundingBox(False)
    lug_name='Track'+('Left' if name.endswith('L') else 'Right')+'ShoulderLugs'
    old_lug_gap=o.Shape.distToShape(before[lug_name].Shape)[0]
    new_lug_gap=p.Shape.distToShape(after[lug_name].Shape)[0]
    row=dict(name=name,old_lug_clearance_mm=old_lug_gap,new_lug_clearance_mm=new_lug_gap,old_rear_y_mm=ob.YMax,new_rear_y_mm=bb.YMax,extension_mm=bb.YMax-ob.YMax,
        original_material_removed_mm3=removed,added_volume_mm3=added.Volume,thickness_mm=bb.XLength,
        max_z_mm=bb.ZMax,valid=p.Shape.isValid(),solids=len(p.Shape.Solids),unexpected_overlaps=overlaps,
        nearest_to_added_material=sorted(near,key=lambda x:x['distance_mm'])[:8])
    row['passed']=row['valid'] and row['solids']==1 and new_lug_gap>=old_lug_gap-1e-5 and removed<1e-5 and not overlaps and abs(row['extension_mm']-30)<1e-5 and abs(bb.XLength-1.5)<1e-5 and abs(bb.ZMax-90)<1e-5
    frames.append(row)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report=dict(revision='0.49',baseline_revision='0.48',baseline_sha256=sha(args.baseline),source_sha256=sha(cad),
    added=sorted(after.keys()-before.keys()),removed=sorted(before.keys()-after.keys()),
    unchanged_objects=sum(not r.get('changed',True) for r in rows),changed=[r['name'] for r in rows if r.get('changed')],
    objects=rows,frames=frames,physical_fit_verified=False,structural_strength_verified=False,
    passed=set(before)==set(after) and all(r['passed'] for r in rows) and len(frames)==2 and all(r['passed'] for r in frames))
(out/'side-frame-extension-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='objects'},ensure_ascii=False,indent=2))
assert report['passed']
