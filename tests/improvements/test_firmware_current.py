import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('firmware_current', ROOT/'scripts/check_firmware_current.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FirmwareCurrentTests(unittest.TestCase):
    def test_role_only_update_keeps_original_firmware_deployment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fw=root/'firmware';audio=fw/'esp32-audio';audio.mkdir(parents=True)
            (audio/'apply_overlay.py').write_text('set(PROJECT_VER "2.0.3-ct45")')
            (audio/'role-prompt.txt').write_text('new role')
            digest=hashlib.sha256(b'new role').hexdigest()
            deployment={'version':'2.0.3-ct45','platform_role':{'sha256':'old role'}}
            (fw/'startup.json').write_text(json.dumps(deployment))
            (fw/'software.json').write_text(json.dumps({'version':'2.0.3-ct45'}))
            current={'source_version':'2.0.3-ct45','role_sha256':digest,'last_recorded_deployment':'startup.json',
                     'software_evidence':'software.json','deployment_relation':'matches_recorded_version','physical_acceptance':'incomplete'}
            (fw/'current.json').write_text(json.dumps(current))
            with self.assertRaisesRegex(ValueError,'role differs'):module.check(root)
            current['last_recorded_role_sync']='role-sync.json';(fw/'current.json').write_text(json.dumps(current))
            (fw/'role-sync.json').write_text(json.dumps({'version':'2.0.3-ct45','platform_role':{'sha256':digest}}))
            self.assertEqual(module.check(root)['role_sha256'],digest)
            self.assertEqual(json.loads((fw/'startup.json').read_text()),deployment)
            (fw/'role-sync.json').write_text(json.dumps({'version':'2.0.3-ct44','platform_role':{'sha256':digest}}))
            with self.assertRaisesRegex(ValueError,'role differs'):module.check(root)
