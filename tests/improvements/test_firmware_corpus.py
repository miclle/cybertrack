import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('firmware_corpus',ROOT/'scripts/firmware_corpus.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class FirmwareCorpusTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name);self.binary=self.root/'host';self.binary.write_bytes(b'fixture')
        self.sha=hashlib.sha256(self.binary.read_bytes()).hexdigest()

    def manifest(self,**values):
        (self.root/'manifest.json').write_text(json.dumps(dict(executable_sha256=self.sha,**values)))

    def test_legacy_projection_is_lossless_and_does_not_mutate(self):
        self.manifest()
        calls=[dict(name='self.tank.sequence',arguments=dict(steps_json='[]'),rpc_id=7,elapsed_ms=2)]
        projected=module.expected_commands(self.binary,calls)
        self.assertEqual(projected,calls);self.assertIsNot(projected,calls)
        projected[0]['arguments']['steps_json']='changed';self.assertEqual(calls[0]['arguments']['steps_json'],'[]')

    def test_native_projection_preserves_values_timing_and_empty_cancel(self):
        self.manifest(step_argument_format='native_array')
        step=dict(direction='left',move_ms=880,water_ms=0,bubbles_ms=1000,ignition_ms=0)
        calls=[dict(input_text='编排',elapsed_ms=0),dict(name='self.tank.sequence',arguments=dict(steps_json=json.dumps([step])),rpc_id=7,elapsed_ms=2),
               dict(name='self.tank.compose',arguments=dict(edit='cancel',revision=7,step=0,steps_json=''),rpc_id=8,elapsed_ms=3)]
        projected=module.expected_commands(self.binary,calls)
        self.assertEqual(projected[0],calls[0]);self.assertEqual(projected[1]['arguments'],dict(steps=[step]))
        self.assertEqual((projected[1]['rpc_id'],projected[1]['elapsed_ms']),(7,2))
        self.assertEqual(projected[2]['arguments'],dict(edit='cancel',revision=7,step=0,steps=[]))
        self.assertIn('steps_json',calls[1]['arguments'])

    def test_invalid_fixtures_are_not_repaired_and_ambiguous_fields_reject(self):
        self.manifest(step_argument_format='native_array')
        for encoded in ('[invalid',False):
            call=dict(name='self.tank.sequence',arguments=dict(steps_json=encoded))
            self.assertEqual(module.expected_commands(self.binary,[call]),[call])
        with self.assertRaises(ValueError):module.expected_commands(self.binary,[dict(name='self.tank.sequence',arguments=dict(steps=[],steps_json='[]'))])

    def test_wrong_binary_or_unknown_contract_rejects(self):
        self.manifest(step_argument_format='unknown')
        with self.assertRaises(ValueError):module.expected_commands(self.binary,[])
        self.manifest(step_argument_format='native_array');self.binary.write_bytes(b'changed')
        with self.assertRaises(ValueError):module.expected_commands(self.binary,[])
