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
