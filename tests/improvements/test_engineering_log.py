"""Temporary Git fixtures verify recording; they are not real efficiency samples."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("engineering_log", ROOT / "scripts/engineering_log.py")
log = importlib.util.module_from_spec(spec)
spec.loader.exec_module(log)


class EngineeringLogTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.records = self.root / "records"
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.commit("initial")

    def commit(self, value):
        (self.root / "source.txt").write_text(value)
        subprocess.run(["git", "add", "source.txt"], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "-c", "commit.gpgSign=false", "commit", "-qm", value], cwd=self.root, check=True)
        return log.git("rev-parse", "HEAD", root=self.root)

    def begin(self):
        return log.start(self.records, "example", "Synthetic fixture", self.root)

    def end(self, effort=None):
        commit = self.commit("changed")
        evidence = self.root / "check.json"
        evidence.write_text('{"fixture": true}')
        return log.finish(self.records, "example", commit, [evidence],
                          effort or dict.fromkeys(log.EFFORT_FIELDS), self.root)

    def test_empty_and_open_records_are_not_completed(self):
        self.assertEqual(log.report(self.records, self.root)["complete_records"], 0)
        self.begin()
        report = log.report(self.records, self.root)
        self.assertEqual(report["changes"][0]["missing"], ["finish record"])
        self.assertEqual(report["additional_complete_records_needed"], 5)

    def test_interval_commit_and_unknown_effort_remain_separate(self):
        with patch.object(log, "now", side_effect=["2026-10-31T00:00:00+00:00", "2026-10-31T00:02:03+00:00"]):
            self.begin(); self.end()
        report = log.report(self.records, self.root)
        self.assertEqual(report["complete_records"], 0)
        self.assertEqual(report["changes"][0]["finish"]["recorded_elapsed_seconds"], 123)
        self.assertEqual(set(report["changes"][0]["missing"]), set(log.EFFORT_FIELDS))
        self.assertEqual(report["efficiency_improvement"], "not_established")

    def test_complete_record_is_not_an_efficiency_claim_and_evidence_must_match(self):
        self.begin(); self.end(dict.fromkeys(log.EFFORT_FIELDS, 0))
        report = log.report(self.records, self.root)
        self.assertEqual(report["complete_records"], 1)
        self.assertEqual(report["efficiency_improvement"], "not_established")
        (self.root / "check.json").write_text("changed")
        report = log.report(self.records, self.root)
        self.assertEqual(report["complete_records"], 0)
        self.assertIn("evidence changed: check.json", report["changes"][0]["missing"])
        (self.root / "check.json").unlink()
        self.assertIn("evidence missing: check.json", log.report(self.records, self.root)["changes"][0]["missing"])

    def test_record_immutability_clock_reversal_and_start_hash(self):
        source = self.begin()
        with self.assertRaises(FileExistsError): self.begin()
        closed = self.end()
        record = json.loads(closed.read_text())
        with self.assertRaises(FileExistsError):
            log.finish(self.records, "example", record["commit"], [self.root / "check.json"],
                       dict.fromkeys(log.EFFORT_FIELDS), self.root)
        source.write_text(source.read_text()+"\n")
        with self.assertRaisesRegex(ValueError, "start record changed"):
            log.report(self.records, self.root)
        log.start(self.records, "backwards", "Synthetic clock", self.root)
        with patch.object(log, "now", return_value="2000-01-01T00:00:00+00:00"), self.assertRaisesRegex(ValueError, "backwards"):
            log.finish(self.records, "backwards", self.commit("next"), [self.root / "check.json"],
                       dict.fromkeys(log.EFFORT_FIELDS), self.root)

    def test_invalid_effort_identity_and_unchanged_commit_rejected(self):
        self.begin()
        for value in (True, -1, float("nan"), "0"):
            effort = dict.fromkeys(log.EFFORT_FIELDS); effort["human_minutes"] = value
            with self.subTest(value=value), self.assertRaises(ValueError): log.validate_effort(effort)
        effort = dict.fromkeys(log.EFFORT_FIELDS); effort["revision_rounds"] = 1.5
        with self.assertRaises(ValueError): log.validate_effort(effort)
        with self.assertRaises(ValueError): log.identifier("../outside")
        with self.assertRaisesRegex(ValueError, "new commit"):
            log.finish(self.records, "example", log.git("rev-parse", "HEAD", root=self.root), [],
                       dict.fromkeys(log.EFFORT_FIELDS), self.root)
        with self.assertRaisesRegex(ValueError, "explicit commit hash"):
            log.finish(self.records, "example", "HEAD", [], dict.fromkeys(log.EFFORT_FIELDS), self.root)

    def test_outside_evidence_or_orphan_record_rejected(self):
        self.begin(); commit = self.commit("changed")
        with self.assertRaises(ValueError):
            log.finish(self.records, "example", commit, [self.root.parent / "outside.json"],
                       dict.fromkeys(log.EFFORT_FIELDS), self.root)
        (self.records / "missing.finish.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "orphan"): log.report(self.records, self.root)

    def test_one_commit_cannot_be_counted_as_multiple_changes(self):
        self.begin()
        log.start(self.records, "other", "Second synthetic start", self.root)
        finished = json.loads(self.end().read_text())
        with self.assertRaisesRegex(ValueError, "another change record"):
            log.finish(self.records, "other", finished["commit"], [self.root / "check.json"],
                       dict.fromkeys(log.EFFORT_FIELDS), self.root)


if __name__ == "__main__":
    unittest.main()
