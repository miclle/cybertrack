"""Compare orientations and pack the four remaining parts without changing old plates."""
import json,zipfile,concurrent.futures,subprocess,hashlib
from pathlib import Path
import xml.etree.ElementTree as E
from prepare_accessory_print import load_mesh
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'hardware/model/remaining-print'
REF=ROOT/'hardware/model/print-ready/CyberTrack-Ready-4plates.3mf'
SLICER='/Applications/BambuStudio.app/Contents/MacOS/BambuStudio'
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
FAST=dict(layer_height='0.28',wall_loops='3',line_width='0.5',outer_wall_line_width='0.5',inner_wall_line_width='0.5',sparse_infill_line_width='0.6',internal_solid_infill_line_width='0.6',top_surface_line_width='0.5',sparse_infill_density='10%',sparse_infill_pattern='cubic',top_shell_layers='4',top_shell_thickness='1.0',bottom_shell_layers='4',enable_support='1',support_type='normal(auto)',support_style='snug',support_base_pattern_spacing='4',support_line_width='0.5',support_top_z_distance='0.2',support_on_build_plate_only='0',independent_support_layer_height='1',brim_type='outer_only',brim_width='3',wall_generator='classic')

def make(path,parts,settings):
 model=E.Element('model',unit='millimeter',xmlns=NS);res=E.SubElement(model,'resources');build=E.SubElement(model,'build');rows=[]
 for number,(stem,x,y) in enumerate(parts,1):
  verts,tris,size=load_mesh(OUT/(stem+'.stl'));obj=E.SubElement(res,'object',id=str(number),type='model',name=stem)
  mesh=E.SubElement(obj,'mesh');vs=E.SubElement(mesh,'vertices');ts=E.SubElement(mesh,'triangles')
  for v in verts:E.SubElement(vs,'vertex',dict(zip(('x','y','z'),map(str,v))))
  for t in tris:E.SubElement(ts,'triangle',dict(zip(('v1','v2','v3'),map(str,t))))
  E.SubElement(build,'item',objectid=str(number),transform=f'1 0 0 0 1 0 0 0 1 {x} {y} 0')
  rows.append(dict(stem=stem,position=[x,y],size=size,bounds=[x-size[0]/2,y-size[1]/2,x+size[0]/2,y+size[1]/2]))
 with zipfile.ZipFile(REF) as z:config=json.loads(z.read('Metadata/project_settings.config'))
 config.update(FAST);config.update(settings);config['print_settings_id']='Remaining parts '+path.parent.name
 with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
  z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
  z.writestr('3D/3dmodel.model',E.tostring(model,encoding='utf-8',xml_declaration=True));z.writestr('Metadata/project_settings.config',json.dumps(config))
 process=json.loads((ROOT/'hardware/model/print-parts/PP04-slicing/process.json').read_text())
 process.update({k:v for k,v in config.items() if k in process or k in FAST});process.update(type='process',name=config['print_settings_id'],**{'from':'user','instantiation':'true'})
 (path.parent/'process.json').write_text(json.dumps(process))
 from compare_head_print_speed import filament_profile
 profile=filament_profile('Bambu PLA Basic @BBL P2S');(path.parent/'filament.json').write_text(json.dumps(profile))
 (path.parent/'layout.json').write_text(json.dumps(rows,indent=2)+'\n')
 return rows

def run(args):
 name,parts,settings=args;dest=OUT/'slicing'/name;dest.mkdir(parents=True,exist_ok=True)
 layout=make(dest/'input.3mf',parts,settings)
 with (dest/'run.log').open('w') as log:p=subprocess.run([SLICER,'--load-settings',str(ROOT/'hardware/model/print-parts/PP04-slicing/machine.json')+';'+str(dest/'process.json'),'--load-filaments',str(dest/'filament.json'),'--orient','0','--arrange','0','--slice','0','--outputdir',str(dest),str(dest/'input.3mf')],stdout=log,stderr=subprocess.STDOUT,timeout=400)
 if p.returncode:row=dict(name=name,failed=True,code=p.returncode,log=str(dest/'run.log'))
 else:
  result=json.loads((dest/'result.json').read_text());s=result['sliced_plates'][0]
  row=dict(name=name,seconds=s['total_predication'],grams=sum(f['total_used_g'] for f in s['filaments']),warning=s['warning_message'],layout=layout,features=s['feature_type_times'],input_project=str(dest/'input.3mf'),gcode_file=str(dest/'plate_1.gcode'))
 print(json.dumps(row),flush=True);return row

def main():
 candidates=[('cradles-024',[('PP01-base',85,128),('PP02-base',170,128)],{'layer_height':'0.24'}),('cradles-028',[('PP01-base',85,128),('PP02-base',170,128)],{})]
 for name in ['PP03-base','PP03-back','LC04-base','LC04-flipped']:candidates.append((name,[(name,128,128)],{}))
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(run,candidates))
 (OUT/'slicing/comparison.json').write_text(json.dumps(rows,indent=2)+'\n')
if __name__=='__main__':main()
