"""Stand PP03 on its native bottom on the existing dedicated plate."""
import xml.etree.ElementTree as E
import zipfile
from prepare_lean_print import tag, PN, meta, xml, archive_write


def orient(path):
    with zipfile.ZipFile(path) as z:
        files = {n: z.read(n) for n in z.namelist()}
    root = E.fromstring(files['3D/3dmodel.model'])
    settings = E.fromstring(files['Metadata/model_settings.config'])
    obj = next(o for o in settings.findall('object') if meta(o)['name'] == 'PP03-base')
    oid = obj.get('id')
    plate = next(p for p in settings.findall('plate')
                 if any(meta(i)['object_id'] == oid for i in p.findall('model_instance')))
    assert len(plate.findall('model_instance')) == 1
    number = int(meta(plate)['plater_id'])
    component = root.find(tag('resources')).find(tag('object')+f"[@id='{oid}']").find(tag('components'))[0]
    assert list(map(float, component.get('transform').split())) == [1,0,0,0,1,0,0,0,1,0,0,0]
    child = E.fromstring(files[component.get('{'+PN+'}path').lstrip('/')])
    mesh = child.find('.//'+tag('mesh'))
    vertices = [[float(v.get(k)) for k in 'xyz'] for v in mesh.find(tag('vertices'))]
    low = [min(v[i] for v in vertices) for i in range(3)]
    high = [max(v[i] for v in vertices) for i in range(3)]
    item = root.find(tag('build')).find(tag('item')+f"[@objectid='{oid}']")
    before = list(map(float, item.get('transform').split()))
    translation = [before[9], before[10], -low[2]]
    transform = ' '.join(map(str, [1,0,0,0,1,0,0,0,1]+translation))
    item.set('transform', transform)
    for instance in settings.findall('assemble/assemble_item'):
        if instance.get('object_id') == oid:
            instance.set('transform', transform)
    for m in list(plate.findall('metadata')):
        if m.get('key') in ('gcode_file','thumbnail_file','thumbnail_no_light_file','top_file','pick_file'):
            files.pop(m.get('value'), None)
            plate.remove(m)
    assert f'Metadata/plate_{number}.gcode' not in files
    files['3D/3dmodel.model'] = xml(root)
    files['Metadata/model_settings.config'] = xml(settings)
    # Seven plates use three columns in the existing project.
    origin = [((number-1)%3)*307.2, -((number-1)//3)*307.2, 0]
    bounds = [[low[i]+translation[i]-origin[i], high[i]+translation[i]-origin[i]] for i in range(3)]
    assert all(a >= -1e-6 and b <= 256+1e-6 for a,b in bounds)
    assert abs(bounds[2][0]) < 1e-6
    archive_write(path, files)
    return {'plate':number, 'before_transform':before,
            'upright_transform':list(map(float, transform.split())), 'plate_local_bounds_mm':bounds,
            'size_mm':[high[i]-low[i] for i in range(3)], 'geometry_and_process_unchanged':True}
