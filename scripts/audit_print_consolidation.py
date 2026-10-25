"""Compare 0.51 source geometry to a supplied pre-consolidation FCStd."""
import argparse
import hashlib
import json
from pathlib import Path
import FreeCAD as App
import Part

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('baseline',type=Path)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
model=root/'hardware/model'
path=model/'CyberTrack.FCStd'
tree=model/'model-tree-audit.json'
if tree.exists():
    tree_data=json.loads(tree.read_text())
    if tree_data['delivery_sha256']==hashlib.sha256(path.read_bytes()).hexdigest():
        path=model/tree_data['source_document']
old=App.openDocument(str(args.baseline.resolve()))
new=App.openDocument(str(path))
a={o.Name:o for o in old.Objects if hasattr(o,'Category')}
b={o.Name:o for o in new.Objects if hasattr(o,'Category')}
assert set(a)==set(b)
allowed={'HeadCrownShell','NeckCrossbar','RearBulkhead','NeckOuterWebL','NeckOuterWebR'}
changes=[]
for name,source in a.items():
    current=b[name]
    before,after=source.Shape,current.Shape
    if before.exportBrepToString()==after.exportBrepToString():
        added=removed=0
    else:
        added=after.cut(before).Volume
        removed=before.cut(after).Volume
    if added+removed>1e-5:
        changes.append({'name':name,'added_mm3':added,'removed_mm3':removed})
        assert name in allowed and removed<1e-5,changes[-1]
assert {r['name'] for r in changes}==allowed
from print_consolidation import groups, connect_features
bounds=[]
for name,label,members in groups(new):
    before=Part.makeCompound([a[n].Shape for n in members]).optimalBoundingBox(False)
    after=new.getObject(name).Shape.optimalBoundingBox(False)
    delta=max(abs(getattr(before,k)-getattr(after,k)) for k in ('XMin','YMin','ZMin','XMax','YMax','ZMax'))
    assert delta<1e-5,(name,delta)
    bounds.append({'part':name,'maximum_bbox_change_mm':delta})
# Independently regenerate the five permitted source-feature changes on the baseline, then
# compare their saved geometry, not just volume or bounding boxes.
connect_features(old)
expected_changes=[]
for name in allowed:
    expected,actual=old.getObject(name).Shape,new.getObject(name).Shape
    difference=expected.cut(actual).Volume+actual.cut(expected).Volume
    assert difference<1e-5,(name,difference)
    expected_changes.append({'name':name,'expected_geometry_difference_mm3':difference})
report={'revision':'0.51','source_document':str(path.relative_to(model)),'baseline_sha256':hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
        'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source_feature_count':len(a),
        'expected_saved_geometry_checks':expected_changes,'changed_source_features':changes,'unchanged_source_features':len(a)-len(changes),
        'merged_part_bbox_changes':bounds,'passed':True,
        'scope':'Only crown ties, fixed crossbar gap filling and internal wet-bay seam ties and neck bore webs add material; six groups retain exact exterior bounds. Appearance checked separately in renders.',
        'physical_fit_verified':False}
(root/'hardware/model/print-consolidation-change-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
App.closeDocument(new.Name);App.closeDocument(old.Name)
