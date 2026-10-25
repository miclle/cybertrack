"""Bound the 0.48 change against the superseded 0.47 exterior-route candidate."""
import argparse,hashlib,json
from pathlib import Path
import FreeCAD as App
import Part
from ignition_routing import paths,capsule

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('baseline',type=Path)
args=parser.parse_args()
folder=Path(__file__).resolve().parents[1]/'hardware/model'
current=folder/'CyberTrack.FCStd'
old=App.openDocument(str(args.baseline.resolve()));new=App.openDocument(str(current))
before={o.Name:o for o in old.Objects if hasattr(o,'Category')}
after={o.Name:o for o in new.Objects if hasattr(o,'Category')}
expected_changed={'LowerTub','KeelLid','PowerBank','PowerCableRoute','BatteryPullStrap','BatteryHatch','ChestGuardL','ChestGuardR'}
expected_changed.update(f'FrontEffectSleeve{s}{i}' for s in ('L','R') for i in (1,2))
expected_changed.update(r[0] for r in paths())
expected_added=sorted('IgnitionMOS'+s for s in ['Board','Support','Retainer','Carrier','PortL','PortR',
    'RetainerInsertInner','RetainerInsertOuter','RetainerScrewInner','RetainerScrewOuter',
    'MountInsertL','MountInsertR','MountScrewL','MountScrewR'])
rows=[]
for name,obj in before.items():
    other=after.get(name)
    if other is None:rows.append(dict(name=name,passed=False,missing=True));continue
    same=obj.Shape.exportBrepToString()==other.Shape.exportBrepToString()
    delta=0 if same else obj.Shape.cut(other.Shape).Volume+other.Shape.cut(obj.Shape).Volume
    changed=delta>=1e-5
    rows.append(dict(name=name,changed=changed,difference_mm3=delta,
        passed=(changed if name in expected_changed else not changed)
        and obj.Category==other.Category and (name in expected_changed or obj.Label==other.Label)))
added=sorted(after.keys()-before.keys());removed=sorted(before.keys()-after.keys())
def hits(shape,objects):
    result=[]
    for obj in objects:
        if shape.BoundBox.intersect(obj.Shape.BoundBox):
            volume=shape.common(obj.Shape).Volume
            if volume>.01:result.append(dict(object=obj.Name,volume_mm3=volume))
    return result

routes=[after[n] for n,_,_,_ in paths()]
service=[];projections=[]
for side,sign,prefix in [('L',1,'TrackLeft'),('R',-1,'TrackRight')]:
    group=[o.Shape for n,o in after.items() if n.startswith(prefix) or n in ('TrackMount'+side,'DriveCoupler'+side)]
    bb=Part.makeCompound(group).optimalBoundingBox(False)
    sweep=Part.makeBox(bb.XLength+60,bb.YLength,bb.ZLength,App.Vector(bb.XMin+min(0,sign*60),bb.YMin,bb.ZMin))
    clashes=hits(sweep,routes)
    service.append(dict(name='track_outward_'+side,method='conservative AABB sweep 60 mm outward',overlaps=clashes,passed=not clashes))
    # Explicitly test "not above the tracks", not merely 3-D nonintersection.
    belt=[o.Shape for n,o in after.items() if n.startswith(prefix) and any(k in n for k in ('RubberBand','TreadPads','ChevronTreads'))]
    bb=Part.makeCompound(belt).optimalBoundingBox(False)
    prism=Part.makeBox(bb.XLength,bb.YLength,250,App.Vector(bb.XMin,bb.YMin,0))
    clashes=hits(prism,routes)
    old_clashes=hits(prism,[before[n] for n,_,_,_ in paths()])
    projections.append(dict(side=side,method='belt bounding rectangle extruded vertically; conservative XY test',
        track_rectangle_xy_mm=[bb.XMin,bb.YMin,bb.XMax,bb.YMax],overlaps=clashes,
        superseded_route_overlaps=old_clashes,passed=not clashes and bool(old_clashes)))
    # The rear handoff sits above the module: release leads before upward removal.
    sweep=Part.makeCylinder(12.75,160,App.Vector(sign*74,85,54))
    clashes=hits(sweep,routes)
    service.append(dict(name='bare_module_up_'+side,method='bare cylinder sweep 90 mm, corridors left in place',
        overlaps=clashes,passed=not clashes,prerequisite='release and park the actual leads before upward module removal'))
expected_tub=before['LowerTub'].Shape.copy()
for _,points,radius,target in paths():expected_tub=expected_tub.cut(capsule(points,radius+.3 if target else radius+.4))
tub_delta=expected_tub.cut(after['LowerTub'].Shape).Volume+after['LowerTub'].Shape.cut(expected_tub).Volume
lid_deleted=before['KeelLid'].Shape.cut(after['KeelLid'].Shape).Volume
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report=dict(revision='0.48',baseline_revision='0.47',baseline_sha256=sha(args.baseline),source_sha256=sha(current),
    added=added,removed=removed,changed=[r['name'] for r in rows if r.get('changed')],
    unchanged_objects=sum(not r.get('changed',True) for r in rows),objects=rows,
    tub_difference_from_front_passage_cuts_mm3=tub_delta,original_lid_material_removed_mm3=lid_deleted,
    track_projection_checks=projections,additional_route_service_checks=service,
    scope='change bounds and track projection; module removal with leads installed is reported separately',
    passed=added==expected_added and not removed and all(r['passed'] for r in rows)
        and tub_delta<1e-5 and lid_deleted<1e-5 and all(r['passed'] for r in projections)
        and all(r['passed'] for r in service if r['name'].startswith('track_outward')))
(folder/'ignition-routing-change-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='objects'},ensure_ascii=False,indent=2))
assert report['passed']
