"""Place selected Crown and Tray projects on one plate, preserving tray-specific wall settings."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import uuid
import zipfile
import xml.etree.ElementTree as E

BASE=Path(__file__).resolve().parents[1]/'hardware/model/print-parts/PP07-slicing'
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
PNS='http://schemas.microsoft.com/3dmanufacturing/production/2015/06'
E.register_namespace('',NS);E.register_namespace('p',PNS)
tag=lambda s:'{'+NS+'}'+s


def compose(crown_name,tray_name):
    target=BASE/'head-set-speed/combined';target.mkdir(exist_ok=True)
    crown_path=BASE/'head-set-speed'/crown_name/(crown_name+'.3mf')
    tray_path=BASE/'head-set-speed'/tray_name/(tray_name+'.3mf')
    with zipfile.ZipFile(crown_path) as cz,zipfile.ZipFile(tray_path) as tz:
        files={n:cz.read(n) for n in cz.namelist() if n.startswith('3D/') or n in ('[Content_Types].xml','_rels/.rels')}
        main=E.fromstring(files['3D/3dmodel.model']);resources=main.find(tag('resources'));build=main.find(tag('build'))
        item=build.find(tag('item'));transform=list(map(float,item.get('transform').split()));transform[9]=128;transform[10]=78
        item.set('transform',' '.join(map(str,transform)))
        tmain=E.fromstring(tz.read('3D/3dmodel.model'));tobj=copy.deepcopy(tmain.find(tag('resources')).find(tag('object')));tobj.set('id','100');tobj.set('{'+PNS+'}UUID',str(uuid.uuid4()))
        for i,component in enumerate(tobj.find(tag('components'))):
            old_path=component.get('{'+PNS+'}path').lstrip('/');new_path='3D/Objects/tray_'+str(i)+'.model'
            mesh_model=E.fromstring(tz.read(old_path))
            mesh_model.find(tag('resources')).find(tag('object')).set('id','101')
            files[new_path]=E.tostring(mesh_model,encoding='utf-8',xml_declaration=True)
            component.set('objectid','101');component.set('{'+PNS+'}path','/'+new_path);component.set('{'+PNS+'}UUID',str(uuid.uuid4()))
        resources.append(tobj)
        titem=copy.deepcopy(tmain.find(tag('build')).find(tag('item')));titem.set('objectid','100');titem.set('{'+PNS+'}UUID',str(uuid.uuid4()))
        tr=list(map(float,titem.get('transform').split()));tr[9]=128;tr[10]=199;titem.set('transform',' '.join(map(str,tr)));build.append(titem)
        cm=E.fromstring(cz.read('Metadata/model_settings.config'));tm=E.fromstring(tz.read('Metadata/model_settings.config')).find('object');tm.set('id','100');tm.find('part').set('id','101')
        cc=json.loads(cz.read('Metadata/project_settings.config'));tc=json.loads(tz.read('Metadata/project_settings.config'))
        keys=['wall_loops','wall_generator','line_width','outer_wall_line_width','inner_wall_line_width',
              'top_shell_layers','bottom_shell_layers','top_shell_thickness','bottom_shell_thickness',
              'sparse_infill_density','sparse_infill_pattern','top_surface_line_width',
              'sparse_infill_line_width','internal_solid_infill_line_width']
        overrides={k:tc[k] for k in keys if cc.get(k)!=tc[k]}
        for k,v in overrides.items():
            assert isinstance(v,str),(k,v)
            E.SubElement(tm,'metadata',key=k,value=v)
        cm.append(tm)
        for node in list(cm):
            if node.tag in ('plate','assemble'):cm.remove(node)
        plate=E.SubElement(cm,'plate')
        for k,v in {'plater_id':'1','plater_name':'Crown and Tray','locked':'false','filament_map_mode':'Auto For Flush','filament_maps':'1','filament_volume_maps':'0'}.items():
            E.SubElement(plate,'metadata',key=k,value=v)
        for identifier,object_id in enumerate((item.get('objectid'),'100'),1):
            instance=E.SubElement(plate,'model_instance')
            for k,v in {'object_id':object_id,'instance_id':'0','identify_id':str(identifier)}.items():
                E.SubElement(instance,'metadata',key=k,value=v)
        files['Metadata/model_settings.config']=E.tostring(cm,encoding='utf-8',xml_declaration=True)
        files['3D/3dmodel.model']=E.tostring(main,encoding='utf-8',xml_declaration=True)
        # Core production extension files need OPC relationship entries.
        # Bambu's OPC reader expects unprefixed relationship tags.
        relationship = '<Relationship Target="/3D/Objects/tray_0.model" Id="rel-tray" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
        files['3D/_rels/3dmodel.model.rels'] = files['3D/_rels/3dmodel.model.rels'].replace(
            b'</Relationships>', relationship.encode() + b'</Relationships>')
        cc['print_settings_id']='Crown and Tray PLA Basic fast'
        files['Metadata/project_settings.config']=json.dumps(cc).encode()
        project=target/'input.3mf'
        with zipfile.ZipFile(project,'w',zipfile.ZIP_DEFLATED) as out:
            for n,data in files.items():out.writestr(n,data)
    with (target/'run.log').open('w') as log:
        p=subprocess.run(['/Applications/BambuStudio.app/Contents/MacOS/BambuStudio','--orient','0','--arrange','0','--slice','0',
            '--export-3mf','Head-Crown-Tray-FAST.3mf','--outputdir',str(target),str(project)],stdout=log,stderr=subprocess.STDOUT,timeout=300)
    assert p.returncode==0,(p.returncode,(target/'run.log').read_text())
    result=json.loads((target/'result.json').read_text());assert result['return_code']==0 and len(result['sliced_plates'])==1
    plate=result['sliced_plates'][0];assert not plate['warning_message'],plate['warning_message']
    report=dict(crown_candidate=crown_name,tray_candidate=tray_name,tray_overrides=overrides,
        positions_xy={'Crown':[128,78],'Tray':[128,199]},seconds=plate['total_predication'],
        grams=sum(f['total_used_g'] for f in plate['filaments']),warning=plate['warning_message'])
    (target/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('crown');parser.add_argument('tray');args=parser.parse_args()
    compose(args.crown,args.tray)
