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
            self.assertEqual(set(archive.namelist()), set(paths) | {"MANIFEST.json", "START_HERE.md", "family/rehearsal.html", "replay/voice.json", "replay/compose.json", "replay/ct57/voice.json", "replay/ct57/compose.json", "replay/firmware-host/voice.json", "replay/firmware-host/compose.json", "replay/qwen/voice.json", "replay/qwen/compose.json", "replay/doubao/compose.json", "replay/stt/voice.json", "replay/compact-receipts/compose.json", "replay/stop-negation/voice.json", "replay/stop-negation/compose.json"})
            manifest = json.loads(archive.read("MANIFEST.json"))
            current = json.loads(archive.read("firmware/current.json"))
            build = json.loads(archive.read("firmware/" + current["software_evidence"]))
            self.assertEqual(build["version"], current["source_version"])
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
            compose = result["firmware_host_scores"]["compose"]
            self.assertEqual((compose["scored"], compose["correct"]), (8, 6))
            self.assertEqual(compose["incomplete"], ["C005"])
            self.assertEqual(compose["mismatch_ids"], ["C005", "C008"])
            self.assertFalse(compose["tool_call_target_met"])
            captured = json.loads(archive.read("replay/firmware-host/compose.json"))
            self.assertFalse(next(row for row in captured["results"] if row["id"] == "C005")["completed"])
            qwen = result["qwen_scores"]["voice"]
            self.assertEqual((qwen["scored"], qwen["correct"]), (80, 68))
            self.assertEqual(qwen["failed_stop_cases"], ["V049"])
            self.assertEqual(qwen["forbidden_call_cases"], ["V079"])
            doubao = result["doubao_compose_scores"]["compose"]
            self.assertEqual((doubao["scored"], doubao["correct"]), (8, 3))
            self.assertEqual(doubao["invalid_tool_argument_cases"], ["C002", "C007"])
            self.assertEqual(doubao["forbidden_call_cases"], ["C005", "C006"])
            self.assertFalse(doubao["tool_call_target_met"])
            speech = result["spoken_stt_review"]
            self.assertEqual((speech["expected"], speech["completed"], speech["calls_match"]), (20, 19, 19))
            self.assertEqual(speech["not_completed"], ["V017"])
            self.assertEqual(speech["transcript_matches"], 19)
            compact = result["compact_receipt_scores"]["compose"]
            self.assertEqual((compact["scored"], compact["correct"]), (8, 5))
            self.assertEqual(compact["forbidden_call_cases"], ["C006"])
            self.assertFalse(compact["tool_call_target_met"])
            stop = result["stop_negation_scores"]
            self.assertEqual((stop["voice"]["scored"], stop["voice"]["correct"]), (80, 77))
            self.assertEqual(stop["voice"]["forbidden_call_cases"], ["V064", "V079"])
            self.assertEqual(stop["voice"]["failed_stop_cases"], [])
            self.assertFalse(stop["voice"]["tool_call_target_met"])
            self.assertEqual((stop["compose"]["scored"], stop["compose"]["correct"]), (8, 6))
            self.assertEqual(stop["compose"]["mismatch_ids"], ["C007", "C008"])
            self.assertEqual(stop["compose"]["forbidden_call_cases"], [])
            self.assertFalse(stop["compose"]["tool_call_target_met"])
            stop_trace = json.loads(archive.read("replay/stop-negation/voice.json"))
            self.assertEqual(next(row for row in stop_trace["results"] if row["id"] == "V079")["calls"],
                             [dict(name="self.tank.move", arguments=dict(direction="forward", duration_ms=1000))])
            guard = json.loads(archive.read("docs/validation/evidence/ct62-voice-turn/replay.json"))
            fallback = next(row for row in guard["archived_cases"] if row["id"] == "C005")
            self.assertEqual(fallback["starts"], 0)
            self.assertIn("voice_input_failed", fallback["results"][1])
            self.assertFalse(json.loads(archive.read("firmware/esp32-audio/verification-ct62.json"))["flashed"])
            stop_dispatch = json.loads(archive.read("docs/validation/evidence/ct66-stop-dispatch/replay.json"))
            self.assertTrue(stop_dispatch["passed"])
            self.assertEqual(stop_dispatch["scenarios"], 8)
            self.assertTrue(all(row["passed"] for row in stop_dispatch["results"]))
            comparison = json.loads(archive.read("docs/validation/evidence/ct66-stop-dispatch/comparison.json"))
            self.assertEqual(len(comparison["baseline_failed"]), 5)
            self.assertEqual(comparison["candidate_failed"], [])
            self.assertFalse(json.loads(archive.read("firmware/esp32-audio/verification-ct66.json"))["flashed"])
            qualifier = json.loads(archive.read("docs/validation/evidence/stop-role-qualifier/experiment.json"))
            self.assertTrue(qualifier["preflight_checks_met"])
            self.assertEqual(qualifier["decision"], "not_adopted")
            self.assertEqual(qualifier["result"]["candidate_silent_stops"], 0)
            self.assertTrue(qualifier["restored"]["saved_platform_role"])
            self.assertEqual(qualifier["result"]["baseline_C008_revision"], 8)
            relative = json.loads(archive.read("docs/validation/evidence/ct67-relative-draft/platform-review.json"))
            self.assertEqual((relative["total"], relative["completed"], relative["state_matches"]), (20, 20, 20))
            self.assertEqual(relative["tool_matches"], 14)
            self.assertEqual(relative["clarification_rejections"], 0)
            self.assertEqual(relative["relative_states_preserved"], 6)
            self.assertNotEqual(relative["capture_host_sha256"], relative["host_sha256"])
            native = json.loads(archive.read("docs/validation/evidence/ct67-relative-draft/native-replay.json"))
            self.assertTrue(native["passed"])
            self.assertEqual(native["scenarios"], 13)
            self.assertFalse(json.loads(archive.read("firmware/esp32-audio/verification-ct67.json"))["flashed"])
            vague = json.loads(archive.read("docs/validation/evidence/ct68-vague-action/platform-review.json"))
            self.assertEqual((vague["total"], vague["completed"], vague["tool_matches"], vague["state_matches"]), (20, 20, 16, 20))
            self.assertEqual((vague["clarification_rejections"], vague["vague_states_preserved"]), (3, 8))
            self.assertNotIn("docs/validation/evidence/ct68-vague-action/platform-1.json.gz", archive.namelist())
            self.assertFalse(json.loads(archive.read("firmware/esp32-audio/verification-ct68.json"))["flashed"])
            routing = json.loads(archive.read("docs/validation/evidence/intent-routing-role/review.json"))
            self.assertFalse(routing["structural_preflight_passed"])
            for group in routing["groups"].values():
                self.assertEqual((group["total"], group["completed"], group["strict_matches"]), (36, 36, 29))
                self.assertEqual(group["stops_without_tts_text"], 0)
            self.assertTrue(json.loads(archive.read("docs/validation/evidence/intent-routing-role/restored-readback.json"))["savedAndReopened"])
            inputs = json.loads(archive.read("docs/validation/evidence/capture-recognized-input/summary.json"))
            self.assertEqual((inputs["total"], inputs["completed"], inputs["strict_tool_matches"], inputs["state_matches"]), (24, 24, 20, 24))
            self.assertEqual(inputs["clarification_rejections"], 2)
            legacy_input = json.loads(archive.read("docs/validation/evidence/capture-recognized-input/legacy-review.json"))
            self.assertEqual(legacy_input["host_input_mode"], "simulated_initial_input")
            self.assertEqual(legacy_input["strict_tool_matches"], 9)
            self.assertNotIn("device_id", manifest["firmware"])
            for name in ("replay/voice.json", "replay/ct57/voice.json", "replay/firmware-host/voice.json", "replay/firmware-host/compose.json", "replay/qwen/voice.json", "replay/doubao/compose.json", "replay/stt/voice.json", "replay/compact-receipts/compose.json", "replay/stop-negation/voice.json", "replay/stop-negation/compose.json"):
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

    def test_missing_current_build_evidence_is_rejected(self):
        paths = json.loads((ROOT / "tools/lingxi-solution/files.json").read_bytes())
        current = json.loads((ROOT / "firmware/current.json").read_bytes())
        paths.remove("firmware/" + current["software_evidence"])
        with self.assertRaisesRegex(ValueError, "current candidate build evidence"):
            package.build_archive(ROOT, paths, "test-revision", False)

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
