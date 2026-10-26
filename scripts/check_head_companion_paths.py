"""Run with FreeCADcmd: compare native screw-seat material with emitted extrusion paths."""
import sys,json,math,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import FreeCAD as A,Part
from check_head_print_paths import layers,distance
root=Path(__file__).resolve().parents[1];base=root/'hardware/model/print-parts/PP07-slicing';doc=A.openDocument(str(root/'hardware/model/CyberTrack.FCStd'))
results={}
for part,candidates in [('Crown',['crown-arachne-seats','combined']),('Tray',['tray-wide','combined'])]:
 shape=doc.getObject('PrintCrown' if part=='Crown' else 'ElectronicsTray').Shape
 objects=[('baseline',base/part/(part+'.3mf'))]+[(n,base/'head-set-speed'/n/('Head-Crown-Tray-FAST.3mf' if n=='combined' else n+'.3mf')) for n in candidates]
 targets=[]
 for x in (-64,64) if part=='Crown' else (-57,57):
  for y in (-52,7) if part=='Crown' else (-40,-5):
   for z in (216.65,217.4,218.4) if part=='Crown' else (172.0,173.3):targets.append((x,y,z))
 allrows=[]
 for name,project in objects:
  # Exclude all support variants, including transition lines, and support-only Z levels.
  ls={h:[s for s in seg if not s[3].startswith('Support')] for h,seg in layers(project).items()}
  ls={h:s for h,s in ls.items() if s};heights=sorted(ls);rows=[];flip='flipped' in name
  for x,y,z in targets:
   px=x+128;py=128+(y+26)*(-1 if flip else 1) if part=='Crown' else y+155.5
   if name=='combined':py+=-50 if part=='Crown' else 71
   pz=(228-z if flip else z-196) if part=='Crown' else z-171.5
   h=min(heights,key=lambda a:abs(a-pz));idx=heights.index(h);thickness=h-(heights[idx-1] if idx else 0)
   worldz=(228-(h-thickness/2) if flip else 196+h-thickness/2) if part=='Crown' else 171.5+h-thickness/2
   r=3.5 if part=='Crown' else 4;w=2*r
   local=shape.common(Part.makeBox(w,w,.002,A.Vector(x-r,y-r,worldz-.001)))
   assert local.Volume>1e-8
   nearby=[s for s in ls[h] if max(s[0][0],s[1][0])+s[2]/2>=px-r and min(s[0][0],s[1][0])-s[2]/2<=px+r and max(s[0][1],s[1][1])+s[2]/2>=py-r and min(s[0][1],s[1][1])-s[2]/2<=py+r]
   total=covered=0
   for i in range(math.ceil(w/.2)):
    for j in range(math.ceil(w/.2)):
     dx=-r+(i+.5)*.2;dy=-r+(j+.5)*.2
     if math.hypot(dx,dy)>r or not local.isInside(A.Vector(x+dx,y+dy,worldz),1e-6,True):continue
     total+=1;covered+=any(distance(px+dx,py+dy*(-1 if flip else 1),a,b)<=width/2+.035 for a,b,width,_ in nearby)
   assert total>0
   rows.append(dict(x=x,y=y,target_world_z=z,sampled_print_z=h,coverage=covered/total,points=total,segments=len(nearby)))
  allrows.append(dict(candidate=name,project_sha256=hashlib.sha256(project.read_bytes()).hexdigest(),sections=rows))
 baseline=allrows[0]
 for row in allrows[1:]:
  row['passed']=all(a['coverage']>=.85 and a['coverage']>=b['coverage']-.05 for a,b in zip(row['sections'],baseline['sections']))
  row['minimum_coverage']=min(a['coverage'] for a in row['sections'])
  print(part,row['candidate'],row['passed'],row['minimum_coverage'],flush=True)
 results[part]=allrows
out=dict(results=results,method='Exact native material mask, 0.2 mm samples in screw-seat circles; support excluded. Each candidate section >=85% footprint coverage and no more than 5 percentage points below baseline. 12 crown seat sections and 8 tray-ear sections per candidate.',limits='Conservative path-presence comparison, not calibrated strength, all-layer connectivity or fit proof.')
(base/'head-set-speed/delivery-critical-sections.json').write_text(json.dumps(out,indent=2)+'\n');A.closeDocument(doc.Name)

assert all(row['passed'] for rows in results.values() for row in rows[1:]), 'Critical section screen failed'
