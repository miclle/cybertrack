import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from review_compose_routing import EVIDENCE, review


class ComposeRoutingTest(unittest.TestCase):
    def test_original_failure_and_draft_change_remain_visible(self):
        result = review()
        self.assertEqual(result['decision'], 'not_adopted')
        baseline, route = result['groups']['baseline'], result['groups']['route']
        self.assertEqual((baseline['sessions'], baseline['tool_calls_match']), (6, 2))
        self.assertEqual((route['sessions'], route['tool_calls_match']), (6, 5))
        self.assertEqual(route['unexpected_draft_changes'], ['route-C008-2.json.gz'])
        failure = next(r for r in result['rows'] if not r['draft_preserved'])
        self.assertEqual(failure['final_draft']['steps'][0]['move_ms'], 880)
        self.assertEqual(failure['final_draft']['steps'][1]['bubbles_ms'], 500)
        self.assertEqual(failure['starts'], 0)
        self.assertFalse(any(failure['logical_outputs'].values()))

    def test_missing_original_session_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'evidence'
            shutil.copytree(EVIDENCE, folder)
            path = folder / 'experiment.json'
            data = json.loads(path.read_bytes())
            data['runs'].pop()
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'all twelve original sessions'):
                review(folder)

    def test_changed_capture_cannot_keep_original_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'evidence'
            shutil.copytree(EVIDENCE, folder)
            path = folder / 'route-C005-1.json.gz'
            path.write_bytes(gzip.compress(b'{}'))
            with self.assertRaisesRegex(ValueError, 'differs from experiment manifest'):
                review(folder)

    def test_timeout_is_not_a_successful_no_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'evidence'
            shutil.copytree(EVIDENCE, folder)
            path = folder / 'route-C005-1.json.gz'
            trace = json.loads(gzip.decompress(path.read_bytes()))
            trace['results'][0].update(completed=False, completion='incomplete_or_timeout')
            raw = json.dumps(trace).encode()
            path.write_bytes(gzip.compress(raw))
            manifest_path = folder / 'experiment.json'
            manifest = json.loads(manifest_path.read_bytes())
            run = next(r for r in manifest['runs'] if r['capture'] == path.name)
            run['capture_json_sha256'] = hashlib.sha256(raw).hexdigest()
            manifest_path.write_text(json.dumps(manifest))
            result = review(folder)['groups']['route']
            self.assertEqual(result['tool_calls_match'], 4)
            self.assertEqual(result['incomplete'], [path.name])


if __name__ == '__main__':
    unittest.main()
