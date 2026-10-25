"""Verify 0.53 changes only the centre deck and adds the four switch objects."""
import argparse
import hashlib
import json
from pathlib import Path
import FreeCAD as App
from power_switch import NAMES, check


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline',type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    path=root/'hardware/model/source/CyberTrack-design.FCStd'
    old_doc=App.openDocument(str(args.baseline))
    before={o.Name:o.Shape.copy() for o in old_doc.Objects if hasattr(o,'Category')}
    App.closeDocument(old_doc.Name)
    doc=App.openDocument(str(path))
    after={o.Name:o.Shape for o in doc.Objects if hasattr(o,'Category')}
    assert set(after)-set(before)==set(NAMES)
    assert not set(before)-set(after)
    changed=[];unchanged=[]
    for name,old in before.items():
        new=after[name]
        identical=old.exportBrepToString()==new.exportBrepToString()
        delta=0 if identical else old.cut(new).Volume+new.cut(old).Volume
        if delta>1e-5:changed.append(dict(name=name,difference_mm3=delta))
        else:unchanged.append(name)
    assert {r['name'] for r in changed}=={'KeelLid'},changed
    result=check(doc)
    assert result['passed'],result
    # Scope stays within the declared foredeck patch, including relief bores.
    import Part
    patch=Part.makeBox(28,24,19,App.Vector(-14,-76,68))
    added=after['KeelLid'].cut(before['KeelLid'])
    removed=before['KeelLid'].cut(after['KeelLid'])
    assert added.cut(patch).Volume+removed.cut(patch).Volume<1e-5
    engagement=[]
    for x in (-7.4,7.4):
        origin=App.Vector(x,-64,75.6)
        ring=Part.makeCylinder(1,5.5,origin).cut(Part.makeCylinder(.8,5.5,origin))
        missing=ring.cut(after['KeelLid']).Volume
        assert missing<1e-5
        engagement.append(dict(x_mm=x,nominal_depth_mm=5.5,missing_material_mm3=missing,
                               thread_strength_verified=False))
    report=dict(passed=True,baseline_sha256=hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
                source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                changed=changed,unchanged_count=len(unchanged),unchanged=unchanged,added=NAMES,
                added_material_mm3=added.Volume,removed_material_mm3=removed.Volume,
                patch_bbox_mm=[-14,-76,68,14,-52,87],
                screw_engagement_material=engagement,
                original_head_and_drive_preserved=True,physical_fit_verified=False)
    (root/'hardware/model/power-switch-change-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='unchanged'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
