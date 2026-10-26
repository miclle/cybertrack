"""Check the consolidated print project and render its four first layers."""
import hashlib,json,sys,zipfile,xml.etree.ElementTree as E
from pathlib import Path
from PIL import Image,ImageDraw
from check_head_set_delivery import meshes
from check_head_print_paths import layers
from compose_ready_prints import SOURCES,OUT,NS,tag,PROCESS_KEYS

project=OUT/'CyberTrack-Ready-4plates.3mf'
expected={}
for _,source in SOURCES:expected.update(meshes(source))
actual=meshes(project)
assert len(actual)==len(expected)==18 and actual==expected
with zipfile.ZipFile(project) as z:
 settings=E.fromstring(z.read('Metadata/model_settings.config'));config=json.loads(z.read('Metadata/project_settings.config'))
 assert len(settings.findall('plate'))==4 and len(settings.findall('object'))==18
 assert len(settings.findall("object/part[@subtype='modifier_part']"))==4
 assert all(int(v)==0 for s in settings.findall('.//mesh_stat') for k,v in s.attrib.items() if k!='face_count')
 byname={o.find("metadata[@key='name']").get('value'):o for o in settings.findall('object')}
 for _,source in SOURCES:
  with zipfile.ZipFile(source) as src:
   sc=json.loads(src.read('Metadata/project_settings.config'));ss=E.fromstring(src.read('Metadata/model_settings.config'))
   for obj in ss.findall('object'):
    name=obj.find("metadata[@key='name']").get('value')
    before={m.get('key'):m.get('value') for m in obj.findall('metadata')};after={m.get('key'):m.get('value') for m in byname[name].findall('metadata')}
    for key in PROCESS_KEYS:assert before.get(key,sc[key])==after.get(key,config[key]),(name,key)
 assert config['filament_settings_id']==['Bambu PLA Basic @BBL P2S']
 canvas=Image.new('RGB',(1120,1160),'#f6f8fa');draw=ImageDraw.Draw(canvas);rows=[]
 results=json.loads((OUT/'result.json').read_text())['sliced_plates'];results.sort(key=lambda p:p['id'])
 for i,result in enumerate(results,1):
  assert result['warning_message']=='' and result['times']['conflict_check_time']>=0
  temp=Path(f'/tmp/cybertrack-ready-plate-{i}.3mf')
  with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as t:t.writestr('Metadata/plate_1.gcode',z.read(f'Metadata/plate_{i}.gcode'))
  paths=layers(temp,include_support=True);first=paths[min(paths)]
  bounds=[min(min(a[k],b[k])-w/2 for a,b,w,_ in first) for k in (0,1)]+[max(max(a[k],b[k])+w/2 for a,b,w,_ in first) for k in (0,1)]
  assert all(v>=0 for v in bounds[:2]) and all(v<=256 for v in bounds[2:]),(i,bounds)
  ox=20+((i-1)%2)*560;oy=40+((i-1)//2)*580
  draw.rectangle((ox,oy,ox+512,oy+512),outline='#63758b',width=2)
  xy=lambda p:(ox+p[0]*2,oy+512-p[1]*2)
  for a,b,w,f in first:draw.line((xy(a),xy(b)),fill='#e69b35' if f.startswith('Support') else '#97a2ad' if f=='Brim' else '#226eaf',width=max(1,round(w*2)))
  draw.text((ox,oy-24),SOURCES[i-1][0],fill='#152537')
  rows.append(dict(plate=i,objects=len(result['objects']),seconds=result['total_predication'],grams=sum(f['total_used_g'] for f in result['filaments']),first_layer_bounds_xy_mm=bounds,warning=result['warning_message']))
  (OUT/f'plate-{i}-preview.png').write_bytes(z.read(f'Metadata/plate_{i}.png'))
 canvas.save(OUT/'four-plates-first-layers.png')
report=dict(project_sha256=hashlib.sha256(project.read_bytes()).hexdigest(),normal_meshes_exact=18,modifier_regions=4,process_settings_match_sources=True,plates=rows,total_seconds=sum(p['seconds'] for p in rows),total_grams=sum(p['grams'] for p in rows),limits='Geometry/settings and sampled paths only; physical fit and strength still require printing.')
(OUT/'delivery-check.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
