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
    bottles = json.loads((MODEL / 'bottle-backpack-direct-fit.json').read_text())
    head = json.loads((MODEL / 'pcb-speaker-fit.json').read_text())
    files = {**bottles['files_sha256'], **head['files_sha256']}
    for relative, digest in files.items():
        assert sha(MODEL / relative) == digest, relative
    assert all(not (MODEL / relative).exists() for relative in bottles['retired_exports'])
    assert all(row['pass'] for row in bottles['bottle_service'].values())
    assert bottles['saved_reopened'] and head['saved_reopened']
    for relative in ('CyberTrack.FCStd', 'source/CyberTrack-design.FCStd'):
        with zipfile.ZipFile(MODEL / relative) as archive:
            objects = E.fromstring(archive.read('Document.xml')).findall('./Objects/Object')
            names = {obj.get('name') for obj in objects}
            assert {'MainboardA1', 'ElectronicsTray', 'SpeakerL', 'SpeakerR', 'SpeakerFasteners'} <= names
            assert not any(n.startswith(('Breadboard', 'L298N', 'EffectMOS', 'MT3608')) for n in names)
    print_report = head['projects']
    for row in print_report:
        path = ROOT / row['path']
        assert sha(path) == row['sha256'], path
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            settings = E.fromstring(archive.read('Metadata/model_settings.config'))
            names = [obj.find("metadata[@key='name']").get('value') for obj in settings.findall('object')]
            assert names == row['part_names']
            assert 'IgnitionMOSCarrier' not in names
            assert not any(name in names for name in ('WaterPod', 'BubblePod', 'WaterLidMark', 'BubbleLidMark'))
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
