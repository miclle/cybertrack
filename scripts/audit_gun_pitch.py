"""Verify the saved gun elevation against its previous revision, preserving unrelated geometry."""
import argparse
import hashlib
import json
from pathlib import Path
import FreeCAD as A
import Part
from gun_pitch import moved, ANGLE, OFFSETS
from head_lift import head_members

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('baseline',type=Path)
parser.add_argument('--baseline-report',type=Path,required=True)
parser.add_argument('--current',type=Path,default=Path('hardware/model/CyberTrack.FCStd'))
parser.add_argument('--output',type=Path,default=Path('hardware/model/gun-pitch-audit.json'))
args=parser.parse_args()
old=A.openDocument(str(args.baseline.resolve()));new=A.openDocument(str(args.current.resolve()))
before={o.Name:o.Shape for o in old.Objects if hasattr(o,'Category')}
after={o.Name:o.Shape for o in new.Objects if hasattr(o,'Category')}
baseline_report=json.loads(args.baseline_report.read_text())
prior=baseline_report['gun_pitch']
current_report=json.loads(Path('hardware/model/readback.json').read_text())
assert baseline_report['files_sha256']['CyberTrack.FCStd']==hashlib.sha256(args.baseline.read_bytes()).hexdigest()
assert current_report['files_sha256']['CyberTrack.FCStd']==hashlib.sha256(args.current.read_bytes()).hexdigest()
assert current_report['gun_pitch']['elevation_degrees']==-ANGLE
rigid_label=f"rigid {prior['elevation_degrees']:g} to {-ANGLE:g} degrees"
routes={'WaterHoseRoute','WaterGunHoseClearance','BubbleGunHoseRoute','BubbleGunHoseClearance'}
redesigned=routes|{'ShoulderRailL','ShoulderRailR'}
rows=[]
for name in sorted(before.keys() & after.keys()):
    expected=before[name].cleaned()
    kind='water' if name.startswith('WaterGun') else 'bubble' if name.startswith('BubbleGun') else None
    rigid=kind and name not in redesigned|{'BubbleGunStopAccess'}
    if rigid:
        expected.translate(-A.Vector(*prior['translation_world_mm'][kind]))
        expected.rotate(A.Vector(*prior['pivot_world_mm'][kind]),A.Vector(1,0,0),-prior['rotation_about_X_degrees'])
        expected=moved(expected,kind)
    actual=after[name].cleaned()
    identical=expected.exportBrepToString()==actual.exportBrepToString()
    difference=0.0 if identical else expected.cut(actual).Volume+actual.cut(expected).Volume
    rows.append({'name':name,'expectation':rigid_label if rigid else 'support/hose rebuild' if name in redesigned else 'unchanged',
                 'difference_from_expected_mm3':difference,'passed':name in redesigned or difference<=1e-5})
head=Part.makeCompound([o.Shape for o in head_members(new) if o.Category!='clearance'])
neck=Part.makeCompound([o.Shape for o in new.Objects if hasattr(o,'Category') and o.Name.startswith('Neck')])
clearances=[]
for gun in ('WaterGunMaximumEnvelope','BubbleGunInspectionEnvelope'):
    shape=after[gun]
    targets={'head':head,'neck':neck,**{name:after[name] for name in ('KeelLid','LowerTub','WaterModule','BubbleModule')}}
    for name,target in targets.items():
        clearances.append({'gun':gun,'target':name,'distance_mm':shape.distToShape(target)[0],
                           'overlap_mm3':shape.common(target).Volume})
for moving,target in (('WaterGunCradle','KeelLid'),('BubbleGunHoseRoute','BubbleGunConnectorService'),
                      ('BubbleGunHoseClearance','BubbleGunConnectorService')):
    a,b=after[moving],after[target]
    clearances.append({'gun':moving,'target':target,'distance_mm':a.distToShape(b)[0],
                       'overlap_mm3':a.common(b).Volume})
added=sorted(after.keys()-before.keys());removed=sorted(before.keys()-after.keys())
support_contacts=[]
for support,cradle in (('ShoulderRailL','WaterGunCradle'),('ShoulderRailR','BubbleGunCradle')):
    a,b=after[support],after[cradle]
    area=sum(f.common(g).Area for f in a.Faces for g in b.Faces if f.BoundBox.intersect(g.BoundBox))
    overlap=a.common(b).Volume
    support_contacts.append({'support':support,'cradle':cradle,'face_contact_area_mm2':area,
                             'overlap_mm3':overlap,'passed':area>1e-5 and overlap<.01})
report={'baseline_revision':baseline_report['design_revision'],'revision':current_report['design_revision'],'baseline_sha256':hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
        'source_sha256':hashlib.sha256(args.current.read_bytes()).hexdigest(),
        'previous_elevation_degrees':prior['elevation_degrees'],'elevation_degrees':-ANGLE,'head_lift_mm':25,
        'translation_world_mm':{k:list(v) for k,v in OFFSETS.items()},
        'rigid_gun_object_count':sum(r['expectation']==rigid_label for r in rows),
        'unchanged_object_count':sum(r['expectation']=='unchanged' for r in rows),
        'rebuilt_supports_and_hoses':sorted(redesigned),'added':added,'removed':removed,
        'objects':rows,'clearances':clearances,'support_contacts':support_contacts,
        'passed':not added and not removed and all(r['passed'] for r in rows)
                 and all(r['overlap_mm3']<.01 and r['distance_mm']>0 for r in clearances)
                 and all(r['passed'] for r in support_contacts),
        'range_improvement_verified':False,'physical_fit_verified':False,'manufacturing_released':False,
        'limits':'Nominal CAD and prescribed service paths only. Spray range, bubble output, drainage, hose bending and adhesive retention require physical tests.'}
args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='objects'},indent=2))
A.closeDocument(old.Name);A.closeDocument(new.Name)
if not report['passed']:raise SystemExit(1)
