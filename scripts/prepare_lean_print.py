"""Remove five retainers, bring gun seats forward, and order by priority."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import xml.etree.ElementTree as E
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'hardware/model/lean-print'
BASE = ROOT / 'hardware/model/archive/print-baselines/CyberTrack-34parts-6plates.3mf'
TARGET = OUT / 'CyberTrack-Lean-6plates.3mf'
NS = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
PN = 'http://schemas.microsoft.com/3dmanufacturing/production/2015/06'
E.register_namespace('', NS); E.register_namespace('p', PN)
tag = lambda n: '{'+NS+'}'+n
xml = lambda n: E.tostring(n, encoding='utf-8', xml_declaration=True)
meta = lambda n: {m.get('key'): m.get('value') for m in n.findall('metadata')}
sha = lambda b: hashlib.sha256(b).hexdigest()
REMOVED = {'EffectRetainerLMOS', 'EffectRetainerLBuck', 'EffectRetainerRMOS',
           'EffectRetainerRBuck', 'IgnitionMOSRetainer'}
ORDER = [1, 2, 6, 4, 3, 5]
TITLES = ['01 Drive chassis', '02 Drive and control mounts',
          '03 Gun mounts MOS carriers bottles and trim', '04 Controller tray and crown',
          '05 Head shell', '06 LAST Backpack and lid']


def archive_write(path, files):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, value in files.items(): z.writestr(name, value)


def setmeta(node, key, value):
    m = node.find("metadata[@key='%s']" % key)
    if m is None: m = E.SubElement(node, 'metadata', key=key)
    m.set('value', str(value))


def relxml(node):
    # Bambu's relationship parser expects an unprefixed default namespace.
    root = E.Element('Relationships', xmlns='http://schemas.openxmlformats.org/package/2006/relationships')
    for child in node: E.SubElement(root, 'Relationship', child.attrib)
    return xml(root)


def raw_mesh(path):
    data = path.read_bytes(); count = struct.unpack_from('<I', data, 80)[0]
    vertices, faces, ids = [], [], {}
    for i in range(count):
        coords = struct.unpack_from('<12fH', data, 84+50*i)[3:12]; face = []
        for j in (0, 3, 6):
            v = tuple(coords[j:j+3])
            if v not in ids: ids[v] = len(vertices); vertices.append(v)
            face.append(ids[v])
        faces.append(face)
    mesh = E.Element(tag('mesh')); vs = E.SubElement(mesh, tag('vertices')); ts = E.SubElement(mesh, tag('triangles'))
    for v in vertices: E.SubElement(vs, tag('vertex'), dict(zip(('x','y','z'), map(str, v))))
    for t in faces: E.SubElement(ts, tag('triangle'), dict(zip(('v1','v2','v3'), map(str, t))))
    return mesh, count


def prepare():
    with zipfile.ZipFile(BASE) as z: files = {n: z.read(n) for n in z.namelist()}
    root = E.fromstring(files['3D/3dmodel.model']); settings = E.fromstring(files['Metadata/model_settings.config'])
    resources, build = root.find(tag('resources')), root.find(tag('build'))
    plates = settings.findall('plate'); deleted = []
    for obj in list(settings.findall('object')):
        name = meta(obj)['name']; oid = obj.get('id')
        parent = resources.find("%s[@id='%s']" % (tag('object'), oid))
        if name in REMOVED:
            deleted.append(name); settings.remove(obj); resources.remove(parent)
            assembly = settings.find('assemble')
            if assembly is not None:
                for item in list(assembly):
                    if item.get('object_id') == oid: assembly.remove(item)
            for item in list(build):
                if item.get('objectid') == oid: build.remove(item)
            for plate in plates:
                for instance in list(plate.findall('model_instance')):
                    if meta(instance)['object_id'] == oid: plate.remove(instance)
        elif name in ('EffectTray', 'IgnitionMOSCarrier'):
            component = parent.find(tag('components'))[0]
            path = component.get('{'+PN+'}path').lstrip('/')
            child = E.fromstring(files[path]); child_obj = child.find(tag('resources'))[0]
            mesh, count = raw_mesh(OUT / (name+'.stl'))
            child_obj.remove(child_obj.find(tag('mesh'))); child_obj.append(mesh)
            files[path] = xml(child)
            obj.find('metadata[@face_count]').set('face_count', str(count))
            obj.find('part/mesh_stat').set('face_count', str(count))
    assert set(deleted) == REMOVED
    # Bring the required gun seats forward; only the backpack and lid remain
    # on the last plate. A freed retainer location accommodates the MOS carrier.
    for name, x, y, rotate, identify in [('PP01-base',195,30,True,1001),
                                       ('PP02-base',211,93,False,1002),
                                       ('IgnitionMOSCarrier',180,160,False,None)]:
        obj = next(o for o in settings.findall('object') if meta(o)['name'] == name)
        oid = obj.get('id'); item = build.find("%s[@objectid='%s']" % (tag('item'), oid))
        tr = list(map(float,item.get('transform').split()))
        if rotate:
            for j in range(3): tr[j*3],tr[j*3+1] = -tr[j*3+1],tr[j*3]
        tr[9],tr[10] = 614.4+x,-307.2+y
        item.set('transform',' '.join(map(str,tr)))
        if identify is not None:
            instance = next(i for i in plates[4].findall('model_instance') if meta(i)['object_id']==oid)
            plates[4].remove(instance); plates[5].append(instance); setmeta(instance,'identify_id',identify)
        assembly = settings.find('assemble')
        if assembly is not None:
            for item in assembly:
                if item.get('object_id')==oid and item.get('instance_id') is not None:
                    item.set('transform',' '.join(map(str,tr)))
    # Drop orphaned mesh resources and relationships, not just visible objects.
    referenced = {c.get('{'+PN+'}path').lstrip('/') for c in resources.findall('.//'+tag('component'))}
    for path in list(files):
        if path.startswith('3D/Objects/') and path.endswith('.model') and path not in referenced:
            del files[path]
    rel = E.fromstring(files['3D/_rels/3dmodel.model.rels'])
    for node in list(rel):
        if node.get('Target').lstrip('/') not in referenced: rel.remove(node)
    files['3D/_rels/3dmodel.model.rels'] = relxml(rel)
    files['3D/3dmodel.model'] = xml(root); files['Metadata/model_settings.config'] = xml(settings)
    # A modified plate must not carry the old cached G-code before it is sliced.
    for index in (2, 5, 6):
        for suffix in ('.gcode', '.gcode.md5'): files.pop(f'Metadata/plate_{index}'+suffix, None)
    archive_write(OUT/'input.3mf', files)
    return files


def slice_plate(index):
    dest = OUT / ('plate-'+str(index)); dest.mkdir(exist_ok=True)
    with (dest/'run.log').open('w') as log:
        p = subprocess.run(['/Applications/BambuStudio.app/Contents/MacOS/BambuStudio',
            '--orient','0','--arrange','0','--slice',str(index),'--outputdir',str(dest),str(OUT/'input.3mf')],
            stdout=log, stderr=subprocess.STDOUT, timeout=600)
    assert p.returncode == 0, (index, p.returncode, str(dest/'run.log'))
    result = json.loads((dest/'result.json').read_text()); stats = result['sliced_plates'][0]
    assert not stats['warning_message'], stats['warning_message']
    assert stats['times']['conflict_check_time'] > 0
    return index, stats


def finish(files, results):
    root = E.fromstring(files['3D/3dmodel.model']); settings = E.fromstring(files['Metadata/model_settings.config'])
    info = E.fromstring(files['Metadata/slice_info.config']); plates = settings.findall('plate'); infos = info.findall('plate')
    old_stats = {i: meta(p) for i, p in enumerate(infos, 1)}
    for index, stats in results:
        gc = (OUT/('plate-'+str(index))/f'plate_{index}.gcode').read_bytes()
        plate = plates[index-1]; ip = infos[index-1]
        active = {meta(inst)['identify_id'] for inst in plate.findall('model_instance')}
        labels = {x.decode() for x in re.findall(rb'unique label id: (\d+)', gc)}
        assert labels == active, (index, labels, active)
        for obj in list(ip.findall('object')): ip.remove(obj)
        names = {o.get('id'):meta(o)['name'] for o in settings.findall('object')}
        for inst in plate.findall('model_instance'):
            md = meta(inst)
            E.SubElement(ip,'object',identify_id=md['identify_id'],name=names[md['object_id']],skipped='false')
        grams = sum(f['total_used_g'] for f in stats['filaments'])
        setmeta(ip, 'prediction', int(stats['total_predication'])); setmeta(ip, 'weight', round(grams, 2))
        fil = ip.find('filament'); fil.set('used_g', str(round(grams,2)))
        length = float(re.search(rb'total filament length \[mm\] : ([\d.]+)', gc)[1]); fil.set('used_m', str(round(length/1000,2)))
        count = int(re.search(rb'total layer number: (\d+)', gc)[1])
        ip.find('layer_filament_lists/layer_filament_list').set('layer_ranges', '0 '+str(count-1))
        files[f'Metadata/plate_{index}.gcode'] = gc
        files[f'Metadata/plate_{index}.gcode.md5'] = hashlib.md5(gc).hexdigest().encode()
    # Move whole plates in the editor grid only; emitted coordinates stay local.
    mapping = {old: new for new, old in enumerate(ORDER, 1)}
    objects = {meta(i)['object_id']: old for old, p in enumerate(plates, 1) for i in p.findall('model_instance')}
    origin = lambda i: (((i-1)%3)*307.2, -((i-1)//3)*307.2)
    for item in root.find(tag('build')):
        old = objects[item.get('objectid')]; a, b = origin(old), origin(mapping[old])
        tr = list(map(float, item.get('transform').split())); tr[9] += b[0]-a[0]; tr[10] += b[1]-a[1]
        item.set('transform', ' '.join(map(str, tr)))
    assembly = settings.find('assemble')
    if assembly is not None:
        for item in assembly:
            if item.get('instance_id') is not None:
                old = objects[item.get('object_id')]; a, b = origin(old), origin(mapping[old])
                tr = list(map(float, item.get('transform').split())); tr[9] += b[0]-a[0]; tr[10] += b[1]-a[1]
                item.set('transform', ' '.join(map(str, tr)))
    remap = lambda s: re.sub(r'plate_(\d+)(?=[._])', lambda m: 'plate_'+str(mapping[int(m[1])]), s)
    files = {remap(n): v for n,v in files.items()}
    for p in plates: settings.remove(p)
    for p in infos: info.remove(p)
    rows = []
    for new, old in enumerate(ORDER, 1):
        p, ip = plates[old-1], infos[old-1]
        for m in p.findall('metadata'): m.set('value', remap(m.get('value')))
        setmeta(p, 'plater_id', new); setmeta(p, 'plater_name', TITLES[new-1]); setmeta(ip, 'index', new)
        settings.append(p); info.append(ip)
        md = meta(ip); rows.append({'plate':new,'original_plate':old,'name':TITLES[new-1],
            'parts':len(p.findall('model_instance')), 'seconds':float(md['prediction']), 'grams':float(md['weight']),
            'old_seconds':float(old_stats[old]['prediction']), 'old_grams':float(old_stats[old]['weight'])})
    seq = json.loads(files['Metadata/filament_sequence.json'])
    files['Metadata/filament_sequence.json'] = json.dumps({'plate_'+str(mapping[int(k.split('_')[1])]):v for k,v in seq.items()}).encode()
    rel = E.fromstring(files['Metadata/_rels/model_settings.config.rels'])
    for node in rel: node.set('Target', remap(node.get('Target')))
    files['Metadata/_rels/model_settings.config.rels'] = relxml(rel)
    files['3D/3dmodel.model'] = xml(root); files['Metadata/model_settings.config'] = xml(settings); files['Metadata/slice_info.config'] = xml(info)
    for new in (2, 3, 6):
        # Remove stale rendered images from changed plates; fresh previews are
        # attached by the path-check step, and Studio renders the real meshes.
        for name in list(files):
            if re.fullmatch(f'Metadata/plate_{new}(?:_[^/]*)?\\.png', name): del files[name]
        for m in list(plates[ORDER[new-1]-1].findall('metadata')):
            if 'thumbnail' in m.get('key',''): plates[ORDER[new-1]-1].remove(m)
    files['Metadata/model_settings.config'] = xml(settings)
    with zipfile.ZipFile(BASE) as old:
        for i in (1,3,4): assert files[f'Metadata/plate_{mapping[i]}.gcode'] == old.read(f'Metadata/plate_{i}.gcode')
        assert files['Metadata/project_settings.config'] == old.read('Metadata/project_settings.config')
    archive_write(TARGET, files)
    report = {'project':str(TARGET.relative_to(ROOT)), 'project_sha256':sha(TARGET.read_bytes()),
        'original_project_sha256':sha(BASE.read_bytes()), 'plates':rows,'ordinary_print_parts':sum(r['parts'] for r in rows),
        'removed':sorted(REMOVED),'modified_geometry':['EffectTray','IgnitionMOSCarrier'],
        'unchanged_gcode_original_plates':[1,3,4], 'process_and_material_settings_preserved':True,
        'moved_parts':['PP01-base','PP02-base','IgnitionMOSCarrier'],
        'saved_seconds':sum(r['old_seconds']-r['seconds'] for r in rows),
        'saved_grams':sum(r['old_grams']-r['grams'] for r in rows), 'GUI_verified':False}
    assert report['ordinary_print_parts'] == 29
    (OUT/'delivery-check.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__ == '__main__':
    files = prepare()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(slice_plate, (2, 5, 6)))
    finish(files, results)
