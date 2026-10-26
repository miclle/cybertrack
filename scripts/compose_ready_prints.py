"""Consolidate four validated print layouts into one editable, sliced Bambu project."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import uuid
import xml.etree.ElementTree as E
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'hardware/model/print-ready'
SOURCES=[
 ('01 Chassis',ROOT/'hardware/model/print-parts/PP04-slicing/PP04-P2S-PLA-FAST.3mf'),
 ('02 Accessories 14 parts',ROOT/'hardware/model/l298n-compact/slicing/Accessories-14parts-P2S-PLA-FAST.3mf'),
 ('03 Head shell',ROOT/'hardware/model/print-parts/PP07-slicing/PP07-P2S-PLA-Basic-wide-fast.3mf'),
 ('04 Crown and tray',ROOT/'hardware/model/print-parts/PP07-slicing/Head-Crown-Tray-PLA-Basic-FAST.3mf')]
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02';PNS='http://schemas.microsoft.com/3dmanufacturing/production/2015/06'
E.register_namespace('',NS);E.register_namespace('p',PNS)
tag=lambda t:'{'+NS+'}'+t
# Process differences observed in the input projects; material is unified to confirmed PLA Basic.
PROCESS_KEYS=['layer_height','bottom_shell_layers','brim_width','inner_wall_line_width','line_width',
 'outer_wall_line_width','sparse_infill_density','support_base_pattern_spacing','support_line_width',
 'support_style','support_top_z_distance','support_type','top_shell_layers','top_shell_thickness',
 'top_surface_line_width','tree_support_wall_count','wall_loops','wall_generator']


def main():
 OUT.mkdir(exist_ok=True)
 with zipfile.ZipFile(SOURCES[2][1]) as z:
  config=json.loads(z.read('Metadata/project_settings.config'))
  main=E.fromstring(z.read('3D/3dmodel.model'))
  files={n:z.read(n) for n in ['[Content_Types].xml','_rels/.rels']}
 for node in list(main):
  if node.tag in (tag('resources'),tag('build')):main.remove(node)
 resources=E.SubElement(main,tag('resources'));build=E.SubElement(main,tag('build'),{'{'+PNS+'}UUID':str(uuid.uuid4())})
 settings=E.Element('config');relations=[];next_id=1;manifest=[]
 for index,(name,path) in enumerate(SOURCES):
  dx=(index%2)*307.2;dy=-(index//2)*307.2
  with zipfile.ZipFile(path) as z:
   srcmain=E.fromstring(z.read('3D/3dmodel.model'));srcsettings=E.fromstring(z.read('Metadata/model_settings.config'))
   sc=json.loads(z.read('Metadata/project_settings.config'))
   idmap={};pathmap={};children={}
   # Assign global IDs across all external meshes and parent component objects.
   for oldpath in [n for n in z.namelist() if n.startswith('3D/Objects/') and n.endswith('.model')]:
    child=E.fromstring(z.read(oldpath));children[oldpath]=child
    newpath=f'3D/Objects/plate_{index+1}_{Path(oldpath).name}';pathmap[oldpath]=newpath
    for obj in child.find(tag('resources')).findall(tag('object')):
     idmap[obj.get('id')]=str(next_id);next_id+=1
   for obj in srcmain.find(tag('resources')).findall(tag('object')):
    idmap[obj.get('id')]=str(next_id);next_id+=1
   for oldpath,child in children.items():
    for obj in child.find(tag('resources')).findall(tag('object')):obj.set('id',idmap[obj.get('id')])
    files[pathmap[oldpath]]=E.tostring(child,encoding='utf-8',xml_declaration=True);relations.append('/'+pathmap[oldpath])
   for obj in srcmain.find(tag('resources')).findall(tag('object')):
    obj.set('id',idmap[obj.get('id')]);obj.set('{'+PNS+'}UUID',str(uuid.uuid4()))
    for c in obj.find(tag('components')):
     c.set('objectid',idmap[c.get('objectid')]);c.set('{'+PNS+'}path','/'+pathmap[c.get('{'+PNS+'}path').lstrip('/')]);c.set('{'+PNS+'}UUID',str(uuid.uuid4()))
    resources.append(obj)
   overrides={k:sc[k] for k in PROCESS_KEYS if sc[k]!=config[k]}
   for obj in srcsettings.findall('object'):
    obj.set('id',idmap[obj.get('id')])
    present={m.get('key') for m in obj.findall('metadata')}
    for k,v in overrides.items():
     if k not in present:E.SubElement(obj,'metadata',key=k,value=v)
    for part in obj.findall('part'):
     part.set('id',idmap[part.get('id')]);part.set('uuid',str(uuid.uuid4()))
    settings.append(obj)
   plate=E.SubElement(settings,'plate')
   for k,v in {'plater_id':str(index+1),'plater_name':name,'locked':'false','filament_map_mode':'Auto For Flush','filament_maps':'1','filament_volume_maps':'0'}.items():E.SubElement(plate,'metadata',key=k,value=v)
   objects=[]
   for item in srcmain.find(tag('build')):
    oid=idmap[item.get('objectid')];item.set('objectid',oid);item.set('{'+PNS+'}UUID',str(uuid.uuid4()))
    tr=list(map(float,item.get('transform').split()));tr[9]+=dx;tr[10]+=dy;item.set('transform',' '.join(map(str,tr)));build.append(item)
    instance=E.SubElement(plate,'model_instance')
    for k,v in {'object_id':oid,'instance_id':'0','identify_id':oid}.items():E.SubElement(instance,'metadata',key=k,value=v)
    objects.append(oid)
   manifest.append(dict(plate=index+1,name=name,source=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),origin=[dx,dy],objects=objects,process_overrides=overrides))
 files['3D/3dmodel.model']=E.tostring(main,encoding='utf-8',xml_declaration=True)
 files['3D/_rels/3dmodel.model.rels']=('''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'''+''.join(f'<Relationship Target="{p}" Id="rel-{i}" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>' for i,p in enumerate(relations))+ '</Relationships>').encode()
 config['print_settings_id']='CyberTrack ready prints - per object settings';config['wipe_tower_x']=['15']*4;config['wipe_tower_y']=['220']*4
 files['Metadata/model_settings.config']=E.tostring(settings,encoding='utf-8',xml_declaration=True)
 files['Metadata/project_settings.config']=json.dumps(config).encode()
 project=OUT/'input.3mf'
 with zipfile.ZipFile(project,'w',zipfile.ZIP_DEFLATED) as z:
  for n,data in files.items():z.writestr(n,data)
 (OUT/'manifest.json').write_text(json.dumps(dict(plates=manifest,material='Bambu PLA Basic @BBL P2S',volumetric_limit=21),indent=2)+'\n')
 with (OUT/'run.log').open('w') as log:
  p=subprocess.run(['/Applications/BambuStudio.app/Contents/MacOS/BambuStudio','--orient','0','--arrange','0','--slice','0','--export-3mf','CyberTrack-Ready-4plates.3mf','--outputdir',str(OUT),str(project)],stdout=log,stderr=subprocess.STDOUT,timeout=600)
 assert p.returncode==0,(p.returncode,(OUT/'run.log').read_text()[-5000:])
 result=json.loads((OUT/'result.json').read_text());assert result['return_code']==0 and len(result['sliced_plates'])==4
 for plate in result['sliced_plates']:
  assert not plate['warning_message'],plate['warning_message']
  print(json.dumps(dict(plate=plate['id'],seconds=plate['total_predication'],grams=sum(f['total_used_g'] for f in plate['filaments']),objects=len(plate['objects']))),flush=True)

if __name__=='__main__':main()
