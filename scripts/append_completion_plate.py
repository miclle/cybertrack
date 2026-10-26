"""Append the completion plate, preserving all five existing cached slices."""
import argparse,copy,hashlib,json,math,re,uuid,zipfile
from pathlib import Path
import xml.etree.ElementTree as E
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'hardware/model/print-ready';BASE=ROOT/'hardware/model/completion-print'
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02';PN='http://schemas.microsoft.com/3dmanufacturing/production/2015/06';RN='http://schemas.openxmlformats.org/package/2006/relationships'
E.register_namespace('',NS);E.register_namespace('p',PN);tag=lambda n:'{'+NS+'}'+n
sha=lambda b:hashlib.sha256(b).hexdigest()
def data(node):return {m.get('key'):m.get('value') for m in node.findall('metadata') if m.get('key')}
def metadata(node,values):
 for k,v in values.items():E.SubElement(node,'metadata',key=k,value=str(v))
def xml(root):return E.tostring(root,encoding='utf-8',xml_declaration=True)
def relation_file(items):return ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="'+RN+'">'+''.join('<Relationship '+ ' '.join(k+'="'+v+'"' for k,v in row.items())+'/>' for row in items)+'</Relationships>').encode()
def main(base,candidate,target):
 with zipfile.ZipFile(base) as z:files={n:z.read(n) for n in z.namelist()}
 before={n:sha(v) for n,v in files.items() if re.fullmatch(r'Metadata/plate_\d+.gcode',n)}
 root=E.fromstring(files['3D/3dmodel.model']);resources=root.find(tag('resources'));build=root.find(tag('build'));settings=E.fromstring(files['Metadata/model_settings.config']);plates=settings.findall('plate');old_count=len(plates);new_count=old_count+1
 assert old_count==5,'Expected the current five-plate project'
 old_cols=math.ceil(math.sqrt(old_count));cols=math.ceil(math.sqrt(new_count));origin=lambda n,c:((n%c)*307.2,-(n//c)*307.2)
 shifts={}
 for i,plate in enumerate(plates):
  a,b=origin(i,old_cols),origin(i,cols);delta=(b[0]-a[0],b[1]-a[1])
  for instance in plate.findall('model_instance'):shifts[data(instance)['object_id']]=delta
 for item in build:
  tr=list(map(float,item.get('transform').split()));delta=shifts[item.get('objectid')];tr[9]+=delta[0];tr[10]+=delta[1];item.set('transform',' '.join(map(str,tr)))
 ids=[]
 for name,value in files.items():
  if name.endswith('.model'):
   ids += [int(o.get('id')) for o in E.fromstring(value).findall('.//'+tag('object'))]
 next_id=max(ids)+1
 with zipfile.ZipFile(candidate/'input.3mf') as z:source=E.fromstring(z.read('3D/3dmodel.model'))
 config=json.loads(files['Metadata/project_settings.config']);process=json.loads((candidate/'process.json').read_text())
 overrides={k:v for k,v in process.items() if k in config and v!=config[k] and k not in ('name','from','print_settings_id')};assert all(isinstance(v,str) for v in overrides.values())
 plate=E.SubElement(settings,'plate');metadata(plate,{'plater_id':new_count,'plater_name':'06 Completion parts','locked':'false','filament_map_mode':'Auto For Flush','filament_maps':'1','filament_volume_maps':'0','gcode_file':f'Metadata/plate_{new_count}.gcode','thumbnail_file':f'Metadata/plate_{new_count}.png'})
 relationships=[r.attrib for r in E.fromstring(files['3D/_rels/3dmodel.model.rels'])];dx,dy=origin(old_count,cols);new_rows=[]
 for index,source_object in enumerate(source.find(tag('resources')).findall(tag('object'))):
  child_id,parent_id=str(next_id),str(next_id+1);next_id+=2
  name=source_object.get('name');mesh=copy.deepcopy(source_object.find(tag('mesh')));face_count=len(mesh.find(tag('triangles')))
  child=E.Element(tag('model'),unit='millimeter');child_res=E.SubElement(child,tag('resources'));obj=E.SubElement(child_res,tag('object'),id=child_id,type='model');obj.append(mesh)
  child_path=f'3D/Objects/completion_{index+1}.model';files[child_path]=xml(child)
  relationships.append({'Target':'/'+child_path,'Id':'completion-'+str(index+1),'Type':'http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel'})
  obj=E.SubElement(resources,tag('object'),id=parent_id,type='model');components=E.SubElement(obj,tag('components'))
  E.SubElement(components,tag('component'),{'objectid':child_id,'{'+PN+'}path':'/'+child_path,'{'+PN+'}UUID':str(uuid.uuid4()),'transform':'1 0 0 0 1 0 0 0 1 0 0 0'})
  srcitem=list(source.find(tag('build')))[index];tr=list(map(float,srcitem.get('transform').split()));tr[9]+=dx;tr[10]+=dy
  E.SubElement(build,tag('item'),objectid=parent_id,transform=' '.join(map(str,tr)),printable='1')
  object_overrides=dict(overrides)
  settings_obj=E.SubElement(settings,'object',id=parent_id);metadata(settings_obj,{'name':name,'extruder':'1',**object_overrides});E.SubElement(settings_obj,'metadata',face_count=str(face_count))
  part=E.SubElement(settings_obj,'part',id=child_id,subtype='normal_part',uuid=str(uuid.uuid4()));metadata(part,{'name':name,'matrix':'1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1','source_file':name+'.stl','source_object_id':'0','source_volume_id':'0','source_offset_x':'0','source_offset_y':'0','source_offset_z':'0'})
  E.SubElement(part,'mesh_stat',face_count=str(face_count),edges_fixed='0',degenerate_facets='0',facets_removed='0',facets_reversed='0',backwards_edges='0')
  # Generic 3MF import allocates instance IDs 8,12,16,20 in this Bambu version;
  # these are verified in the actual G-code's object label comments below.
  identify=8+index*4;instance=E.SubElement(plate,'model_instance');metadata(instance,{'object_id':parent_id,'instance_id':'0','identify_id':identify})
  new_rows.append({'name':name,'object_id':parent_id,'identify_id':identify})
 gc=(candidate/'plate_1.gcode').read_bytes();labels=set(map(int,re.findall(rb'unique label id: (\d+)',gc)));assert labels=={r['identify_id'] for r in new_rows},labels
 files[f'Metadata/plate_{new_count}.gcode']=gc;files[f'Metadata/plate_{new_count}.gcode.md5']=hashlib.md5(gc).hexdigest().encode()
 # Reuse the existing format, replacing only the newly appended plate's statistics.
 info=E.fromstring(files['Metadata/slice_info.config']);new_info=copy.deepcopy(info.findall('plate')[0]);stats=json.loads((candidate/'result.json').read_text())['sliced_plates'][0];assert stats['warning_message']==''
 for obj in new_info.findall('object'):new_info.remove(obj)
 values={'index':str(new_count),'prediction':str(int(stats['total_predication'])),'weight':f"{stats['filaments'][0]['total_used_g']:.2f}",'label_object_enabled':'true'}
 for m in new_info.findall('metadata'):
  if m.get('key') in values:m.set('value',values[m.get('key')])
 for row in new_rows:E.SubElement(new_info,'object',identify_id=str(row['identify_id']),name=row['name'],skipped='false')
 filament=new_info.find('filament');length=float(re.search(rb'total filament length \[mm\] : ([\d.]+)',gc)[1]);filament.set('used_m',str(round(length/1000,2)));filament.set('used_g',values['weight'])
 layer_count=int(re.search(rb'total layer number: (\d+)',gc)[1]);new_info.find('layer_filament_lists/layer_filament_list').set('layer_ranges','0 '+str(layer_count-1));info.append(new_info)
 files['Metadata/slice_info.config']=xml(info)
 seq=json.loads(files['Metadata/filament_sequence.json']);seq['plate_'+str(new_count)]=copy.deepcopy(seq['plate_1']);files['Metadata/filament_sequence.json']=json.dumps(seq).encode()
 relations=[r.attrib for r in E.fromstring(files['Metadata/_rels/model_settings.config.rels'])];relations.append({'Target':f'/Metadata/plate_{new_count}.gcode','Id':'completion-gcode','Type':'http://schemas.bambulab.com/package/2021/gcode'});files['Metadata/_rels/model_settings.config.rels']=relation_file(relations)
 for key in ('wipe_tower_x','wipe_tower_y'):
  if key in config:config[key]+=[config[key][-1]]
 files['Metadata/project_settings.config']=json.dumps(config).encode();files['Metadata/model_settings.config']=xml(settings);files['3D/3dmodel.model']=xml(root);files['3D/_rels/3dmodel.model.rels']=relation_file(relationships)
 if (BASE/'plate-6-preview.png').exists():files[f'Metadata/plate_{new_count}.png']=(BASE/'plate-6-preview.png').read_bytes()
 else:
  for m in list(plate.findall('metadata')):
   if m.get('key')=='thumbnail_file':plate.remove(m)
  files['Metadata/model_settings.config']=xml(settings)
 assert all(sha(files[n])==v for n,v in before.items())
 with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
  for n,value in files.items():z.writestr(n,value)
 report={'base':str(base),'base_sha256':sha(base.read_bytes()),'project_sha256':sha(target.read_bytes()),'old_gcodes_unchanged':before,'old_plate_count':old_count,'new_plate_count':new_count,'new_objects':new_rows,'overrides':overrides,'new_seconds':stats['total_predication'],'new_grams':stats['filaments'][0]['total_used_g'],'warning':stats['warning_message'],'limits':'Existing model/settings retained; five plate origins unchanged; both layouts use three columns. UI inspection remains separately recorded.'}
 (OUT/'completion-append-audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--base',type=Path,default=OUT/'CyberTrack-Ready-5plates.3mf');p.add_argument('--candidate',type=Path,default=BASE/'slicing/wide-028');p.add_argument('--output',type=Path,default=OUT/'CyberTrack-Ready-6plates.3mf');args=p.parse_args();main(args.base,args.candidate,args.output)
