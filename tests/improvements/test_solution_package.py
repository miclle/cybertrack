import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("package_solution", ROOT / "scripts/package_lingxi_solution.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class SolutionPackageTest(unittest.TestCase):
    def test_exact_allowlist_and_integrity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / "reference.md").write_text("example")
            (root / "private.txt").write_text("must stay out")
            data = package.build_archive(root, ["reference.md"], "test-revision", False)
            self.assertEqual(data, package.build_archive(root, ["reference.md"], "test-revision", False))
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                self.assertEqual(set(archive.namelist()), {"reference.md", "MANIFEST.json", "START_HERE.md"})
                manifest = json.loads(archive.read("MANIFEST.json"))
                self.assertEqual(manifest["files"]["reference.md"]["sha256"], hashlib.sha256(b"example").hexdigest())

    def test_reject_outside_sensitive_and_symlink_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / "real.md").write_text("reference")
            (root / "alias.md").symlink_to(root / "real.md")
            for path in ["../real.md", "/real.md", "alias.md", "secrets/wifi.json", "recordings/transcript.txt", "x//y.md"]:
                with self.subTest(path=path), self.assertRaises(ValueError):
                    package.build_archive(root, [path], "test", False)


if __name__ == "__main__": unittest.main()
