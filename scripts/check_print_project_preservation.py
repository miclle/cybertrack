"""Compare GUI round-tripped model geometry and effective process settings by name."""
import json,zipfile,hashlib,xml.etree.ElementTree as E
from pathlib import Path
NS={'c':'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
PN='{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}'
def meta(o):return {m.get('key'):m.get('value') for m in o.findall('metadata') if m.get('key')}
def transform(v,s):
 t=list(map(float,s.split())) if s else [1,0,0,0,1,0,0,0,1,0,0,0]
 return tuple(sum(v[j]*t[j*3+i] for j in range(3))+t[9+i] for i in range(3))
def read(path):
 with zipfile.ZipFile(path) as z:
  root=E.fromstring(z.read('3D/3dmodel.model'));settings=E.fromstring(z.read('Metadata/model_settings.config'));conf=json.loads(z.read('Metadata/project_settings.config'));parts={};objects={};plates=[]
  items={i.get('objectid'):i for i in root.findall('c:build/c:item',NS)}
  for o in settings.findall('object'):
   md=meta(o);name=md['name'];objects[name]=md;parent=root.find("c:resources/c:object[@id='%s']"%o.get('id'),NS)
   for p in o.findall('part'):
    component=parent.find("c:components/c:component[@objectid='%s']"%p.get('id'),NS);child=E.fromstring(z.read(component.get(PN+'path').lstrip('/')));mesh=child.find("c:resources/c:object[@id='%s']/c:mesh"%p.get('id'),NS)
    vs=[transform(transform(tuple(float(v.get(k)) for k in ('x','y','z')),component.get('transform')),items[o.get('id')].get('transform')) for v in mesh.find('c:vertices',NS)]
    ts=[tuple(int(v.get(k)) for k in ('v1','v2','v3')) for v in mesh.find('c:triangles',NS)]
    pm=meta(p);pm.pop('matrix',None)
    parts[(name,pm['name'])]=(vs,ts,pm,p.get('subtype'))
  names={o.get('id'):meta(o)['name'] for o in settings.findall('object')}
  for p in settings.findall('plate'):plates.append({'name':meta(p)['plater_name'],'objects':sorted(names[meta(i)['object_id']] for i in p.findall('model_instance'))})
  return parts,objects,conf,plates

def compare(a,b):
 pa,oa,ca,la=read(a);pb,ob,cb,lb=read(b);assert pa.keys()==pb.keys();assert la==lb
 maximum=0
 for name,(v,t,m,typ) in pa.items():
  w,u,n,kind=pb[name];assert t==u and len(v)==len(w),(name,'mesh topology');assert typ==kind
  delta=max(abs(x-y) for p,q in zip(v,w) for x,y in zip(p,q));assert delta<.00002,(name,delta);maximum=max(maximum,delta)
  # Studio normalizes string representations of numeric process values.
  def eq(x,y):
   if x==y:return True
   try:return float(x)==float(y)
   except (TypeError,ValueError):return False
  for k in set(m)|set(n):
   if k.startswith('source_'):continue
   assert eq(m.get(k),n.get(k)),(name,k,m.get(k),n.get(k))
 for name,md in oa.items():
  for k in set(md)|set(ob[name]):assert eq(md.get(k),ob[name].get(k)),(name,k,md.get(k),ob[name].get(k))
 diff={k:[ca.get(k),cb.get(k)] for k in set(ca)|set(cb) if ca.get(k)!=cb.get(k)}
 assert set(diff)<= {'print_settings_id'},diff
 return {'mesh_parts':len(pa),'maximum_world_coordinate_difference_mm':maximum,'plates':len(la),'all_geometry_placements_and_processes_preserved':True,'display_preset_name_change':diff}
if __name__=='__main__':
 import sys
 print(json.dumps(compare(Path(sys.argv[1]),Path(sys.argv[2])),indent=2))
