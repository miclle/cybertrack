"""Complete omitted rigid print parts without changing the existing five plates (FreeCAD)."""
import json,hashlib,shutil
from collections import Counter
from pathlib import Path
import FreeCAD as A,Part,MeshPart,Mesh
from update_pp02 import shape_rows,signature,same
ROOT=Path(__file__).resolve().parents[1];MODEL=ROOT/'hardware/model';OUT=MODEL/'completion-print';V=A.Vector
FUNCTIONAL=['WaterPod','BubblePod','EffectTray','IgnitionMOSCarrier','IgnitionMOSRetainer']
COSMETIC=['ChestAudioPanel','PrintChestGuardL','PrintChestGuardR','LowerChin','ChestBadge','WaterLidMark','BubbleLidMark']

def repair_tangent_posts(shape):
 mesh=MeshPart.meshFromShape(Shape=shape,LinearDeflection=.035,AngularDeflection=.08,Relative=False)
 vs,ts=mesh.Topology;edges=Counter(tuple(sorted(e)) for t in ts for e in [(t[0],t[1]),(t[1],t[2]),(t[2],t[0])]);add=[]
 for edge,count in edges.items():
  if count<=2:continue
  a,b=[vs[i] for i in edge];assert abs(a.x-b.x)<1e-5 and abs(a.y-b.y)<1e-5
  lo,hi=sorted((a.z,b.z));add.append(Part.makeCylinder(.35,hi-lo+.1,V(a.x,a.y,lo-.1)))
 if add:shape=shape.multiFuse(add).removeSplitter()
 return shape,len(add)

def prep(doc,delivery):
 changed=set();notes={}
 for name in ['EffectTray','IgnitionMOSCarrier']:
  obj=doc.getObject(name);fixed,count=repair_tangent_posts(obj.Shape)
  if count:
   obj.Shape=fixed;changed.add(name);obj.EvidenceBasis+='；2026-10-26 将相切柱/壁的零厚度连接补为半径0.35连接，孔位/接触面保持；打印待验。'
   print('TANGENT REPAIR',name,count,flush=True)
 # Flat mating surfaces use a 0.15 mm adhesive bond line; existing chassis is untouched.
 for name in ['ChestAudioPanel','LowerChin','ChestBadge']:
  obj=doc.getObject(name);obj.Shape=obj.Shape.cut(Part.makeBox(200,10,150,V(-100,-101.15,0))).removeSplitter();changed.add(name)
  obj.EvidenceBasis='2026-10-26 补齐打印：背面退让0.15 mm薄胶层；胶粘到既有底盘，固定强度待实测。'
 for side in 'LR':
  guard,accent=[doc.getObject(n+side) for n in ['ChestGuard','ChestAccent']]
  if delivery and guard is None and doc.getObject('PrintChestGuard'+side):continue
  s=guard.Shape.fuse(accent.Shape).removeSplitter().cut(Part.makeBox(200,10,150,V(-100,-101.15,0))).removeSplitter()
  name='PrintChestGuard'+side;o=doc.getObject(name) or doc.addObject('PartDesign::Feature',name);o.Shape=s;o.Label='前舱一体侧甲与嵌条 · '+side
  if 'SourceFeatures' not in o.PropertiesList:o.addProperty('App::PropertyStringList','SourceFeatures')
  o.SourceFeatures=[guard.Name,accent.Name]
  if 'Category' not in o.PropertiesList:o.addProperty('App::PropertyString','Category')
  o.Category='exterior'
  if 'EvidenceBasis' not in o.PropertiesList:o.addProperty('App::PropertyString','EvidenceBasis')
  o.EvidenceBasis='2026-10-26 两件合为一体，原穿线孔保持；背面0.15 mm胶层，既有底盘不改。'
  changed.add(name)
  if delivery:
   for old in [guard.Name,accent.Name]:changed.add(old);doc.removeObject(old)
  else:
   guard.Visibility=False;accent.Visibility=False
 for name in ['WaterLidMark','BubbleLidMark']:
  o=doc.getObject(name);b=o.Shape.BoundBox;o.Shape=Part.makeBox(b.XLength,.8,b.ZLength,V(b.XMin,95.15,b.ZMin));changed.add(name)
  o.EvidenceBasis='2026-10-26 识别条厚0.8 mm／背面预留0.15 mm胶层；贴合既有背包，不改背包。'
 doc.recompute();return changed

def main():
 OUT.mkdir(exist_ok=True);base=OUT/'baseline';base.mkdir(exist_ok=True)
 paths={'delivery':MODEL/'CyberTrack.FCStd','source':MODEL/'source/CyberTrack-design.FCStd'};docs={};before={};changed={};report={'parts':{},'unchanged':{},'physical_fit_verified':False}
 for key,path in paths.items():
  dest=base/(key+'.FCStd')
  if not dest.exists():shutil.copy2(path,dest)
  doc=A.openDocument(str(path));docs[key]=doc;before[key]=shape_rows(doc);changed[key]=prep(doc,key=='delivery')
 d=docs['delivery'];objects=[o for o in d.Objects if hasattr(o,'Shape') and not o.isDerivedFrom('App::DocumentObjectGroup') and not o.Shape.isNull() and getattr(o,'Category','')!='clearance']
 for name in FUNCTIONAL+COSMETIC:
  s=d.getObject(name).Shape;assert s.isValid() and len(s.Solids)==1,name
  overlaps=[]
  for o in objects:
   if o.Name==name or not s.BoundBox.intersect(o.Shape.BoundBox):continue
   volume=s.common(o.Shape).Volume
   if volume>.01:overlaps.append([o.Name,volume])
  assert not overlaps,(name,overlaps)
  angle=-90 if name in COSMETIC and not name.endswith('LidMark') else 90 if name.endswith('LidMark') else 0
  t=s.copy()
  if angle:t.rotate(V(),V(1,0,0),angle)
  b=t.optimalBoundingBox(False);offset=(-(b.XMin+b.XMax)/2,-(b.YMin+b.YMax)/2,-b.ZMin);t.translate(V(*offset))
  t.exportBrep(str(OUT/(name+'.brep')));t.exportStep(str(OUT/(name+'.step')))
  mesh=MeshPart.meshFromShape(Shape=t,LinearDeflection=.035,AngularDeflection=.08,Relative=False);mesh.write(str(OUT/(name+'.stl')))
  back=Mesh.Mesh(str(OUT/(name+'.stl')));assert back.isSolid() and back.countComponents()==1 and not back.hasNonManifolds(),name
  step=Part.Shape();step.read(str(OUT/(name+'.step')));delta=step.cut(t).Volume+t.cut(step).Volume;assert delta<.01,name
  report['parts'][name]={'valid':True,'solids':1,'size':[b.XLength,b.YLength,b.ZLength],'rotation_x':angle,'translation':offset,'volume':s.Volume,'facets':back.CountFacets,'step_delta_mm3':delta,'overlaps':overlaps}
 for key,doc in docs.items():
  for name,sig in before[key].items():
   if name not in changed[key]:assert same(sig,signature(doc.getObject(name).Shape)),(key,name)
  report['unchanged'][key]=len(set(before[key])-changed[key]);expected=shape_rows(doc);doc.save();A.closeDocument(doc.Name);again=A.openDocument(str(paths[key]));actual=shape_rows(again)
  assert actual.keys()==expected.keys() and all(same(actual[n],expected[n]) for n in actual)
  docs[key]=again
 d=docs['delivery'];Part.export([o for o in d.Objects if hasattr(o,'Shape') and not o.isDerivedFrom('App::DocumentObjectGroup') and getattr(o,'Category','') not in ('clearance','envelope')],str(MODEL/'CyberTrack.step'))
 report['model_sha256']={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in paths.items()};report['saved_reopened']=True
 (OUT/'geometry-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('COMPLETE',json.dumps(report),flush=True)
