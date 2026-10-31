import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("package_solution", ROOT / "scripts/package_lingxi_solution.py")
package = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(ROOT/"scripts"))
try:
    spec.loader.exec_module(package)
finally:
    sys.path.pop(0)


class SolutionPackageTest(unittest.TestCase):
    def test_exact_allowlist_and_integrity(self):
        paths = json.loads((ROOT / "tools/lingxi-solution/files.json").read_bytes())
        data = package.build_archive(ROOT, paths, "test-revision", False)
        self.assertEqual(data, package.build_archive(ROOT, paths, "test-revision", False))
        with tempfile.TemporaryDirectory() as folder, zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(set(archive.namelist()), set(paths) | {"MANIFEST.json", "START_HERE.md", "family/rehearsal.html", "replay/voice.json", "replay/compose.json", "replay/ct57/voice.json", "replay/ct57/compose.json", "replay/firmware-host/voice.json"})
            manifest = json.loads(archive.read("MANIFEST.json"))
            self.assertEqual(manifest["files"]["START_HERE.md"]["sha256"], hashlib.sha256(archive.read("START_HERE.md")).hexdigest())
            archive.extractall(folder)
            root = Path(folder)
            cli = [sys.executable, "-E", "-s", str(root/"scripts/review_lingxi_reference.py")]
            result = json.loads(subprocess.check_output(cli, cwd=folder, text=True))
            self.assertEqual(result["scores"]["compose"]["scored"], 8)
            self.assertEqual(result["scores"]["voice"]["scored"], 80)
            self.assertEqual(result["candidate_scores"]["voice"]["scored"], 80)
            self.assertEqual(result["candidate_scores"]["compose"]["scored"], 8)
            self.assertEqual(result["firmware_host_scores"]["voice"]["scored"], 80)
            self.assertEqual(result["firmware_host_scores"]["voice"]["input_mode"], "raw_text_diagnostic")
            self.assertNotIn("device_id", manifest["firmware"])
            for name in ("replay/voice.json", "replay/ct57/voice.json", "replay/firmware-host/voice.json"):
                replay = root/name
                original = replay.read_bytes()
                replay.write_bytes(original+b" ")
                failed = subprocess.run(cli, cwd=folder, capture_output=True, text=True)
                self.assertNotEqual(failed.returncode, 0)
                self.assertIn("differs from manifest", failed.stderr)
                replay.write_bytes(original)

    def test_cli_creates_archive_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/"reference.zip"
            command = [sys.executable, str(ROOT/"scripts/package_lingxi_solution.py"), "--output", str(output)]
            report = json.loads(subprocess.check_output(command, cwd=ROOT, text=True))
            original = output.read_bytes()
            self.assertEqual(hashlib.sha256(original).hexdigest(), report["sha256"])
            failed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(output.read_bytes(), original)

    def test_extensionless_license_and_notice_remain_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            for name in ["LICENSE", "NOTICE", "other"]:
                (root / name).write_text("reviewed legal text")
            contents = package.read_inputs(root, ["LICENSE", "NOTICE"])
            self.assertEqual(contents, {"LICENSE": b"reviewed legal text", "NOTICE": b"reviewed legal text"})
            with self.assertRaises(ValueError):
                package.read_inputs(root, ["other"])

    def test_reject_outside_sensitive_and_symlink_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / "real.md").write_text("reference")
            (root / "alias.md").symlink_to(root / "real.md")
            for path in ["../real.md", "/real.md", "alias.md", "secrets/wifi.json", "recordings/transcript.txt", "x//y.md"]:
                with self.subTest(path=path), self.assertRaises(ValueError):
                    package.read_inputs(root, [path])


if __name__ == "__main__": unittest.main()
