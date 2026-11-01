"""Synthetic binary fixtures parsed by the installed ESP-IDF parser; no device access."""
import importlib.util
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from zlib import crc32

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("review_nvs", ROOT / "scripts/review_nvs_config.py")
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def entry(namespace, key, kind, value, chunk=255):
    children = b""
    if kind in (0x21, 0x41, 0x42):
        children = value + b"\xff" * (-len(value) % 32)
        payload = struct.pack("<HHI", len(value), 0xffff, crc32(value, 0xffffffff))
    elif kind == 0x48:
        payload = struct.pack("<IBB2x", *value)
    else:
        payload = int(value).to_bytes(8, "little")
    raw = bytearray(bytes([namespace, kind, 1 + len(children) // 32, chunk]) + b"\0" * 4
                    + key.encode().ljust(16, b"\0") + payload)
    raw[4:8] = struct.pack("<I", crc32(raw[:4] + raw[8:], 0xffffffff))
    return bytes(raw) + children


def snapshot(*records):
    data = bytearray(b"\xff" * 4096)
    data[:9] = struct.pack("<IIB", 0xfffffffe, 0, 0xfe)
    data[28:32] = struct.pack("<I", crc32(data[4:28], 0xffffffff))
    content = b"".join(records)
    assert len(content) <= 4032
    data[64:64 + len(content)] = content
    for index in range(len(content) // 32):
        data[32 + index // 4] &= ~(1 << ((index % 4) * 2))
    return bytes(data)


def config(token=b"private-token\0", calibration=b"abcdefgh", split=False, wifi=b"private-ssid\0"):
    records = [entry(0, "wifi", 1, 1), entry(0, "websocket", 1, 2), entry(0, "phy", 1, 3),
               entry(1, "ssid", 0x21, wifi)]
    if token is not None:
        records.append(entry(2, "token", 0x21, token))
    if split:
        records += [entry(3, "cal_data", 0x42, calibration[:4], 128),
                    entry(3, "cal_data", 0x42, calibration[4:], 129),
                    entry(3, "cal_data", 0x48, (len(calibration), 2, 128))]
    else:
        records += [entry(3, "cal_data", 0x42, calibration, 0),
                    entry(3, "cal_data", 0x48, (len(calibration), 1, 0))]
    return snapshot(*records)


@unittest.skipUnless(os.environ.get("IDF_PATH"), "Set IDF_PATH to run actual ESP-IDF binary parser tests")
class ConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parser = staticmethod(review.load_parser(os.environ["IDF_PATH"])[0])

    def compare(self, before, after, **kwargs):
        return review.compare(before, after, self.parser, **kwargs)

    def test_identical(self):
        result = self.compare(config(), config())
        self.assertTrue(result["matches_policy"])
        self.assertEqual(result["logical_entries_after"], 3)

    def test_blob_index_layout_does_not_change_value(self):
        result = self.compare(config(split=True), config())
        self.assertTrue(result["all_logical_values_unchanged"])
        self.assertNotEqual(result["records_before"], result["records_after"])

    def test_runtime_differences_require_explicit_exception(self):
        a, b = config(split=True), config(token=b"new-token\0", calibration=b"new-data")
        self.assertFalse(self.compare(a, b)["matches_policy"])
        self.assertEqual(self.compare(a, b, allowed={"websocket/token"})["unexpected_changed_keys"], ["phy/cal_data"])
        result = self.compare(a, b, allowed={"websocket/token", "phy/cal_data"})
        self.assertTrue(result["matches_policy"])
        self.assertFalse(result["all_logical_values_unchanged"])
        self.assertNotIn("new-token", str(result))
        self.assertNotIn("private-ssid", str(result))

    def test_user_change_not_permitted(self):
        result = self.compare(config(), config(wifi=b"other\0"), allowed={"websocket/token", "phy/cal_data"})
        self.assertFalse(result["matches_policy"])
        self.assertEqual(result["unexpected_changed_keys"], ["wifi/ssid"])

    def test_runtime_deletion_is_not_exception(self):
        result = self.compare(config(), config(token=None), allowed={"websocket/token"})
        self.assertFalse(result["matches_policy"])
        self.assertEqual(result["removed_keys"], ["websocket/token"])
        result = self.compare(config(token=None), config(), allowed={"websocket/token"})
        self.assertFalse(result["matches_policy"])
        self.assertEqual(result["added_keys"], ["websocket/token"])

    def test_non_nvs_change_and_bounds(self):
        result = self.compare(b"a" + config() + b"z", b"b" + config() + b"z", offset=1, size=4096)
        self.assertFalse(result["matches_policy"])
        self.assertFalse(result["non_nvs_bytes_unchanged"])
        for kwargs in ({"offset": -1}, {"size": 8192}, {"size": 0}):
            with self.assertRaises(review.SnapshotError):
                self.compare(config(), config(), **kwargs)

    def test_corrupt_header_entry_and_data(self):
        good = config()
        # Header sequence, entry payload, and Wi-Fi string bytes respectively.
        for pos in (4, 64 + 24, 64 + 4 * 32):
            bad = bytearray(good)
            bad[pos] ^= 1
            with self.subTest(pos=pos), self.assertRaises(review.SnapshotError):
                self.compare(good, bad)

    def test_truncated_and_dirty_empty_page(self):
        for bad in (config()[:-1], b"\xff" * 64 + b"x" + b"\xff" * (4096 - 65)):
            with self.assertRaises(review.SnapshotError):
                self.compare(bad, bad)

    def test_duplicate_and_unknown_namespace(self):
        for records in ((entry(0, "wifi", 1, 1), entry(1, "ssid", 0x21, b"x\0"), entry(1, "ssid", 0x21, b"y\0")),
                        (entry(1, "ssid", 0x21, b"x\0"),)):
            bad = snapshot(*records)
            with self.assertRaises(review.SnapshotError):
                self.compare(bad, bad)

    def test_missing_or_wrong_size_blob_chunk(self):
        orphan = snapshot(entry(0, "phy", 1, 1), entry(1, "cal_data", 0x42, b"abcdefgh", 0))
        with self.assertRaises(review.SnapshotError):
            self.compare(orphan, orphan)
        for size, count, start in ((8, 2, 0), (9, 1, 0), (8, 2, 255)):
            bad = snapshot(entry(0, "phy", 1, 1), entry(1, "cal_data", 0x42, b"abcdefgh", 0),
                           entry(1, "cal_data", 0x48, (size, count, start)))
            with self.assertRaises(review.SnapshotError):
                self.compare(bad, bad)

    def test_cli_exit_codes_and_value_redaction(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / "a.bin", Path(folder) / "b.bin"
            a.write_bytes(config())
            b.write_bytes(config(token=b"secret-new-token\0"))
            cmd = [sys.executable, str(ROOT / "scripts/review_nvs_config.py"), "--before", str(a), "--after", str(b)]
            for extra, expected in (([], 1), (["--allow-runtime-change", "websocket/token"], 0)):
                result = subprocess.run(cmd + extra, text=True, capture_output=True)
                self.assertEqual(result.returncode, expected, result.stdout)
                self.assertNotIn("secret-new-token", result.stdout + result.stderr)
                self.assertNotIn("private-ssid", result.stdout + result.stderr)
            b.write_bytes(b"private-secret-invalid")
            result = subprocess.run(cmd, text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("private-secret-invalid", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
