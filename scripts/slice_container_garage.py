"""Prepare and slice the eleven-part garage on ten P2S-profile build plates.

The user calls the printer P2SC and supplies 256 cubed. The installed vendor
profile is P2S 0.4; slicing is an estimate, not machine or strength acceptance.
"""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
import xml.etree.ElementTree as E

from prepare_accessory_print import load_mesh
from compare_head_print_speed import filament_profile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'hardware/model/container-garage/printed'
REF=ROOT/'hardware/model/lean-print/CyberTrack-Lean-6plates.3mf'
SLICER='/Applications/BambuStudio.app/Contents/MacOS/BambuStudio'
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'


def make(dest,parts,kind,wall_loops=None):
    dest.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(REF) as z:config=json.loads(z.read('Metadata/project_settings.config'))
    loops=wall_loops or ('2' if kind=='roof' else '3')
    settings=dict(layer_height='0.28',wall_loops=loops,line_width='0.6',outer_wall_line_width='0.6',
        inner_wall_line_width='0.6',sparse_infill_line_width='0.6',internal_solid_infill_line_width='0.6',
        top_surface_line_width='0.6',sparse_infill_density='12%',sparse_infill_pattern='gyroid',
        top_shell_layers='7' if kind=='body' else '4',bottom_shell_layers='4',
        top_shell_thickness='1.96' if kind=='body' else '1.12',
        enable_support='1',support_type='normal(auto)',support_style='snug',
        support_on_build_plate_only='0',support_base_pattern_spacing='4',support_top_z_distance='0.2',
        support_critical_regions_only='1',independent_support_layer_height='1',
        brim_type='outer_only',brim_width='2',wall_generator='arachne',enable_prime_tower='0',
        ironing_type='no ironing')
    config.update(settings);config['print_settings_id']='Garage '+dest.name
    profile=filament_profile('Bambu PLA Basic @BBL P2S')
    metadata={'name','type','inherits','include','from','setting_id','instantiation','compatible_printers','compatible_printers_condition','description'}
    config.update({k:v for k,v in profile.items() if k not in metadata and k in config})
    config['filament_settings_id']=['Bambu PLA Basic @BBL P2S'];config['filament_ids']=[profile['filament_id']]
    model=E.Element('model',unit='millimeter',xmlns=NS);resources=E.SubElement(model,'resources');build=E.SubElement(model,'build')
    layout=[]
    for index,(name,x,y) in enumerate(parts,1):
        verts,tris,size=load_mesh(OUT/'parts'/(name+'.stl'))
        bounds=[x-size[0]/2-2,y-size[1]/2-2,x+size[0]/2+2,y+size[1]/2+2]
        assert min(bounds[:2])>=0 and max(bounds[2:])<=256 and size[2]<=256.001,(name,bounds,size)
        for previous in layout:
            a=previous['bounds_with_brim_mm'];b=bounds
            assert min(a[2],b[2])<=max(a[0],b[0]) or min(a[3],b[3])<=max(a[1],b[1])
        obj=E.SubElement(resources,'object',id=str(index),type='model',name=name)
        mesh=E.SubElement(obj,'mesh');vs=E.SubElement(mesh,'vertices');ts=E.SubElement(mesh,'triangles')
        for v in verts:E.SubElement(vs,'vertex',dict(zip(('x','y','z'),map(str,v))))
        for t in tris:E.SubElement(ts,'triangle',dict(zip(('v1','v2','v3'),map(str,t))))
        E.SubElement(build,'item',objectid=str(index),transform=f'1 0 0 0 1 0 0 0 1 {x} {y} 0')
        layout.append({'id':name,'size_xyz_mm':size,'centre_xy_mm':[x,y],'bounds_with_brim_mm':bounds,
                       'stl_sha256':hashlib.sha256((OUT/'parts'/(name+'.stl')).read_bytes()).hexdigest()})
    path=dest/'input.3mf'
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr('3D/3dmodel.model',E.tostring(model,encoding='utf-8',xml_declaration=True))
        z.writestr('Metadata/project_settings.config',json.dumps(config))
    (dest/'layout.json').write_text(json.dumps(layout,indent=2)+'\n')
    process=json.loads((ROOT/'hardware/model/print-parts/PP04-slicing/process.json').read_text())
    process.update({k:v for k,v in config.items() if k in process})
    process.update(settings)
    process.update(type='process',name=config['print_settings_id'],**{'from':'user','instantiation':'true'})
    (dest/'process.json').write_text(json.dumps(process,indent=2)+'\n')
    (dest/'filament.json').write_text(json.dumps(profile,indent=2)+'\n')
    return path,layout,settings


def run(job):
    name,parts,kind,loops=job;dest=OUT/'slicing'/name
    path,layout,settings=make(dest,parts,kind,loops)
    with (dest/'run.log').open('w') as log:
        proc=subprocess.run([SLICER,'--load-settings',str(ROOT/'hardware/model/print-parts/PP04-slicing/machine.json')+';'+str(dest/'process.json'),
            '--load-filaments',str(dest/'filament.json'),'--orient','0','--arrange','0','--slice','0',
            '--export-3mf',name+'.3mf','--outputdir',str(dest),str(path)],stdout=log,stderr=subprocess.STDOUT,timeout=600)
    if proc.returncode:
        row={'plate':name,'failed':True,'exit_code':proc.returncode,'log':str((dest/'run.log').relative_to(OUT))}
    else:
        result=json.loads((dest/'result.json').read_text());plate=result['sliced_plates'][0]
        row={'plate':name,'failed':False,'seconds':plate['total_predication'],
             'grams':sum(f['total_used_g'] for f in plate['filaments']),
             'warnings':plate['warning_message'],'feature_times':plate['feature_type_times'],
             'layout':layout,'settings':settings,'project':str((dest/(name+'.3mf')).relative_to(OUT))}
        # The sliced 3MF retains the exact G-code; remove only its verified duplicate.
        raw=dest/'plate_1.gcode'
        with zipfile.ZipFile(dest/(name+'.3mf')) as archive:
            embedded=archive.read('Metadata/plate_1.gcode')
        if raw.exists():
            assert hashlib.sha256(raw.read_bytes()).digest()==hashlib.sha256(embedded).digest()
            raw.unlink()
    print(json.dumps(row),flush=True)
    (dest/'summary.json').write_text(json.dumps(row,indent=2)+'\n')
    return row


def main():
    rows=json.loads((OUT/'parts.json').read_text());jobs=[]
    for row in rows:
        if row['id']=='L01':continue
        parts=[(row['id'],128,128)]
        if row['id']=='B01':parts.append(('L01',229,128))
        jobs.append((row['id'],parts,row['kind'],None))
    jobs.append(('B02-two-walls',[('B02',128,128)],'body','2'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(run,jobs))
    production=[r for r in results if r['plate']!='B02-two-walls']
    report={'user_printer':'P2SC; 256 x 256 x 256 mm supplied by user',
            'profile':'Bambu Lab P2S 0.4 nozzle; Bambu PLA Basic',
            'plates':production,'comparison':[r for r in results if r['plate']=='B02-two-walls'],
            'all_sliced':all(not r['failed'] for r in production),
            'total_seconds':sum(r.get('seconds',0) for r in production),
            'total_grams':sum(r.get('grams',0) for r in production),
            'physical_strength_verified':False,'print_time_measured':False}
    (OUT/'slicing-summary.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
