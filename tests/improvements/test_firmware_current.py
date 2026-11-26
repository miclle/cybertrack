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
            with self.assertRaisesRegex(ValueError, 'no source build recorded for board: a1'):
                module.check(root, board='a1')
            (fw/'role-sync.json').write_text(json.dumps({'version':'2.0.3-ct44','platform_role':{'sha256':digest}}))
            with self.assertRaisesRegex(ValueError,'deployment version'):
                module.check(root)

    def test_each_board_checks_its_own_image_and_the_recorded_deployment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fw = root / 'firmware'
            audio = fw / 'esp32-audio'
            audio.mkdir(parents=True)
            version = '2.0.3-ct80'
            (audio/'apply_overlay.py').write_text(f'set(PROJECT_VER "{version}")')
            (audio/'role-prompt.txt').write_bytes(b'role')
            role_hash = hashlib.sha256(b'role').hexdigest()
            images = {}
            for board in ('a1', 'a4', 'breadboard'):
                data = board.encode()
                (root/board).write_bytes(data)
                images[board] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            (fw/'current.json').write_text(json.dumps({
                'source_version': version, 'role_sha256': role_hash,
                'last_recorded_deployment': 'deployment.json', 'software_evidence': 'software.json',
                'deployment_relation': 'matches_recorded_version', 'physical_acceptance': 'incomplete',
            }))
            (fw/'deployment.json').write_text(json.dumps({
                'version': version, 'flash': images['breadboard'], 'platform_role': {'sha256': role_hash},
            }))
            (fw/'software.json').write_text(json.dumps({
                'version': version, 'esp_idf_build': images['breadboard'], 'mainboard_a1_build': images['a1'],
                'mainboard_a4_build': images['a4'],
            }))
            self.assertEqual(module.check(root)['source_board'], 'a1')
            for board, other in [('a1', 'breadboard'), ('breadboard', 'a1'), ('a4', 'a1'), ('a1', 'a4')]:
                with self.subTest(board=board):
                    verified = module.check(root, root/board, root/'breadboard', board=board)
                    self.assertEqual(verified['source_image'], images[board])
                    self.assertEqual(verified['deployed_image'], images['breadboard'])
                    with self.assertRaisesRegex(ValueError, 'application image does not match'):
                        module.check(root, source_bin=root/other, board=board)
