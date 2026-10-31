#!/usr/bin/env python3
"""Copy the saved production model to an independent whole-model study."""
import hashlib
import json
from pathlib import Path
import shutil
import uuid

ROOT = Path(__file__).resolve().parents[1]


def prepare():
    source = ROOT / 'hardware/model/CyberTrack.FCStd'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    folder = ROOT / 'output/solidcue/assembly-studies' / uuid.uuid4().hex
    folder.mkdir(parents=True, exist_ok=False)
    target = folder / 'CyberTrackStudy.FCStd'
    shutil.copyfile(source, target)
    if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        raise ValueError('Study copy differs from production source')
    evidence = {'source': str(source.relative_to(ROOT)), 'source_sha256': digest,
                'study': str(target.relative_to(ROOT)), 'initial_copy_identical': True,
                'production_modified': False, 'physical_acceptance': 'not tested'}
    (folder/'provenance.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence,indent=2))


if __name__ == '__main__':
    prepare()
