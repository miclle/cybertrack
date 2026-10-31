import asyncio
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from capture_lingxi import capture_case
from synthetic_speech import split_packets


class SyntheticSpeechTests(unittest.TestCase):
    def test_packet_boundaries(self):
        index = "#tb 0: 1/16000\n0,0,0,960,2,crc\n0,960,960,960,3,crc"
        self.assertEqual(split_packets(b"abcde", index), [b"ab", b"cde"])
        for bad in (b"", b"abc", b"abcdef"):
            with self.assertRaises(ValueError):
                split_packets(bad, index)

    def test_only_binary_phrase_is_sent(self):
        socket = AsyncMock()
        socket.recv.side_effect = [json.dumps(msg) for msg in (
            {"type": "hello", "session_id": "test"},
            {"type": "mcp", "payload": {"method": "tools/list", "id": 1}},
            {"type": "stt", "text": "停止。"}, {"type": "tts", "state": "stop"})]
        connection = MagicMock()
        connection.return_value.__aenter__.return_value = socket
        with patch.dict(sys.modules, {"websockets.asyncio.client": MagicMock(connect=connection)}):
            result = asyncio.run(capture_case(dict(token="test", client_id="c", device_id="d"), [],
                dict(id="V045", text="停止", context="", opus_frames=[b"packet1", b"packet2"])))
        sent = [c.args[0] for c in socket.send.call_args_list]
        self.assertEqual(sent[-4:], [json.dumps(dict(session_id="test", type="listen", state="start",
            mode="manual")), b"packet1", b"packet2", json.dumps(dict(session_id="test", type="listen", state="stop"))])
        self.assertFalse(any("停止" in msg for msg in sent if isinstance(msg, str)))
        self.assertTrue(result["completed"])
        self.assertEqual(result["echoed_text"], "停止。")

    def test_admission_envelopes_preserve_rejection(self):
        for as_result in (False, True):
            socket = AsyncMock()
            socket.recv.side_effect = [json.dumps(msg) for msg in (
                {"type": "hello", "session_id": "test"},
                {"type": "mcp", "payload": {"method": "tools/list", "id": 1}},
                {"type": "mcp", "payload": {"method": "tools/call", "id": 2,
                    "params": {"name": "self.tank.set_speed", "arguments": {"speed_percent": 100}}}},
                {"type": "tts", "state": "stop"})]
            connection = MagicMock()
            connection.return_value.__aenter__.return_value = socket
            error = "speed_rejected_not_moving: no movement at request time"
            with patch.dict(sys.modules, {"websockets.asyncio.client": MagicMock(connect=connection)}), \
                    patch("capture_lingxi.simulated_reply", return_value={"rpc_error": error}):
                result = asyncio.run(capture_case(dict(token="test", client_id="c", device_id="d"),
                    [{"name": "self.tank.set_speed"}], dict(id="V040", text="全速", context="",
                    admission_result_fixture=as_result)))
            reply = json.loads(socket.send.call_args_list[-1].args[0])["payload"]
            if as_result:
                content = json.loads(reply["result"]["content"][0]["text"])
                self.assertEqual(content["result"], "rejected")
                self.assertEqual(content["rejection_reason"], error)
                self.assertFalse(content["physical_feedback"])
                self.assertEqual(result["original_admission_errors"], [error])
            else:
                self.assertEqual(reply["error"]["message"], error)
                self.assertNotIn("simulated_receipts", result)

    def test_invalid_arguments_never_reach_fixture(self):
        socket = AsyncMock()
        socket.recv.side_effect = [json.dumps(msg) for msg in (
            {"type": "hello", "session_id": "test"},
            {"type": "mcp", "payload": {"method": "tools/list", "id": 1}},
            {"type": "mcp", "payload": {"method": "tools/call", "id": 2,
                "params": {"name": "self.tank.bubbles", "arguments": {"duration_ms": 60000}}}},
            {"type": "tts", "state": "stop"})]
        connection = MagicMock()
        connection.return_value.__aenter__.return_value = socket
        verdict = {"valid": False, "error": "actual gate rejected duration", "stop_requested": False}
        with patch.dict(sys.modules, {"websockets.asyncio.client": MagicMock(connect=connection)}), \
                patch("capture_lingxi.subprocess.check_output", return_value=json.dumps(verdict)), \
                patch("capture_lingxi.simulated_reply") as simulate:
            result = asyncio.run(capture_case(dict(token="test", client_id="c", device_id="d"),
                [{"name": "self.tank.bubbles"}], dict(id="V024", text="吹泡泡六十秒", context="",
                argument_validator=Path("/inert/test/checker"))))
        simulate.assert_not_called()
        self.assertNotIn("simulated_receipts", result)
        self.assertEqual(result["argument_checks"][0]["valid"], False)
        self.assertEqual(result["calls"][0]["arguments"]["duration_ms"], 60000)
        self.assertEqual(json.loads(socket.send.call_args_list[-1].args[0])["payload"]["error"]["message"],
                         verdict["error"])
