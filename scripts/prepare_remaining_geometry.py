"""Scoped PP02/LC04 repair, native round trip and printable orientations (FreeCAD)."""
import hashlib,json,shutil
from pathlib import Path
import FreeCAD as A,Part,MeshPart,Mesh
from gun_pitch import moved
from bubble_gun_mount import ring_shape
from remaining_print_repairs import connect_lid_posts
from update_pp02 import shape_rows,signature,same
ROOT=Path(__file__).resolve().parents[1];MODEL=ROOT/'hardware/model';OUT=MODEL/'remaining-print'
NAMES={'PP01':'PrintWaterCradle','PP02':'PrintBubbleCradle','PP03':'PrintBackpack','LC04':'KeelLid'}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 OUT.mkdir(exist_ok=True);backup=OUT/'baseline';backup.mkdir(exist_ok=True)
 paths={'source':MODEL/'source/CyberTrack-design.FCStd','delivery':MODEL/'CyberTrack.FCStd'}
 before={};docs={}
 for key,path in paths.items():
  dest=backup/(key+'.FCStd')
  if not dest.exists():shutil.copy2(path,dest)
  docs[key]=A.openDocument(str(path));before[key]=shape_rows(docs[key])
 src,d=docs['source'],docs['delivery']
 src.BubbleGunRing.Shape=moved(ring_shape(),'bubble');src.recompute()
 d.PrintBubbleCradle.Shape=src.PrintBubbleCradle.Shape.copy()
 lid=connect_lid_posts(d.KeelLid.Shape,[d.getObject(n).Shape for n in ['PrintLowerTub','ShoulderRailL','ShoulderRailR']])
 d.KeelLid.Shape=lid;src.KeelLid.Shape=lid.copy()
 src.BubbleGunRing.Label2='外径39／偏心内孔32＋枪壳同心Ø32.8下缘避让／缺口7.5×2.3／支脚20'
 for doc in docs.values():
  doc.PrintBubbleCradle.EvidenceBasis='2026-10-26 打印修正：圆环下缘增加Ø32.8同心避让，枪壳径向0.65候选；实物待验。'
  doc.KeelLid.EvidenceBasis='2026-10-26 打印修正：两根3 mm内向连接筋连接原承板柱，安装孔位不变；实物待验。'
  doc.recompute()
 report={'scope':['PrintBubbleCradle','KeelLid'],'baseline':{k:sha(backup/(k+'.FCStd')) for k in paths},'unchanged':{},'parts':{},'physical_fit_verified':False}
 for key,doc in docs.items():
  changed={'PrintBubbleCradle','KeelLid'}|({'BubbleGunRing'} if key=='source' else set())
  unchanged=set(before[key])-changed
  assert all(same(before[key][n],signature(doc.getObject(n).Shape)) for n in unchanged),key
  report['unchanged'][key]=len(unchanged)
 # Include physical components and nominal envelopes, but exclude clearance space.
 objects=[o for o in d.Objects if hasattr(o,'Shape') and not o.isDerivedFrom('App::DocumentObjectGroup') and not o.Shape.isNull() and getattr(o,'Category','')!='clearance']
 for ident,name in NAMES.items():
  shape=d.getObject(name).Shape;assert shape.isValid() and len(shape.Solids)==1,name
  overlaps=[]
  for o in objects:
   if o.Name==name or not shape.BoundBox.intersect(o.Shape.BoundBox):continue
   volume=shape.common(o.Shape).Volume
   if volume>.01:overlaps.append({'object':o.Name,'volume_mm3':volume})
  assert not overlaps,(name,overlaps)
  row={'name':name,'signature':signature(shape),'valid':True,'solids':1,'overlaps':overlaps}
  if ident=='PP02':row['shell_clearance_mm']=shape.distToShape(d.BubbleGunShell.Shape)[0]
  row['orientations']=[]
  local=moved(shape,'water' if ident=='PP01' else 'bubble',True) if ident in ('PP01','PP02') else shape.copy()
  variants={'base':(0,0,0)}
  if ident=='PP03':variants.update(back=(90,0,0))
  if ident=='LC04':variants.update(flipped=(180,0,0))
  for orientation,angles in variants.items():
   s=local.copy()
   for axis,angle in zip([(1,0,0),(0,1,0),(0,0,1)],angles):
    if angle:s.rotate(A.Vector(),A.Vector(*axis),angle)
   b=s.BoundBox;offset=(-(b.XMin+b.XMax)/2,-(b.YMin+b.YMax)/2,-b.ZMin);s.translate(A.Vector(*offset))
   stem=ident+'-'+orientation;s.exportBrep(str(OUT/(stem+'.brep')));s.exportStep(str(OUT/(stem+'.step')))
   mesh=MeshPart.meshFromShape(Shape=s,LinearDeflection=.06,AngularDeflection=.12,Relative=False)
   mesh.write(str(OUT/(stem+'.stl')));back=Mesh.Mesh(str(OUT/(stem+'.stl')))
   assert back.isSolid() and not back.hasNonManifolds() and back.countComponents()==1,stem
   check=Part.Shape();check.read(str(OUT/(stem+'.step')))
   delta=check.cut(s).Volume+s.cut(check).Volume;assert delta<.01 and len(check.Solids)==1,stem
   row['orientations'].append({'stem':stem,'size':[b.XLength,b.YLength,b.ZLength],'angles':angles,'translation':offset,'facets':back.CountFacets,'stl_sha256':sha(OUT/(stem+'.stl')),'step_delta_mm3':delta})
  report['parts'][ident]=row
 # Save only after every candidate check succeeds.
 for key,doc in docs.items():
  expected=shape_rows(doc);doc.save();A.closeDocument(doc.Name)
  check=A.openDocument(str(paths[key]));actual=shape_rows(check)
  assert set(actual)==set(expected) and all(same(actual[n],expected[n]) for n in actual)
  docs[key]=check
 d=docs['delivery']
 assembly=[o for o in d.Objects if hasattr(o,'Shape') and not o.isDerivedFrom('App::DocumentObjectGroup') and getattr(o,'Category','') not in ('clearance','envelope')]
 Part.export(assembly,str(MODEL/'CyberTrack.step'))
 for ident,name in [('PP02','BubbleCradle')]:
  # Export index points to the actual bed-oriented geometry used for slicing.
  for ext in ('stl','step'):shutil.copy2(OUT/(ident+'-base.'+ext),MODEL/'print-parts'/(ident+'-'+name+'.'+ext))
 for ext in ('stl','step'):shutil.copy2(OUT/('LC04-base.'+ext),MODEL/'l298n-compact'/('LC04-KeelLid.'+ext))
 report['saved_reopened']=True;report['files']={k:sha(p) for k,p in paths.items()}
 (OUT/'geometry-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
