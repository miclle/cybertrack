"""Audit the localized BOOT change against the supplied 0.53 design source.

Unchanged regenerated shapes use topology/geometry signatures, not an expensive
whole-assembly Boolean equivalence claim. Changed features are re-created from
the baseline and compared with exact solid Boolean differences.
"""
import argparse
import json
from pathlib import Path
import FreeCAD as App
import Part
from boot_button import apply, check
from build_tank import sha


def signature(shape):
    b=shape.optimalBoundingBox(False)
    return dict(volume=shape.Volume,area=shape.Area,
                topology=[len(shape.Solids),len(shape.Faces),len(shape.Edges),len(shape.Vertexes)],
                bbox=[getattr(b,k) for k in ('XMin','YMin','ZMin','XMax','YMax','ZMax')],
                vertices=sorted((tuple(v.Point) for v in shape.Vertexes),key=lambda p:tuple(round(x,5) for x in p)))


def compare(a,b):
    return (a['topology']==b['topology'] and abs(a['volume']-b['volume'])<1e-5
            and abs(a['area']-b['area'])<1e-5
            and max(abs(x-y) for x,y in zip(a['bbox'],b['bbox']))<1e-5
            and all(max(abs(x-y) for x,y in zip(p,q))<1e-5 for p,q in zip(a['vertices'],b['vertices'])))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline',type=Path)
    parser.add_argument('--model',type=Path,default=Path(__file__).resolve().parents[1]/'hardware/model')
    args=parser.parse_args();root=args.model.resolve()
    baseline=App.openDocument(str(args.baseline.resolve()))
    old={o.Name:o.Shape.copy() for o in baseline.Objects if hasattr(o,'Category')}
    # Verify apply() itself does not mutate unrelated baseline geometry.
    before={o.Name:o.Shape.exportBrepToString() for o in baseline.Objects if hasattr(o,'Category')}
    def add(name,label,shape,category,color,basis):
        o=baseline.addObject('Part::Feature',name);o.Label=label;o.Shape=shape
        for key,value in [('Category',category),('EvidenceBasis',basis)]:
            o.addProperty('App::PropertyString',key);setattr(o,key,value)
        return o
    layout=apply(baseline,add)
    expected={o.Name:o.Shape.copy() for o in baseline.Objects if hasattr(o,'Category')}
    changed=['ShoulderRailR','StopControl','BubbleGunStopAccess']
    removed=['StopPlinth'];added=['StopBody','StopNut','StopSignalRoute']
    unchanged=sorted(set(old)-set(changed+removed))
    assert all(before[n]==baseline.getObject(n).Shape.exportBrepToString() for n in unchanged)
    source=root/'source/CyberTrack-design.FCStd'
    current=App.openDocument(str(source))
    actual={o.Name:o.Shape for o in current.Objects if hasattr(o,'Category')}
    assert set(actual)-set(old)==set(added) and set(old)-set(actual)==set(removed)
    signatures=[];exact=[]
    for n in unchanged:
        assert compare(signature(expected[n]),signature(actual[n])),n
        signatures.append(n)
    for n in changed+added:
        delta=expected[n].cut(actual[n]).Volume+actual[n].cut(expected[n]).Volume
        assert delta<1e-5,(n,delta)
        exact.append(dict(name=n,symmetric_difference_mm3=delta))
    extension=actual['ShoulderRailR'].cut(old['ShoulderRailR'])
    patch=Part.makeBox(14,24,31,App.Vector(-43,-30,89))
    assert extension.cut(patch).Volume<1e-5
    assert old['ShoulderRailR'].cut(actual['ShoulderRailR']).Volume<1e-5
    assert len(actual['ShoulderRailR'].Solids)==1
    local=check(current);assert local['passed'],local
    # Check the signal corridor as an installed obstacle, with explicit removal
    # before the electronics tray is extracted. Do not treat it as a solid cable.
    from refine_assembly import check_service_paths
    try:
        current.StopSignalRoute.Category='envelope'
        route_service=check_service_paths(current)
    finally:
        current.StopSignalRoute.Category='clearance'
    assert route_service['passed'],route_service
    report=dict(revision='0.54',passed=True,baseline_sha256=sha(args.baseline),
                source_document='source/CyberTrack-design.FCStd',source_sha256=sha(source),
                delivery_sha256=sha(root/'CyberTrack.FCStd'),changed=changed,removed=removed,added=added,
                unchanged_apply_native_brep_count=len(unchanged),
                regenerated_unchanged_signature_count=len(signatures),
                unchanged_signature_method='solid/face/edge/vertex counts, area, volume, bbox and sorted vertices; 1e-5 tolerance; not a full Boolean equivalence proof',
                regenerated_unchanged_signature_names=signatures,changed_expected_geometry_checks=exact,
                shoulder_added_mm3=extension.Volume,shoulder_added_patch_mm=[-43,-30,89,-29,-6,120],
                power_switch_names_unchanged=[n for n in unchanged if n.startswith('PowerSwitch')]+['KeelLid'],
                signal_corridor_service_check=route_service,layout=layout,
                hardware_selected=False,physical_fit_verified=False,electrical_verified=False)
    (root/'boot-button-change-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('regenerated_unchanged_signature_names','signal_corridor_service_check','layout')},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
