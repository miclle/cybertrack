"""Check the 0.50 integrated ignition pockets against a saved 0.49 assembly."""
import argparse
import hashlib
import json
from pathlib import Path
import FreeCAD as App
import Part
from effects_mount import mirror, zc
from breadboard_layout import box

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('baseline',type=Path)
args=parser.parse_args()
folder=Path(__file__).resolve().parents[1]/'hardware/model'
cad=folder/'CyberTrack.FCStd'
old=App.openDocument(str(args.baseline.resolve()));new=App.openDocument(str(cad))
before={o.Name:o for o in old.Objects if hasattr(o,'Category')}
after={o.Name:o for o in new.Objects if hasattr(o,'Category')}
removed_expected={f'ArcClampOuter{s}{i}' for s in 'LR' for i in (0,1)}
removed_expected|={f'Arc{kind}{s}{i}{j}' for kind in ('Screw','Insert','Tool') for s in 'LR' for i in (0,1) for j in (0,1)}
rows=[]
for name in sorted(before.keys()&after.keys()):
    a,b=before[name],after[name]
    same=a.Shape.cleaned().exportBrepToString()==b.Shape.cleaned().exportBrepToString()
    delta=0 if same else a.Shape.cut(b.Shape).Volume+b.Shape.cut(a.Shape).Volume
    changed=delta>1e-5
    rows.append(dict(name=name,changed=changed,difference_mm3=delta,
        passed=(changed if name=='BackpackShell' else not changed) and a.Category==b.Category))
shell=after['BackpackShell'].Shape
allowed=Part.makeCompound([mirror(box(57,62.5,51.5,90,107.5,126),s) for s in (1,-1)])
changed_volume=before['BackpackShell'].Shape.cut(shell).fuse(shell.cut(before['BackpackShell'].Shape))
outside=changed_volume.cut(allowed).Volume
sides=[]
for side,sign in [('L',1),('R',-1)]:
    # Retain the old outer ring silhouette below the removed overhanging stop.
    bands=Part.makeCompound([before[f'ArcClampOuter{side}{i}'].Shape for i in (0,1)])
    old_stop=box(87.75,81,114,89.75,89,126).fuse(box(74.3,81,124,89.75,89,126))
    bands=bands.cut(mirror(old_stop,sign))
    missing=bands.cut(shell).Volume
    top=mirror(box(74.3,81,124,89.75,89,126),sign)
    capped=shell.common(top).Volume
    # Continuous module sweep, keeping both soft liners and all fixed geometry.
    sweep=zc(12.75,54,214,sign*74,85)
    clashes=[];lead_hits=[]
    for name,obj in after.items():
        if name=='BackpackArc'+side or not sweep.BoundBox.intersect(obj.Shape.BoundBox):continue
        v=sweep.common(obj.Shape).Volume
        if v>.01:
            row=dict(object=name,volume_mm3=v)
            if obj.Category!='clearance':clashes.append(row)
            elif name.startswith('IgnitionRoute'):lead_hits.append(row)
    # A thin cross-section checks closed full rings (including the former split).
    ring_checks=[]
    for z in (60,86,114):
        annulus=zc(15.75,z,z+.1,sign*74,85).cut(zc(13.25,z-.1,z+.2,sign*74,85))
        ring_checks.append(dict(z_mm=z,missing_mm3=annulus.cut(shell).Volume))
    floor=zc(12.75,51.5,53,sign*74,85)
    floor_missing=floor.cut(shell).Volume
    sides.append(dict(side=side,old_outer_band_missing_mm3=missing,top_stop_volume_mm3=capped,
        continuous_module_up_90_overlaps=clashes,leads_left_in_place_overlaps=lead_hits,
        prerequisite='release and park the target leads before lifting the module',
        ring_sections=ring_checks,floor_missing_mm3=floor_missing,
        passed=missing<1e-5 and capped<1e-5 and not clashes and bool(lead_hits)
            and floor_missing<1e-5 and all(r['missing_mm3']<1e-5 for r in ring_checks)))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
removed=sorted(before.keys()-after.keys());added=sorted(after.keys()-before.keys())
report=dict(revision='0.50',baseline_revision='0.49',baseline_sha256=sha(args.baseline),source_sha256=sha(cad),
    saved_and_reopened=True,removed=removed,added=added,
    changed=[r['name'] for r in rows if r['changed']],unchanged_objects=sum(not r['changed'] for r in rows),
    objects=rows,integrated_shell_valid=shell.isValid(),integrated_shell_solids=len(shell.Solids),
    changes_outside_side_housings_mm3=outside,sides=sides,
    physical_fit_verified=False,axial_retention_verified=False,manufacturing_released=False,
    passed=set(removed)==removed_expected and not added and all(r['passed'] for r in rows)
        and shell.isValid() and len(shell.Solids)==1 and outside<1e-5 and all(r['passed'] for r in sides))
(folder/'ignition-housing-change-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='objects'},ensure_ascii=False,indent=2))
assert report['passed']
