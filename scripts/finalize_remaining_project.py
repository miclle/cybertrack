"""Attach checked plate-five paths and verify that all four earlier plates stay intact."""
import json,zipfile,hashlib,math,re,copy
from pathlib import Path
import xml.etree.ElementTree as E
from PIL import Image,ImageDraw
from check_head_print_paths import layers
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'hardware/model/print-ready';BASE=ROOT/'hardware/model/remaining-print'
sha=lambda b:hashlib.sha256(b).hexdigest()
def main():
 path_check=json.loads((BASE/'path-check.json').read_text());assert path_check['candidates']['merged-validation']['passed']
 target=OUT/'CyberTrack-Ready-5plates.3mf';manifest=json.loads((OUT/'remaining-append-audit.json').read_text());base=Path(manifest['base'])
 source=BASE/'slicing/merged-validation';gc=(source/'plate_5.gcode').read_bytes();stats=json.loads((source/'result.json').read_text())['sliced_plates'][0]
 assert sha(gc)==path_check['candidates']['merged-validation']['gcode_sha256'];assert not stats['warning_message'];assert stats['times']['conflict_check_time']>0
 with zipfile.ZipFile(target) as z:files={n:z.read(n) for n in z.namelist()}
 files['Metadata/plate_5.gcode']=gc;files['Metadata/plate_5.gcode.md5']=hashlib.md5(gc).hexdigest().encode()
 info=E.fromstring(files['Metadata/slice_info.config']);plate=info.findall('plate')[4]
 values={'prediction':str(int(stats['total_predication'])),'weight':str(round(stats['filaments'][0]['total_used_g'],2))}
 for m in plate.findall('metadata'):
  if m.get('key') in values:m.set('value',values[m.get('key')])
 filament=plate.find('filament');filament.set('used_g',values['weight']);length=float(re.search(rb'total filament length \[mm\] : ([\d.]+)',gc)[1]);filament.set('used_m',str(round(length/1000,2)))
 files['Metadata/slice_info.config']=E.tostring(info,encoding='utf-8',xml_declaration=True)
 paths=layers(source/'plate_5.gcode',True);allpoints=[p for ss in paths.values() for a,b,w,f in ss for p in (a,b)]
 bounds=[min(p[0] for p in allpoints),min(p[1] for p in allpoints),max(p[0] for p in allpoints),max(p[1] for p in allpoints)]
 assert min(bounds)>=.5 and max(bounds)<=255.5,bounds
 scale=3;im=Image.new('RGB',(850,900),'#f5f7fa');draw=ImageDraw.Draw(im)
 def xy(p):return (40+p[0]*scale,830-p[1]*scale)
 draw.rectangle((40,62,808,830),fill='white',outline='#a4adb8',width=2)
 for n in range(0,257,32):
  draw.line([xy((n,0)),xy((n,256))],fill='#edf0f3');draw.line([xy((0,n)),xy((256,n))],fill='#edf0f3')
 first=min(h for h,s in paths.items() if s)
 for a,b,w,f in paths[first]:
  color='#e9a03b' if f.startswith('Support') else '#3188ce' if f!='Brim' else '#92b8d3';draw.line([xy(a),xy(b)],fill=color,width=max(1,round(w*scale)))
 draw.text((40,20),'Plate 05 | 4 parts | first layer | blue: model, orange: support',fill='#223244')
 draw.text((40,860),f"P2S 0.4 / PLA Basic | {stats['total_predication']/3600:.2f} h | {stats['filaments'][0]['total_used_g']:.2f} g",fill='#223244')
 image_path=BASE/'plate-5-preview.png';im.save(image_path);files['Metadata/plate_5.png']=image_path.read_bytes()
 settings=E.fromstring(files['Metadata/model_settings.config']);plates=settings.findall('plate');assert len(plates)==5
 plate=plates[-1]
 if not any(m.get('key')=='thumbnail_file' for m in plate.findall('metadata')):E.SubElement(plate,'metadata',key='thumbnail_file',value='Metadata/plate_5.png')
 files['Metadata/model_settings.config']=E.tostring(settings,encoding='utf-8',xml_declaration=True)
 with zipfile.ZipFile(base) as z:
  for n in z.namelist():
   if n.startswith('3D/Objects/') or re.fullmatch(r'Metadata/plate_[1-4]\.gcode(?:\.md5)?',n):assert files[n]==z.read(n),n
  old_settings=E.fromstring(z.read('Metadata/model_settings.config'));objects={o.get('id'):o for o in settings.findall('object')}
  for o in old_settings.findall('object'):assert E.tostring(o)==E.tostring(objects[o.get('id')]),o.get('id')
  old_config=json.loads(z.read('Metadata/project_settings.config'));config=json.loads(files['Metadata/project_settings.config'])
  for k,v in old_config.items():assert (config[k][:len(v)]==v if k in ('wipe_tower_x','wipe_tower_y') else config[k]==v),k
 ns={'c':'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'};root=E.fromstring(files['3D/3dmodel.model']);assert len(root.findall('c:build/c:item',ns))==22
 with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
  for n,v in files.items():z.writestr(n,v)
 normal=sum(p.get('subtype')=='normal_part' for o in settings.findall('object') for p in o.findall('part'));assert normal==22
 report={'project':str(target),'project_sha256':sha(target.read_bytes()),'base_sha256':sha(base.read_bytes()),'old_gcodes_unchanged':manifest['old_gcodes_unchanged'],'old_meshes_and_settings_unchanged':True,'normal_meshes':normal,'plates':5,'new_plate_objects':4,'new_plate_seconds':stats['total_predication'],'new_plate_grams':stats['filaments'][0]['total_used_g'],'all_layer_xy_bounds_mm':bounds,'new_plate_warning':stats['warning_message'],'collision_check_executed':True,'sampled_sections_passed':len(path_check['candidates']['merged-validation']['sections']),'new_plate_gcode_sha256':sha(gc),'GUI_loaded':False,'limits':'Saved project and emitted paths checked; GUI opening and round-trip verification are recorded after this script. Physical assembly/strength unverified.'}
 (OUT/'five-plate-delivery-check.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
