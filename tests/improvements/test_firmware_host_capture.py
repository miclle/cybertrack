import asyncio
import tempfile
from argparse import Namespace
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from capture_lingxi import capture_case, firmware_profile, run


class FirmwareHostCaptureTests(unittest.TestCase):
    def test_only_declared_preconditions_are_accepted(self):
        corpus = json.loads((Path(__file__).resolve().parents[2] / "docs/validation/voice-cases.json").read_bytes())
        self.assertEqual({firmware_profile(c["context"]) for c in corpus["cases"]},
                         {"corpus_idle", "corpus_forward70", "corpus_sequence"})
        with self.assertRaises(ValueError):
            firmware_profile("网页长按正在运行")

    def test_retired_preconditions_are_rejected(self):
        root = Path(__file__).resolve().parents[2]
        cases = json.loads((root/"docs/validation/compose-cases.json").read_bytes())["cases"]
        for case in cases:
            with self.assertRaises(ValueError):
                firmware_profile(case["context"])

    def test_full_host_rejects_fixture_transformations(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            connection = root/"connection.json"
            connection.write_text("{}")
            connection.chmod(0o600)
            tools = root/"tools.json"
            tools.write_text(json.dumps({"tools":[{"name":f"self.tank.tool{i}"} for i in range(11)]}))
            args = Namespace(connection=connection, tools=tools, output=root/"capture.json",
                             corpus=Path(__file__).resolve().parents[2]/"docs/validation/voice-cases.json",
                             ids="V001", raw_text=True, firmware_host=Path("/inert/host"),
                             argument_validator=Path("/inert/validator"))
            with self.assertRaisesRegex(ValueError,"own validation and status facts"):
                asyncio.run(run(args))

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

    def test_followup_reuses_connection_and_host_history_and_abort_stops(self):
        for aborted in (False, True):
            socket = AsyncMock()
            messages = [dict(type='hello', session_id='test'),
                        dict(type='mcp', payload=dict(method='tools/list', id=1)),
                        dict(type='stt', text='全速'),
                        dict(type='mcp', payload=dict(method='tools/call', id=2,
                            params=dict(name='self.tank.set_speed', arguments=dict(speed_percent=100)))),
                        dict(type='tts', state='stop', is_aborted=aborted)]
            if not aborted:
                messages += [dict(type='stt', text='左转一秒'),
                             dict(type='mcp', payload=dict(method='tools/call', id=3,
                                 params=dict(name='self.tank.move', arguments=dict(direction='left',duration_ms=1000)))),
                             dict(type='tts', state='stop')]
            socket.recv.side_effect = [json.dumps(m) for m in messages]
            connect = MagicMock()
            connect.return_value.__aenter__.return_value = socket
            wire = dict(result=dict(content=[dict(type='text',text='{"result":"ok"}')],isError=False))
            case = dict(id='R01',text='全速',context='',fixture_version='firmware_host',
                        host_binary=Path('/inert/host'),initial_profile='corpus_idle',host_stt_events=True,
                        opus_frames=[b'first'],uplink={'frames':1},
                        followups=[dict(text='左转一秒',opus_frames=[b'second'],uplink={'frames':1})])
            with patch.dict(sys.modules, {'websockets.asyncio.client':MagicMock(connect=connect)}), \
                    patch('capture_lingxi.firmware_replay',return_value=[wire,dict(starts_this_boot=0)]) as replay, \
                    patch('capture_lingxi.asyncio.sleep',new=AsyncMock()):
                row=asyncio.run(capture_case(dict(token='test',device_id='d',client_id='c'),
                    [dict(name='self.tank.set_speed'),dict(name='self.tank.move')],case))
            self.assertEqual(connect.call_count,1)
            self.assertEqual(row['completed'],not aborted)
            self.assertEqual(len(row['turns']),1 if aborted else 2)
            self.assertEqual([c['input_text'] for c in row['host_calls'] if 'input_text' in c],
                             ['全速'] if aborted else ['全速','左转一秒'])
            sent=[c.args[0] for c in socket.send.call_args_list]
            self.assertEqual([m for m in sent if isinstance(m,bytes)],
                             [b'first'] if aborted else [b'first',b'second'])
            self.assertTrue(all(c.kwargs['await_stt'] for c in replay.call_args_list))
            self.assertEqual(row['turns'][0]['call_start'],0)
            self.assertEqual(row['turns'][0]['call_end'],1)
            if not aborted:
                self.assertEqual(row['turns'][1]['call_start'],1)
                self.assertEqual(row['turns'][1]['call_end'],2)
                self.assertEqual(len(replay.call_args.args[2]),5)  # Both STTs/RPCs and final inspect.
