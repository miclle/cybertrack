import asyncio
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from capture_lingxi import capture_case, firmware_profile


class FirmwareHostCaptureTests(unittest.TestCase):
    def test_only_declared_preconditions_are_accepted(self):
        corpus = json.loads((Path(__file__).resolve().parents[2] / "docs/validation/voice-cases.json").read_bytes())
        self.assertEqual({firmware_profile(c["context"]) for c in corpus["cases"]},
                         {"corpus_idle", "corpus_forward70", "corpus_sequence"})
        with self.assertRaises(ValueError):
            firmware_profile("网页长按正在运行")

    def test_actual_wire_envelope_and_rpc_id_are_preserved(self):
        for rejected in (False, True):
            socket = AsyncMock()
            socket.recv.side_effect = [json.dumps(msg) for msg in (
                {"type": "hello", "session_id": "test"},
                {"type": "mcp", "payload": {"method": "tools/list", "id": 1}},
                {"type": "mcp", "payload": {"method": "tools/call", "id": 41,
                    "params": {"name": "self.tank.get_status", "arguments": {}}}},
                {"type": "tts", "state": "stop"})]
            connect = MagicMock()
            connect.return_value.__aenter__.return_value = socket
            receipt = {"operation": "get_status", "result": "ok"}
            wire = {"error": {"message": "host rejection"}} if rejected else {
                "result": {"content": [{"type": "text", "text": json.dumps(receipt)}], "isError": False,
                           "extra_wire_field": 17}}
            final = {"starts_this_boot": 0}
            case = dict(id="V053", text="你现在在做什么", context="", fixture_version="firmware_host",
                        host_binary=Path("/inert/host"), initial_profile="corpus_idle", raw_text=True)
            with patch.dict(sys.modules, {"websockets.asyncio.client": MagicMock(connect=connect)}), \
                    patch("capture_lingxi.firmware_replay", return_value=[wire, final]) as replay, \
                    patch("capture_lingxi.simulated_reply") as simulate:
                result = asyncio.run(capture_case(dict(token="test", client_id="c", device_id="d"),
                                                  [{"name": "self.tank.get_status"}], case))
            simulate.assert_not_called()
            self.assertEqual(result["host_calls"][0]["rpc_id"], 41)
            self.assertEqual(set(result["calls"][0]), {"name", "arguments"})
            self.assertEqual(result["host_final_state"], final)
            self.assertIn("inspect_ms", replay.call_args.args[2][-1])
            payload = json.loads(socket.send.call_args_list[-1].args[0])["payload"]
            self.assertEqual(payload["id"], 41)
            self.assertEqual(payload["error"] if rejected else payload["result"],
                             wire["error"] if rejected else wire["result"])
