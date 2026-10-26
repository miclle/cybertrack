"""Pack existing rigid accessory meshes and compare local Bambu slicing candidates."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'hardware/model/l298n-compact/slicing'
INPUTS = BASE / 'orientation-inputs'
REFERENCE = ROOT / 'hardware/model/print-parts/PP04-slicing/PP04-P2S-PLA-FAST.3mf'
SLICER = '/Applications/BambuStudio.app/Contents/MacOS/BambuStudio'
NS = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
ET.register_namespace('', NS)
PARTS = [
    ('LC03-BottomServiceCover-flat', 70.8, 73.4, False),
    ('KeelSideFrameL', 73.5, 171.3, False),
    ('KeelSideFrameR', 73.5, 226.3, False),
    ('BatteryHatch', 186.4, 70.8, True),
    ('PrintNeck', 183.6, 167.6, False),
    ('LC01-Carrier-upright', 166.35, 222.35, False),
    ('LC02-TopRetainer-flat', 203.6, 220.475, False),
    ('ShoulderRailL', 238.7, 44.0, False),
    ('ShoulderRailR', 238.7, 136.5, False),
    ('NeckCableBridge', 236.8, 203.0, False),
    ('EffectRetainerLMOS', 168.9, 41.8, False),
    ('EffectRetainerLBuck', 189.4, 41.8, False),
    ('EffectRetainerRMOS', 168.9, 99.8, False),
    ('EffectRetainerRBuck', 189.4, 99.8, False),
]
VARIANTS = {
    'baseline-024': dict(layer_height='0.24', sparse_infill_pattern='gyroid',
        sparse_infill_line_width='0.45', internal_solid_infill_line_width='0.42',
        support_style='default', support_base_pattern_spacing='2.5'),
    'fast-024': {},
    'fast-028': dict(layer_height='0.28'),
    'tree-024': dict(support_type='tree(auto)', support_style='tree_hybrid'),
    'carrier-back-024': dict(carrier_orientation='back'),
    'fast-024-aligned': dict(independent_support_layer_height='0'),
    'fast-024-arachne': dict(wall_generator='arachne'),
    'cover-flipped-024': dict(cover_orientation='flipped'),
}


def load_mesh(path, rotate=False):
    data = path.read_bytes()
    count = struct.unpack_from('<I', data, 80)[0]
    assert len(data) == 84 + 50 * count, path
    vertices, triangles, indices = [], [], {}
    for i in range(count):
        xyz = struct.unpack_from('<12fH', data, 84+i*50)[3:12]
        face = []
        for j in range(0, 9, 3):
            x,y,z = xyz[j:j+3]
            vertex = (-y,x,z) if rotate else (x,y,z)
            if vertex not in indices:
                indices[vertex] = len(vertices)
                vertices.append(vertex)
            face.append(indices[vertex])
        triangles.append(face)
    lo = [min(v[a] for v in vertices) for a in range(3)]
    hi = [max(v[a] for v in vertices) for a in range(3)]
    offset = [(lo[0]+hi[0])/2, (lo[1]+hi[1])/2, lo[2]]
    return [tuple(v[a]-offset[a] for a in range(3)) for v in vertices], triangles, [hi[a]-lo[a] for a in range(3)]


def make_project(path, overrides):
    carrier = overrides.get('carrier_orientation', 'upright')
    model = ET.Element('model', unit='millimeter', xmlns=NS)
    resources = ET.SubElement(model, 'resources')
    build = ET.SubElement(model, 'build')
    rows = []
    for number,(original,x,y,rotate) in enumerate(PARTS, 1):
        stem = original.replace('Carrier-upright', 'Carrier-'+carrier)
        if original.startswith('LC03') and overrides.get('cover_orientation')=='flipped':
            stem='LC03-BottomServiceCover-flipped'
        if original.startswith('LC01') and carrier == 'back': y = 223.1
        source = INPUTS / (stem+'.stl')
        vertices, triangles, size = load_mesh(source, rotate)
        obj = ET.SubElement(resources, 'object', id=str(number), type='model', name=stem)
        mesh = ET.SubElement(obj, 'mesh')
        vs = ET.SubElement(mesh, 'vertices')
        ts = ET.SubElement(mesh, 'triangles')
        for vertex in vertices:
            ET.SubElement(vs, 'vertex', dict(zip(('x','y','z'), map(str,vertex))))
        for face in triangles:
            ET.SubElement(ts, 'triangle', dict(zip(('v1','v2','v3'), map(str,face))))
        ET.SubElement(build, 'item', objectid=str(number), transform=f'1 0 0 0 1 0 0 0 1 {x} {y} 0')
        bounds = [x-size[0]/2,y-size[1]/2,x+size[0]/2,y+size[1]/2]
        assert min(bounds) >= 2 and max(bounds) <= 254, (stem,bounds)
        rows.append(dict(name=stem, position_xy=[x,y], rotate_z_90=rotate, size_xyz_mm=size,
            bounds_xy=bounds, input_sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
    for i,a in enumerate(rows):
        for b in rows[i+1:]:
            if 'BatteryHatch' in (a['name'],b['name']) and any(n.startswith('EffectRetainer') for n in (a['name'],b['name'])):
                continue  # Nested in its four open bays; checked against native solids separately.
            aa,bb = a['bounds_xy'],b['bounds_xy']
            assert min(aa[2],bb[2]) <= max(aa[0],bb[0]) or min(aa[3],bb[3]) <= max(aa[1],bb[1]), (a['name'],b['name'])
    with zipfile.ZipFile(REFERENCE) as z:
        config = json.loads(z.read('Metadata/project_settings.config'))
    config.update(brim_width='2', print_settings_id='Accessory plate '+path.parent.name)
    config.update({k:v for k,v in overrides.items() if k not in ('carrier_orientation','cover_orientation')})
    # Generic 3MF carries independent objects; Bambu consumes its embedded process settings.
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr('3D/3dmodel.model', ET.tostring(model, encoding='utf-8', xml_declaration=True))
        z.writestr('Metadata/project_settings.config', json.dumps(config))
    process = json.loads((ROOT/'hardware/model/print-parts/PP04-slicing/process.json').read_text())
    process.update({k:v for k,v in config.items() if k in process})
    process['independent_support_layer_height'] = config.get('independent_support_layer_height','1')
    process.update(support_style=config['support_style'], type='process', name=config['print_settings_id'], **{'from':'user','instantiation':'true'})
    (path.parent/'process.json').write_text(json.dumps(process,indent=2)+'\n')
    (path.parent/'layout.json').write_text(json.dumps(rows,indent=2)+'\n')
    return rows


def run(name):
    target = BASE/'candidates'/name
    target.mkdir(parents=True, exist_ok=True)
    project = target/'input.3mf'
    layout = make_project(project, VARIANTS[name])
    with (target/'run.log').open('w') as log:
        p = subprocess.run([SLICER,'--load-settings',str(ROOT/'hardware/model/print-parts/PP04-slicing/machine.json')+';'+str(target/'process.json'),'--load-filaments',str(ROOT/'hardware/model/print-parts/PP04-slicing/filament.json'),'--orient','0','--arrange','0','--slice','0',
            '--export-3mf','Accessories.3mf','--outputdir',str(target),str(project)],
            stdout=log,stderr=subprocess.STDOUT,timeout=300)
    result_path = target/'result.json'
    if p.returncode != 0 or not result_path.exists():
        row = dict(name=name, overrides=VARIANTS[name], failed=True, return_code=p.returncode, diagnostic=(target/'run.log').read_text(), layout=layout)
        print(json.dumps(dict(name=name,failed=True,return_code=p.returncode)),flush=True)
        return row
    r = json.loads(result_path.read_text())
    plates = r['sliced_plates']
    row = dict(name=name, overrides=VARIANTS[name], plates=len(plates),
        seconds=sum(s['total_predication'] for s in plates),
        grams=sum(f['total_used_g'] for s in plates for f in s['filaments']),
        warning=[s['warning_message'] for s in plates if s['warning_message']],
        objects=len(layout), layout=layout,
        project=str((target/'Accessories.3mf').relative_to(BASE)))
    print(json.dumps({k:row[k] for k in ('name','seconds','grams','warning','plates','objects')}),flush=True)
    return row


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('variants',nargs='*')
    args=parser.parse_args()
    assert all(n in VARIANTS for n in args.variants)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        rows=list(pool.map(run,args.variants or list(VARIANTS)))
    path=BASE/'comparison.json'
    previous=json.loads(path.read_text()) if path.exists() else {}
    previous.update({r['name']:r for r in rows})
    path.write_text(json.dumps(previous,ensure_ascii=False,indent=2)+'\n')
