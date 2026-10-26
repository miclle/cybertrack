"""Optimize crown/tray using verified head-print baselines, retaining their embedded meshes."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
import xml.etree.ElementTree as E
from compare_head_print_speed import filament_profile

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'hardware/model/print-parts/PP07-slicing'
OUT=BASE/'head-set-speed'
SLICER='/Applications/BambuStudio.app/Contents/MacOS/BambuStudio'
WIDE=dict(layer_height='0.28',wall_loops='2',line_width='0.6',outer_wall_line_width='0.6',
          inner_wall_line_width='0.6',sparse_infill_line_width='0.6',internal_solid_infill_line_width='0.6',
          top_surface_line_width='0.6',support_line_width='0.5',sparse_infill_density='8%',
          sparse_infill_pattern='cubic',top_shell_layers='3',top_shell_thickness='0.84',
          bottom_shell_layers='3',tree_support_wall_count='1')
VARIANTS={
 'crown-wide':('Crown',WIDE),
 'crown-threewalls':('Crown',dict(WIDE,wall_loops='3',outer_wall_line_width='0.5',inner_wall_line_width='0.5')),
 'crown-snug':('Crown',dict(WIDE,support_type='normal(auto)',support_style='snug',support_base_pattern_spacing='5')),
 'crown-hybrid':('Crown',dict(WIDE,support_style='tree_hybrid',support_base_pattern_spacing='4')),
 'crown-arachne':('Crown',dict(WIDE,wall_generator='arachne')),
 'crown-flipped':('Crown',dict(WIDE,rotate_x=180)),
 'tray-wide':('Tray',dict(WIDE,wall_loops='3',outer_wall_line_width='0.5',inner_wall_line_width='0.5',top_shell_layers='5',bottom_shell_layers='4',top_shell_thickness='1.0')),
 'tray-024':('Tray',dict(WIDE,layer_height='0.24',wall_loops='3',outer_wall_line_width='0.5',inner_wall_line_width='0.5',top_shell_layers='5',bottom_shell_layers='4',top_shell_thickness='1.0')),
}

VARIANTS.update({
 'crown-flipped-snug':('Crown',dict(VARIANTS['crown-snug'][1],rotate_x=180)),
 'crown-snug024':('Crown',dict(VARIANTS['crown-snug'][1],layer_height='0.24',top_shell_layers='4',bottom_shell_layers='4',top_shell_thickness='0.96')),
 'crown-snug-support06':('Crown',dict(VARIANTS['crown-snug'][1],support_line_width='0.6')),
 'crown-snug-arachne':('Crown',dict(VARIANTS['crown-snug'][1],wall_generator='arachne')),
 'tray-balanced':('Tray',dict(VARIANTS['tray-wide'][1],top_shell_layers='4',bottom_shell_layers='3',sparse_infill_density='15%')),
})


VARIANTS.update({
 'crown-snug-seats':('Crown',dict(VARIANTS['crown-snug'][1],reinforce_seats=True)),
 'crown-arachne-seats':('Crown',dict(VARIANTS['crown-snug-arachne'][1],reinforce_seats=True)),
 'crown-flipped-seats':('Crown',dict(VARIANTS['crown-flipped-snug'][1],reinforce_seats=True)),
})


def reinforce_seats(files):
    ns='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
    pns='http://schemas.microsoft.com/3dmanufacturing/production/2015/06'
    E.register_namespace('',ns);E.register_namespace('p',pns)
    tag=lambda t:'{'+ns+'}'+t
    main=E.fromstring(files['3D/3dmodel.model'])
    components=main.find('.//'+tag('components'))
    child=E.fromstring(files['3D/Objects/object_1.model'])
    resources=child.find(tag('resources'))
    config=E.fromstring(files['Metadata/model_settings.config'])
    parent=config.find('object')
    faces=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    for number,(x,y) in enumerate([(x,y) for x in (-64,64) for y in (-52,7)],2):
        # Existing Crown component frame: world X, Y+26, Z-212.
        cy=y+26;z0=3.9;z1=7.2
        points=[(x-5,cy-5,z0),(x+5,cy-5,z0),(x+5,cy+5,z0),(x-5,cy+5,z0),
                (x-5,cy-5,z1),(x+5,cy-5,z1),(x+5,cy+5,z1),(x-5,cy+5,z1)]
        obj=E.SubElement(resources,tag('object'),id=str(number),type='model')
        mesh=E.SubElement(obj,tag('mesh'));vertices=E.SubElement(mesh,tag('vertices'));triangles=E.SubElement(mesh,tag('triangles'))
        for v in points:E.SubElement(vertices,tag('vertex'),dict(zip(('x','y','z'),map(str,v))))
        for f in faces:E.SubElement(triangles,tag('triangle'),dict(zip(('v1','v2','v3'),map(str,f))))
        E.SubElement(components,tag('component'),{'{'+pns+'}path':'/3D/Objects/object_1.model','objectid':str(number),'transform':'1 0 0 0 1 0 0 0 1 0 0 0'})
        part=E.SubElement(parent,'part',id=str(number),subtype='modifier_part')
        for k,v in {'name':f'Crown screw seat {number-1}', 'matrix':'1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1',
                    'sparse_infill_density':'100%', 'sparse_infill_pattern':'rectilinear','wall_loops':'4'}.items():
            E.SubElement(part,'metadata',key=k,value=v)
    files['3D/3dmodel.model']=E.tostring(main,encoding='utf-8',xml_declaration=True)
    files['3D/Objects/object_1.model']=E.tostring(child,encoding='utf-8',xml_declaration=True)
    files['Metadata/model_settings.config']=E.tostring(config,encoding='utf-8',xml_declaration=True)


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def make_input(name,part,overrides,target):
    baseline=BASE/part/(part+'.3mf')
    with zipfile.ZipFile(baseline) as src:
        config=json.loads(src.read('Metadata/project_settings.config'))
        profile=filament_profile('Bambu PLA Basic @BBL P2S')
        metadata={'name','type','inherits','include','from','setting_id','instantiation','compatible_printers','compatible_printers_condition','description'}
        config.update({k:v for k,v in profile.items() if k not in metadata and k in config})
        config['filament_settings_id']=['Bambu PLA Basic @BBL P2S'];config['filament_ids']=[profile['filament_id']]
        config.update({k:v for k,v in overrides.items() if k not in ('rotate_x','reinforce_seats')})
        config['print_settings_id']='Head set '+name
        project=target/'input.3mf'
        files={filename:src.read(filename) for filename in src.namelist()
               if filename.startswith('3D/') or filename in ('[Content_Types].xml','_rels/.rels','Metadata/model_settings.config')}
        if overrides.get('reinforce_seats'):reinforce_seats(files)
        with zipfile.ZipFile(project,'w',zipfile.ZIP_DEFLATED) as dst:
            for filename,data in files.items():dst.writestr(filename,data)
            dst.writestr('Metadata/project_settings.config',json.dumps(config))
    (target/'resolved-filament.json').write_text(json.dumps(profile,indent=2)+'\n')
    return project


def run(name):
    part,overrides=VARIANTS[name];target=OUT/name;target.mkdir(parents=True,exist_ok=True)
    project=make_input(name,part,overrides,target)
    cmd=[SLICER,'--orient','0','--arrange','0','--slice','0','--export-3mf',name+'.3mf','--outputdir',str(target)]
    if 'rotate_x' in overrides:cmd+=['--rotate-x',str(overrides['rotate_x']),'--ensure-on-bed']
    cmd.append(str(project))
    with (target/'run.log').open('w') as f:p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=300)
    if p.returncode:
        row=dict(name=name,part=part,failed=True,code=p.returncode,diagnostic=(target/'run.log').read_text())
    else:
        r=json.loads((target/'result.json').read_text());assert r['return_code']==0 and len(r['sliced_plates'])==1
        plate=r['sliced_plates'][0]
        row=dict(name=name,part=part,seconds=plate['total_predication'],grams=sum(f['total_used_g'] for f in plate['filaments']),
                 warning=plate['warning_message'],overrides=overrides,project=str((target/(name+'.3mf')).relative_to(BASE)),
                 project_sha256=digest(target/(name+'.3mf')),features=plate['feature_type_times'])
    print(json.dumps({k:v for k,v in row.items() if k in ('name','seconds','grams','warning','failed','code')}),flush=True)
    return row


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('variants',nargs='*');args=parser.parse_args()
    assert all(n in VARIANTS for n in args.variants)
    data=json.loads((BASE/'independent-parts.json').read_text())
    for row in data['parts']:
        assert digest(BASE.parent/row['stl'])==row['input_stl_sha256'],row['part']
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(run,args.variants or list(VARIANTS)))
    output=OUT/'comparison.json';old=json.loads(output.read_text()) if output.exists() else {}
    old.update({r['name']:r for r in rows});output.write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n')
