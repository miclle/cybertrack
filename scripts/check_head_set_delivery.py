"""Verify head-set mesh preservation, settings and plate paths; render the first layer."""
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as E
import zipfile

from check_head_print_paths import layers

BASE = Path(__file__).resolve().parents[1] / 'hardware/model/print-parts/PP07-slicing'
STUDY = BASE / 'head-set-speed'
NS = {'c': 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
PNS = '{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}'


def meshes(path):
    with zipfile.ZipFile(path) as archive:
        main = E.fromstring(archive.read('3D/3dmodel.model'))
        settings = E.fromstring(archive.read('Metadata/model_settings.config'))
        result = {}
        for obj in settings.findall('object'):
            parent = main.find("c:resources/c:object[@id='%s']" % obj.get('id'), NS)
            for part in obj.findall("part[@subtype='normal_part']"):
                component = parent.find("c:components/c:component[@objectid='%s']" % part.get('id'), NS)
                resource = E.fromstring(archive.read(component.get(PNS+'path').lstrip('/')))
                mesh = resource.find("c:resources/c:object[@id='%s']/c:mesh" % part.get('id'), NS)
                vertices = [tuple(float(v.get(k)) for k in ('x','y','z')) for v in mesh.find('c:vertices', NS)]
                triangles = [tuple(int(v.get(k)) for k in ('v1','v2','v3')) for v in mesh.find('c:triangles', NS)]
                name = part.find("metadata[@key='name']").get('value')
                result[name] = (vertices, triangles)
        return result


def main():
    from PIL import Image, ImageDraw
    sources = {
        'PP05-Crown-PLA-Basic-FAST.3mf': STUDY/'crown-arachne-seats/crown-arachne-seats.3mf',
        'Head-Tray-PLA-Basic-FAST.3mf': STUDY/'tray-wide/tray-wide.3mf',
        'Head-Crown-Tray-PLA-Basic-FAST.3mf': STUDY/'combined/Head-Crown-Tray-FAST.3mf',
    }
    manifest = json.loads((BASE/'independent-parts.json').read_text())
    for part in manifest['parts']:
        assert hashlib.sha256((BASE.parent/part['stl']).read_bytes()).hexdigest() == part['input_stl_sha256']
    baseline = meshes(BASE/'Crown/Crown.3mf') | meshes(BASE/'Tray/Tray.3mf')
    report = {'mesh_checks': {}, 'files': {}}
    for name, source in sources.items():
        actual = meshes(source)
        assert all(mesh == baseline[key] for key, mesh in actual.items()), name
        report['mesh_checks'][name] = {k: len(v[1]) for k,v in actual.items()}
        shutil.copy2(source, BASE/name)
        report['files'][name] = hashlib.sha256(source.read_bytes()).hexdigest()
    project = BASE/'Head-Crown-Tray-PLA-Basic-FAST.3mf'
    with zipfile.ZipFile(project) as z:
        config = json.loads(z.read('Metadata/project_settings.config'))
        settings = E.fromstring(z.read('Metadata/model_settings.config'))
        tray = next(o for o in settings.findall('object') if o.find("metadata[@key='name']").get('value') == 'PP07-Tray.stl')
        for key,value in {'wall_loops':'3','outer_wall_line_width':'0.5','inner_wall_line_width':'0.5','top_shell_layers':'5','bottom_shell_layers':'4','wall_generator':'classic'}.items():
            assert tray.find("metadata[@key='%s']" % key).get('value') == value
        mods = settings.findall("object/part[@subtype='modifier_part']")
        assert len(mods) == 4
        for part in mods:
            assert part.find("metadata[@key='sparse_infill_density']").get('value') == '100%'
            assert part.find("metadata[@key='wall_loops']").get('value') == '4'
        assert config['print_sequence'] == 'by layer'
        assert config['nozzle_diameter'] == ['0.4'] and config['layer_height'] == '0.28'
        assert config['filament_settings_id'] == ['Bambu PLA Basic @BBL P2S']
        assert config['filament_max_volumetric_speed'][0] == '21'
        assert all(int(v) == 0 for node in settings.findall('.//mesh_stat')
                   for k,v in node.attrib.items() if k != 'face_count')
        (STUDY/'combined/plate-preview.png').write_bytes(z.read('Metadata/plate_1.png'))
    paths = layers(project, include_support=True)
    first = paths[min(paths)]
    bounds = [min(min(a[i],b[i])-w/2 for a,b,w,_ in first) for i in (0,1)]
    bounds += [max(max(a[i],b[i])+w/2 for a,b,w,_ in first) for i in (0,1)]
    assert all(v >= 0 for v in bounds[:2]) and all(v <= 256 for v in bounds[2:]), bounds
    im = Image.new('RGB',(848,848),'#f5f7fa'); d = ImageDraw.Draw(im)
    xy = lambda p:(40+p[0]*3,808-p[1]*3)
    d.rectangle((40,40,808,808),outline='#687787',width=2)
    for a,b,w,feature in first:
        color = '#e39e40' if feature.startswith('Support') else '#96a1ad' if feature=='Brim' else '#256fab'
        d.line((xy(a),xy(b)),fill=color,width=max(1,round(w*3)))
    d.text((40,16),'Crown + Tray | first-layer paths | blue: model, orange: support, grey: brim',fill='#182433')
    im.save(STUDY/'combined/first-layer-paths.png')
    report.update(first_layer_bounds_xy_mm=bounds,normal_parts=2,modifier_regions=4,
                  mesh_repairs=0,settings_passed=True,
                  limits='Mesh/settings and extrusion-footprint checks, not physical strength or printer execution acceptance.')
    head=BASE/'PP07-P2S-PLA-Basic-wide-fast.3mf'
    report['files'][head.name]=hashlib.sha256(head.read_bytes()).hexdigest()
    (STUDY/'delivery-check.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
