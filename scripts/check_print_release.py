"""Validate the retained six-plate delivery without deleted slicing intermediates."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as E
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'hardware/model'
READY = MODEL / 'print-ready'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check():
    latest = MODEL / 'bottle-backpack-direct-fit.json'
    if latest.exists():
        cad = json.loads(latest.read_text())
        print_report = cad['projects']
        for relative, digest in cad['files_sha256'].items():
            assert sha(MODEL / relative) == digest, relative
        assert all(not (MODEL / relative).exists() for relative in cad['retired_exports'])
        assert all(row['pass'] for row in cad['bottle_service'].values())
    else:
        cad = json.loads((MODEL / 'v2-cad-readback.json').read_text())
        print_report = json.loads((MODEL / 'v2-print-readback.json').read_text())
        for relative in ('CyberTrack.FCStd', 'source/CyberTrack-design.FCStd', 'CyberTrack.step'):
            path = MODEL / relative
            assert sha(path) == cad['files_sha256'][path.name], relative
    assert cad['saved_reopened']
    for row in print_report:
        path = ROOT / row['path']
        assert sha(path) == row['sha256'], path
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            settings = E.fromstring(archive.read('Metadata/model_settings.config'))
            names = [obj.find("metadata[@key='name']").get('value') for obj in settings.findall('object')]
            assert names == row['part_names']
            assert 'IgnitionMOSCarrier' not in names
            assert not set(row['removed']).intersection(names)
            assert len(names) == len(set(names)) == row['print_parts']
            assert len(settings.findall('plate')) == 6
            for plate in row['requires_reslice_plates']:
                assert f'Metadata/plate_{plate}.gcode' not in archive.namelist(), plate
    return {'passed': True, 'scope': 'v2 native and print project identity; affected caches invalidated',
            'projects': print_report, 'slicing_validated': False, 'physical_fit_verified': False}


if __name__ == '__main__':
    report = check()
    (READY / 'release-check.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
