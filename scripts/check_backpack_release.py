"""Check the current scoped backpack CAD/3MF revision; not slicing acceptance."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as E
import zipfile

ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'hardware/model'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def check():
    geometry=json.loads((MODEL/'backpack-35mm-audit.json').read_text())
    prints=json.loads((MODEL/'backpack-print-update.json').read_text())
    assert geometry['passed'] and geometry['saved_reopened']
    assert geometry['bore_diameter_mm']==35 and not geometry['backpack_collisions']
    for path,digest in geometry['files_sha256'].items():assert sha(ROOT/path)==digest,path
    for key,path in [('source','source/CyberTrack-design.FCStd'),('delivery','CyberTrack.FCStd')]:
        with zipfile.ZipFile(MODEL/path) as z:
            assert 'GuiDocument.xml' in z.namelist(), 'CAD display state is missing'
            gui=E.fromstring(z.read('GuiDocument.xml'))
            assert gui.find(".//ViewProvider[@name='PrintBackpack']/Properties/Property[@name='Visibility']/Bool").get('value')=='true'
            root=E.fromstring(z.read('Document.xml'))
            objects={o.get('name'):o for o in root.findall('./ObjectData/Object')}
            assert not set(geometry['removed'][key]).intersection(objects)
            assert all(n in objects for n in ['WaterModule','WaterPod','PrintBubbleCradle','PrintBackpack'])
    from prepare_lean_print import raw_mesh, tag, PN
    expected_mesh,_=raw_mesh(MODEL/'remaining-print/PP03-base.stl')
    result=[]
    for row in prints['projects']:
        path=ROOT/row['path'];assert sha(path)==row['sha256'],row['path']
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None,row['path']
            settings=E.fromstring(z.read('Metadata/model_settings.config'))
            names=[o.find("metadata[@key='name']").get('value') for o in settings.findall('object')]
            assert names==row['part_names'] and not {'BubblePod','BubbleLidMark'}.intersection(names)
            assert len(names)==len(set(names))==row['print_parts']
            if 'plates' in row:
                objects={o.get('id'):o.find("metadata[@key='name']").get('value') for o in settings.findall('object')}
                plates=[{'name':p.find("metadata[@key='plater_name']").get('value'),
                         'objects':sorted(objects[i.find("metadata[@key='object_id']").get('value')]
                                          for i in p.findall('model_instance'))}
                        for p in settings.findall('plate')]
                assert plates==row['plates']
                assert sorted(n for p in plates for n in p['objects'])==sorted(names)
            for plate in row['requires_reslice_plates']:
                assert f'Metadata/plate_{plate}.gcode' not in z.namelist()
            assert names.count('PP03-base')==1
            obj=next(o for o in settings.findall('object') if o.find("metadata[@key='name']").get('value')=='PP03-base')
            if 'dedicated_backpack_plate' in row:
                plates=settings.findall('plate')
                assert len(plates)==row['plate_count']
                dedicated=next(p for p in plates if p.find("metadata[@key='plater_id']").get('value')==str(row['dedicated_backpack_plate']))
                instances=dedicated.findall('model_instance')
                assert len(instances)==1
                assert instances[0].find("metadata[@key='object_id']").get('value')==obj.get('id')
            root=E.fromstring(z.read('3D/3dmodel.model'))
            if row.get('orientation')=='upright':
                item=root.find(tag('build')).find(tag('item')+"[@objectid='%s']"%obj.get('id'))
                assert list(map(float,item.get('transform').split()))==row['upright_transform']
            parent=root.find(tag('resources')).find("%s[@id='%s']"%(tag('object'),obj.get('id')))
            component=parent.find(tag('components'))[0]
            child=E.fromstring(z.read(component.get('{'+PN+'}path').lstrip('/')))
            mesh=child.find(tag('resources')).find("%s[@id='%s']"%(tag('object'),component.get('objectid'))).find(tag('mesh'))
            actual=list(mesh.find(tag('vertices')));expected=list(expected_mesh.find(tag('vertices')))
            assert len(actual)==len(expected)
            for a,b in zip(actual,expected):
                assert all(abs(float(a.get(k))-float(b.get(k))-offset)<1e-5 for k,offset in zip(('x','y','z'),row['mesh_local_translation_mm']))
            assert [t.attrib for t in mesh.find(tag('triangles'))]==[t.attrib for t in expected_mesh.find(tag('triangles'))]
        result.append({'project':row['path'],'sha256':row['sha256'],'print_parts':len(names),
                       'plate_count':len(settings.findall('plate')),'requires_reslice_plates':row['requires_reslice_plates'],
                       'dedicated_backpack_plate':row.get('dedicated_backpack_plate')})
    for row in prints['retired_exports']:assert not (ROOT/row['path']).exists()
    return {'passed':True,'scope':'backpack CAD and current saved project consistency',
            'projects':result,'slicing_validated':False,'physical_fit_verified':False,
            'limits':'Affected plate G-code is invalidated. Unrelated historical slice evidence is not re-certified.'}

if __name__=='__main__':print(json.dumps(check(),ensure_ascii=False,indent=2))
