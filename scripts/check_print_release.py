"""Validate the retained six-plate delivery without deleted slicing intermediates."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as E
import zipfile

from check_print_project_preservation import read

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'hardware/model'
READY = MODEL / 'print-ready'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_legacy():
    project = READY / 'CyberTrack-Ready-6plates.3mf'
    inventory = json.loads((READY / 'completion-inventory.json').read_text())
    earlier = json.loads((READY / 'completeness-audit.json').read_text())
    delivery = json.loads((READY / 'six-plate-delivery-check.json').read_text())
    assert sha(project) == inventory['project_sha256'] == delivery['project_sha256']
    assert sha(MODEL / 'CyberTrack.FCStd') == inventory['model_sha256']
    with zipfile.ZipFile(MODEL / 'CyberTrack.FCStd') as archive:
        root = E.fromstring(archive.read('Document.xml'))
        native = {o.get('name') for o in root.find('ObjectData').findall('Object')
                  if o.find("Properties/Property[@name='Shape']/Part") is not None}
    expected = set(earlier['included']) | set(inventory['added_print_parts'])
    assert len(expected) == 34
    assert native == expected | set(inventory['other_objects'])
    assert not native.intersection(inventory['cancelled_by_user'])
    a, ao, ac, ap = read(READY / 'CyberTrack-Ready-5plates.3mf')
    b, bo, bc, bp = read(project)
    assert all(b[k] == v for k, v in a.items())
    assert all(bo[k] == v for k, v in ao.items()) and ap == bp[:5]
    for key, value in ac.items():
        assert (bc[key][:len(value)] == value if key in ('wipe_tower_x', 'wipe_tower_y')
                else bc[key] == value), key
    with zipfile.ZipFile(project) as archive, zipfile.ZipFile(READY / 'CyberTrack-Ready-5plates.3mf') as old:
        settings = E.fromstring(archive.read('Metadata/model_settings.config'))
        objects = {o.get('id'): o for o in settings.findall('object')}
        metadata = lambda n: {m.get('key'): m.get('value') for m in n.findall('metadata')}
        counts, names, hashes = [], [], {}
        for index, plate in enumerate(settings.findall('plate'), 1):
            parts = [metadata(p)['name'] for instance in plate.findall('model_instance')
                     for p in objects[metadata(instance)['object_id']].findall("part[@subtype='normal_part']")]
            counts.append(len(parts))
            names.extend(parts)
            path = f'Metadata/plate_{index}.gcode'
            code = archive.read(path)
            assert len(code) > 1000
            assert hashlib.md5(code).hexdigest() == archive.read(path + '.md5').decode().strip().lower()
            hashes[str(index)] = hashlib.sha256(code).hexdigest()
            if index <= 5:
                assert code == old.read(path)
            else:
                assert set(parts) == set(inventory['added_print_parts'])
                assert hashes[str(index)] == delivery['new_plate_gcode_sha256']
        assert counts == [1, 14, 1, 2, 4, 12]
        assert len(names) == len(set(names)) == 34
        assert len(b) == 38  # 34 ordinary meshes plus four crown-seat modifiers.
    paths = json.loads((MODEL / 'completion-print/path-check.json').read_text())
    final = paths['candidates']['merged-validation']
    assert final['passed'] and final['gcode_sha256'] == hashes['6']
    assert len(final['sections']) == 56 and all(r['passed'] for r in final['sections'])
    assert delivery['GUI_loaded'] and not delivery['new_plate_warning']
    return {'passed': True, 'native_geometry_objects': len(native), 'print_parts': len(names),
            'plates': counts, 'old_five_plates_unchanged': True, 'grommets_absent': True,
            'gcode_sha256': hashes, 'checked_new_plate_sections': 56,
            'limits': 'Saved model/project inventory and recorded path evidence; not physical acceptance.'}


def check():
    if (MODEL / 'backpack-print-update.json').exists():
        from check_backpack_release import check as check_backpack
        return check_backpack()
    lean = MODEL / 'lean-print'
    if not (lean / 'delivery-check.json').exists():
        return check_legacy()
    report = json.loads((lean / 'delivery-check.json').read_text())
    geometry = json.loads((lean / 'geometry-audit.json').read_text())
    project = ROOT / report['project']
    assert report['passed'] and sha(project) == report['project_sha256']
    assert sha(MODEL/'CyberTrack.FCStd') == geometry['documents']['delivery']['sha256']
    assert sha(MODEL/'source/CyberTrack-design.FCStd') == geometry['documents']['source']['sha256']
    baseline = MODEL / 'archive/print-baselines/CyberTrack-34parts-6plates.3mf'
    assert sha(baseline) == report['original_project_sha256']
    with zipfile.ZipFile(project) as z, zipfile.ZipFile(baseline) as old:
        settings = E.fromstring(z.read('Metadata/model_settings.config'))
        counts = [len(p.findall('model_instance')) for p in settings.findall('plate')]
        assert counts == [1,10,13,2,1,2]
        assert len(settings.findall('object')) == 29
        names = {o.find("metadata[@key='name']").get('value') for o in settings.findall('object')}
        assert not names.intersection(report['removed'])
        for row in report['plates']:
            i = row['plate']; path = f'Metadata/plate_{i}.gcode'; code = z.read(path)
            assert hashlib.sha256(code).hexdigest() == report['gcode_sha256'][str(i)]
            assert hashlib.md5(code).hexdigest() == z.read(path+'.md5').decode().strip().lower()
            if row['original_plate'] in report['unchanged_gcode_original_plates']:
                assert code == old.read(f"Metadata/plate_{row['original_plate']}.gcode")
        assert z.read('Metadata/project_settings.config') == old.read('Metadata/project_settings.config')
    assert all(r['passed'] for r in report['checked_native_sections'])
    return {'passed': True, 'project': report['project'], 'print_parts':29, 'plates':counts,
            'native_geometry_objects': report['verified_native_geometry_objects'],
            'checked_native_sections':len(report['checked_native_sections']),
            'unchanged_gcode_original_plates': report['unchanged_gcode_original_plates'],
            'saved_seconds':report['saved_seconds'], 'saved_grams':report['saved_grams'],
            'limits': report['limits']}


if __name__ == '__main__':
    report = check()
    (READY / 'release-check.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
