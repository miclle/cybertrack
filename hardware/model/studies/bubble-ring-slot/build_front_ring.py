import FreeCAD as App
import Part
import json,hashlib
from pathlib import Path
V=App.Vector
out=Path('hardware/model/studies/bubble-ring-slot').resolve()
def box(a,b,c,d,e,f):return Part.makeBox(d-a,e-b,f-c,V(a,b,c))
ring=Part.makeCylinder(18.55,5,V(),V(0,1,0)).cut(Part.makeCylinder(16.05,5,V(),V(0,1,0)))
lo=ring.common(box(-30,-1,-30,30,6,-.15)).fuse(box(-5,0,-23,5,5,-17))
hi=ring.common(box(-30,-1,.15,30,6,30))
for x in (-24,17):
 lo=lo.fuse(box(x,0,-4,x+7,5,-.15))
 hi=hi.fuse(box(x,0,.15,x+7,5,4))
for x in (-20.5,20.5):
 hole=Part.makeCylinder(1.6,10,V(x,2.5,-5))
 lo=lo.cut(hole);hi=hi.cut(hole)
lo=lo.removeSplitter();hi=hi.removeSplitter()
doc=App.newDocument('BubbleFrontRingStudy');doc.Label='泡泡枪前圆环候选／后槽位置待确认'
for name,shape in [('LowerRing',lo),('UpperRing',hi)]:
 assert shape.isValid() and len(shape.Solids)==1
 o=doc.addObject('Part::Feature',name);o.Shape=shape
 o.addProperty('App::PropertyString','EvidenceBasis');o.EvidenceBasis='枪口外径31.5为用户尺寸；孔32.1、外径37.1、厚5及配合间隙均为设计候选。未放入整机。'
assert lo.common(hi).Volume<1e-5
witness=Part.makeCylinder(15.75,5,V(),V(0,1,0))
assert lo.common(witness).Volume<1e-5 and hi.common(witness).Volume<1e-5
assert abs(lo.distToShape(witness)[0]-.3)<1e-5
cad=out/'FrontRing-candidate.FCStd';step=out/'FrontRing-candidate.step'
doc.recompute();doc.saveAs(str(cad));Part.export(doc.Objects,str(step));App.closeDocument(doc.Name)
saved=App.openDocument(str(cad))
for name,shape in [('LowerRing',lo),('UpperRing',hi)]:
 actual=saved.getObject(name).Shape
 assert actual.isValid() and actual.cut(shape).Volume+shape.cut(actual).Volume<1e-5
App.closeDocument(saved.Name)
s=Part.Shape();s.read(str(step));assert s.isValid() and len(s.Solids)==2
assert abs(s.Volume-lo.Volume-hi.Volume)<.01
report={'status':'front-ring-only dimensional study; not installed in assembly','user_muzzle_diameter_mm':31.5,
 'candidate_bore_mm':32.1,'candidate_outer_diameter_mm':37.1,'candidate_axial_width_mm':5,
 'radial_clearance_mm':.3,'split_gap_mm':.3,'candidate_hole_diameter_mm':3.2,'two_ring_halves_valid':True,
 'muzzle_cylinder_overlap_mm3':0,'native_readback_passed':True,'step_readback_passed':True,
 'rear_tab_position_confirmed':False,'assembly_interference_checked':False,'physical_fit_verified':False,
 'files_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (cad,step)}}
(out/'front-ring-readback.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
