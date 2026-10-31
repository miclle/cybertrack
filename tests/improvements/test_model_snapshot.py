"""Preserve the FCStd archive contract used by FreeCAD GUI restoration."""
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("assembly_bridge", ROOT / "tools/model-design/assembly_bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class SnapshotPresentationTest(unittest.TestCase):
    def test_headless_copy_preserves_gui_registration_order_and_bytes(self):
        with TemporaryDirectory() as folder:
            source, target = Path(folder) / "source.FCStd", Path(folder) / "copy.FCStd"
            gui = b'<Document><MaterialList file="z-material"/><MaterialList file="a-material"/></Document>'
            with zipfile.ZipFile(source, "w") as archive:
                for name, data in [("Document.xml", b"old geometry"), ("GuiDocument.xml", gui),
                                   ("z-material", b"first color"), ("a-material", b"second color")]:
                    archive.writestr(name, data)

            def save_copy(path):
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("Document.xml", b"edited geometry")
                    archive.writestr("shape.brp", b"edited shape")

            doc = SimpleNamespace(FileName=str(source), Objects=[SimpleNamespace(ViewObject=None)], saveCopy=save_copy)
            bridge._save_copy(doc, target)
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(archive.namelist(), ["Document.xml", "shape.brp", "GuiDocument.xml", "z-material", "a-material"])
                self.assertEqual(archive.read("Document.xml"), b"edited geometry")
                self.assertEqual(archive.read("GuiDocument.xml"), gui)
                self.assertEqual(archive.read("z-material"), b"first color")
                self.assertEqual(archive.read("a-material"), b"second color")


if __name__ == "__main__":
    unittest.main()
