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
            image={'bytes':3,'sha256':hashlib.sha256(b'app').hexdigest()}
            deployment={'flash':image,'version':'2.0.3-ct45','platform_role':{'sha256':'old role'}}
            (fw/'startup.json').write_text(json.dumps(deployment))
            (fw/'software.json').write_text(json.dumps({'version':'2.0.3-ct45','artifact':image}))
            current={'source_version':'2.0.3-ct45','role_sha256':digest,'last_recorded_deployment':'startup.json',
                     'software_evidence':'software.json','deployment_relation':'matches_recorded_version','physical_acceptance':'incomplete'}
            (fw/'current.json').write_text(json.dumps(current))
            with self.assertRaisesRegex(ValueError,'role differs'):module.check(root)
            current['last_recorded_role_sync']='role-sync.json';(fw/'current.json').write_text(json.dumps(current))
            (fw/'role-sync.json').write_text(json.dumps({'version':'2.0.3-ct45','platform_role':{'sha256':digest}}))
            self.assertTrue(module.check(root)['role_matches_recorded_sync'])
            self.assertEqual(module.check(root)['role_sha256'],digest)
            self.assertEqual(json.loads((fw/'startup.json').read_text()),deployment)
            (fw/'role-sync.json').write_text(json.dumps({'version':'2.0.3-ct44','platform_role':{'sha256':digest}}))
            with self.assertRaisesRegex(ValueError,'role differs'):module.check(root)
            current['deployment_relation']='candidate_not_deployed'
            (fw/'current.json').write_text(json.dumps(current))
            (fw/'role-sync.json').write_text(json.dumps(deployment))
            self.assertFalse(module.check(root)['role_matches_recorded_sync'])

            # A new role can be pending even when the application version is unchanged.
            (root/'app.bin').write_bytes(b'app')
            verified=module.check(root, root/'app.bin', root/'app.bin')
            self.assertTrue(verified['local_source_image_checked'])
            self.assertEqual(verified['deployed_image'],image)
            (root/'app.bin').write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError,'application image does not match'):
                module.check(root, source_bin=root/'app.bin')
            with self.assertRaisesRegex(ValueError,'application image does not match'):
                module.check(root, deployed_bin=root/'app.bin')
            (fw/'software.json').write_text(json.dumps({'version':'2.0.3-ct44','artifact':image}))
            with self.assertRaisesRegex(ValueError,'evidence version'):
                module.check(root)
            (fw/'software.json').write_text(json.dumps({'version':'2.0.3-ct45','esp_idf_build':image}))
            self.assertEqual(module.check(root)['source_image'],image)
            (fw/'role-sync.json').write_text(json.dumps({'version':'2.0.3-ct44','platform_role':{'sha256':digest}}))
            with self.assertRaisesRegex(ValueError,'deployment version'):
                module.check(root)
