"""Move only PP03 to a new dedicated plate, preserving other placements."""
import copy
import json
import math
from pathlib import Path
import xml.etree.ElementTree as E
import zipfile
from prepare_lean_print import tag, xml, meta, archive_write, sha


def isolate(path):
    with zipfile.ZipFile(path) as z:files={n:z.read(n) for n in z.namelist()}
    root=E.fromstring(files['3D/3dmodel.model'])
    settings=E.fromstring(files['Metadata/model_settings.config'])
    obj=next(o for o in settings.findall('object') if meta(o).get('name')=='PP03-base')
    oid=obj.get('id');plates=settings.findall('plate')
    source=next(p for p in plates if any(meta(i)['object_id']==oid for i in p.findall('model_instance')))
    instance=next(i for i in source.findall('model_instance') if meta(i)['object_id']==oid)
    old_plate=int(meta(source)['plater_id']);new_plate=len(plates)+1
    assert math.ceil(math.sqrt(len(plates)))==math.ceil(math.sqrt(new_plate)), 'Grid change requires moving all plate origins'
    new=copy.deepcopy(source)
    for i in list(new.findall('model_instance')):new.remove(i)
    for m in list(new.findall('metadata')):
        key=m.get('key')
        if key in ('gcode_file','thumbnail_file','thumbnail_no_light_file','top_file','pick_file'):new.remove(m)
        elif key=='plater_id':m.set('value',str(new_plate))
        elif key=='plater_name':m.set('value','背包 Ø35 · 独立盘')
    source.remove(instance);new.append(instance);settings.append(new)
    build=root.find(tag('build'));item=build.find("%s[@objectid='%s']"%(tag('item'),oid))
    old_transforms={i.get('objectid'):i.get('transform') for i in build}
    tr=list(map(float,item.get('transform').split()))
    cols=math.ceil(math.sqrt(new_plate));index=new_plate-1
    # Existing PP03 mesh is centred locally; keep its orientation and bed height.
    tr[9]=(index%cols)*307.2+128
    tr[10]=-(index//cols)*307.2+128
    item.set('transform',' '.join(map(str,tr)))
    assert all(i.get('transform')==old_transforms[i.get('objectid')] for i in build if i.get('objectid')!=oid)
    for m in list(source.findall('metadata')):
        if m.get('key') in ('gcode_file','thumbnail_file','thumbnail_no_light_file','top_file','pick_file'):
            files.pop(m.get('value'),None);source.remove(m)
    config=json.loads(files['Metadata/project_settings.config'])
    for key in ('wipe_tower_x','wipe_tower_y'):
        if key in config:
            assert len(config[key])==len(plates)
            config[key].append(config[key][-1])
    sequence='Metadata/filament_sequence.json'
    if sequence in files:
        seq=json.loads(files[sequence])
        if 'plate_1' in seq:seq['plate_'+str(new_plate)]=copy.deepcopy(seq['plate_1'])
        files[sequence]=json.dumps(seq).encode()
    files['Metadata/project_settings.config']=json.dumps(config).encode()
    files['Metadata/model_settings.config']=xml(settings)
    files['3D/3dmodel.model']=xml(root)
    archive_write(path,files)
    with zipfile.ZipFile(path) as z:
        saved=E.fromstring(z.read('Metadata/model_settings.config'))
        last=saved.findall('plate')[-1]
        assert len(last.findall('model_instance'))==1 and meta(last.find('model_instance'))['object_id']==oid
        assert len(saved.findall('object'))==len(settings.findall('object'))
    return {'previous_plate':old_plate,'dedicated_plate':new_plate,'plate_count':new_plate,
            'new_transform':tr,'other_object_transforms_unchanged':True,'sha256':sha(path.read_bytes())}
