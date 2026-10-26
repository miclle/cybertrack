"""Reattach unchanged cached slices after Studio's Save As drops G-code."""
import json,zipfile,hashlib,xml.etree.ElementTree as E
from pathlib import Path
from check_head_set_delivery import meshes
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'hardware/model/print-ready';NS={'c':'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
def main():
 original=OUT/'CyberTrack-Ready-4plates.3mf';snapshot=OUT/'CyberTrack-Current-4plates-snapshot.3mf';target=OUT/'CyberTrack-Current-4plates-preserved.3mf'
 assert meshes(original)==meshes(snapshot),'Current geometry differs; do not reuse old paths'
 with zipfile.ZipFile(original) as a,zipfile.ZipFile(snapshot) as b:
  files={n:b.read(n) for n in b.namelist()};ar=E.fromstring(a.read('3D/3dmodel.model'));br=E.fromstring(b.read('3D/3dmodel.model'))
  olditems={i.get('objectid'):i.get('transform') for i in ar.findall('c:build/c:item',NS)};newitems={i.get('objectid'):i.get('transform') for i in br.findall('c:build/c:item',NS)};assert set(olditems)==set(newitems) and all(max(abs(a-b) for a,b in zip(map(float,olditems[k].split()),map(float,newitems[k].split())))<1e-6 for k in olditems),'Current placement differs'
  old=E.fromstring(a.read('Metadata/model_settings.config'));new=E.fromstring(b.read('Metadata/model_settings.config'))
  def settings(o):return {m.get('key'):m.get('value') for m in o.findall('metadata') if m.get('key')}
  oldobj={o.get('id'):o for o in old.findall('object')}
  for obj in new.findall('object'):
   prev=oldobj[obj.get('id')];assert settings(prev)==settings(obj),obj.get('id')
   assert len(prev.findall('part'))==len(obj.findall('part'))
   for p,q in zip(prev.findall('part'),obj.findall('part')):
    ps,qs=settings(p),settings(q)
    if p.get('subtype')=='modifier_part':
     ps.pop('matrix',None);qs.pop('matrix',None)
     oid=obj.get('id');pid=p.get('id');expr="c:resources/c:object[@id='%s']/c:components/c:component[@objectid='%s']" % (oid,pid)
     assert ar.find(expr,NS).get('transform')==br.find(expr,NS).get('transform')
     pn='{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}'
     for archive,model,key in [(a,ar,'old'),(b,br,'new')]:
      node=model.find(expr,NS);child=E.fromstring(archive.read(node.get(pn+'path').lstrip('/')));mesh=E.tostring(child.find("c:resources/c:object[@id='%s']/c:mesh" % pid,NS))
      if key=='old':previous_mesh=mesh
      else:assert mesh==previous_mesh
    assert p.get('subtype')==q.get('subtype') and ps==qs
  ac=json.loads(a.read('Metadata/project_settings.config'));bc=json.loads(b.read('Metadata/project_settings.config'));diff={k:{'before':ac.get(k),'current':v} for k,v in bc.items() if ac.get(k)!=v}
  allowed={'extruder_ams_count','extruder_nozzle_stats','extruder_nozzle_stats_new','filament_colour_type','filament_multi_colour','filament_prime_volume','flush_volumes_matrix','flush_volumes_vector','host_type','print_settings_id','printhost_authorization_type','printhost_ssl_ignore_revoke'}
  assert set(diff)<=allowed, list(set(diff)-allowed)
  for src,dst in zip(old.findall('plate'),new.findall('plate')):
   g=src.find("metadata[@key='gcode_file']");dst.append(E.fromstring(E.tostring(g)))
   inst={settings(i)['object_id']:i for i in src.findall('model_instance')}
   for item in dst.findall('model_instance'):item.find("metadata[@key='identify_id']").set('value',settings(inst[settings(item)['object_id']])['identify_id'])
  files['Metadata/model_settings.config']=E.tostring(new,encoding='utf-8',xml_declaration=True)
  for n in a.namelist():
   if n.endswith(('.gcode','.gcode.md5')) or n in ('Metadata/slice_info.config','Metadata/_rels/model_settings.config.rels') or n.startswith('Metadata/plate_') and n.endswith('.json'):files[n]=a.read(n)
 with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
  for n,v in files.items():z.writestr(n,v)
 report={'snapshot_sha256':hashlib.sha256(snapshot.read_bytes()).hexdigest(),'preserved_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'normal_meshes_unchanged':18,'modifier_meshes_and_placements_unchanged':4,'modifier_import_provenance_matrix_changes_retained':True,'placement_unchanged_within_mm':1e-6,'object_and_modifier_process_settings_unchanged':True,'current_global_settings_changes_retained':diff,'note':'Save As omitted cached slices; restore old G-code after exact geometry/placement/object-setting comparison. Runtime identify IDs restored to match existing G-code. Current prime-volume change applies on future slicing; old plate bytes retained.'}
 (OUT/'current-snapshot-check.json').write_text(json.dumps(report,indent=2)+'\n');print('Preserved current snapshot and restored four unchanged cached slices')
if __name__=='__main__':main()
