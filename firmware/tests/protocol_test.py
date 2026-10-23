"""Black-box tests: real C adapter behind a fake line transport, Python JSON oracle."""
import json
import subprocess
import sys
import unittest

HOST = sys.argv.pop(1)
BOOT, DISARMED, READY, ACTIVE, FAULT = range(5)
MOVE = {"direction": "forward", "speed_level": 2, "duration_ms": 100}
INIT = {"protocolVersion": "2024-11-05", "capabilities": {},
        "clientInfo": {"name": "offline-test", "version": "1"}}
MISSING = object()


def message(method, params=MISSING, request_id=1):
    payload = {"jsonrpc": "2.0", "method": method}
    if params is not MISSING:
        payload["params"] = params
    if request_id is not MISSING:
        payload["id"] = request_id
    return {"type": "mcp", "payload": payload}


def call(name, args=MISSING, request_id=2):
    params = {"name": "self.tank." + name}
    if args is not MISSING:
        params["arguments"] = args
    return message("tools/call", params, request_id)


class Device:
    def __init__(self, synthetic=True, budget=50):
        args = [HOST, "--synthetic-limits" if synthetic else "--no-limits", str(budget)]
        self.process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True)
        self.session = 0
        self.now = 0
        self.enable_generation = 0

    def event(self, text):
        self.process.stdin.write(text + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise AssertionError("host terminated: " + self.process.stderr.read())
        result = json.loads(line)
        self.session = result["session"]
        self.enable_generation = result["enable_generation"]
        return result

    def rpc(self, msg, *, now=None, received=None, fresh=True, session=None, enable_generation=None):
        if now is not None:
            self.now = now
        received = self.now if received is None else received
        session = self.session if session is None else session
        enable_generation = self.enable_generation if enable_generation is None else enable_generation
        raw = msg if isinstance(msg, str) else json.dumps(msg, ensure_ascii=True, separators=(",", ":"))
        return self.event(f"frame {session} {received} {self.now} {int(fresh)} {enable_generation}\t{raw}")

    def start(self, initialized=True, enabled=True):
        self.event("boot")
        self.event("open 0")
        if initialized:
            self.rpc(message("initialize", INIT, "init"))
        if enabled:
            self.event("enable 0")
        return self

    def close(self):
        self.process.stdin.close()
        remaining = self.process.stdout.read()
        errors = self.process.stderr.read()
        code = self.process.wait(timeout=10)
        self.process.stdout.close()
        self.process.stderr.close()
        if code or errors or remaining:
            raise AssertionError(f"host exit={code}, stderr={errors!r}, unexpected stdout={remaining!r}")


class ProtocolTests(unittest.TestCase):
    def device(self, **kwargs):
        device = Device(**kwargs)
        self.addCleanup(device.close)
        return device

    def off(self, result):
        self.assertEqual((result["left"], result["right"], result["water"], result["bubbles"], result["ends_at"]),
                         (0, 0, False, False, 0))

    def payload(self, result):
        reply = result["reply"]
        self.assertEqual(reply["type"], "mcp")
        p = reply["payload"]
        self.assertEqual(p["jsonrpc"], "2.0")
        self.assertNotEqual("error" in p, "result" in p)
        return p

    def error(self, result, code):
        self.assertEqual(self.payload(result)["error"]["code"], code)

    def tool(self, result, text=None, error=False):
        content = self.payload(result)["result"]
        self.assertEqual(content["isError"], error)
        self.assertEqual(content["content"][0]["type"], "text")
        if text is not None:
            self.assertEqual(content["content"][0]["text"], text)
        return content["content"][0]["text"]

    def test_initialize_discovery_and_schema(self):
        d = self.device().start(initialized=False, enabled=False)
        result = d.rpc(message("initialize", INIT, "初始化🔧"))
        payload = self.payload(result)
        self.assertEqual(payload["id"], "初始化🔧")
        self.assertEqual(payload["result"]["protocolVersion"], "2024-11-05")
        self.assertEqual(payload["result"]["capabilities"], {"tools": {}})
        self.off(result)
        result = d.rpc(message("tools/list", request_id="list"))
        tools = self.payload(result)["result"]["tools"]
        self.assertEqual([t["name"] for t in tools], ["self.tank." + s for s in
                         ["get_status", "stop", "move", "water", "bubbles"]])
        self.assertTrue(all(t["inputSchema"]["additionalProperties"] is False for t in tools))
        props = tools[2]["inputSchema"]["properties"]
        self.assertEqual(props["direction"]["enum"], ["forward", "backward", "left", "right"])
        self.assertEqual(props["duration_ms"]["maximum"], 1000)
        self.assertEqual(props["speed_level"]["maximum"], 3)
        self.error(d.rpc(message("tools/list", {"cursor": "unknown"}, "page")), -32602)
        self.assertIsNone(d.rpc(message("notifications/initialized", request_id=MISSING))["reply"])

    def test_version_and_initialization_gates(self):
        d = self.device().start(initialized=False)
        self.error(d.rpc(call("move", MOVE)), -32000)
        self.error(d.rpc(message("initialize", {**INIT, "protocolVersion": "2099-01-01"}, 3)), -32602)
        result = d.rpc(message("initialize", INIT, 4))
        self.assertTrue(result["initialized"])
        self.error(d.rpc(message("initialize", INIT, 5)), -32000)
        # Failed pre-initialize call remains rejected after initialization.
        self.error(d.rpc(call("move", MOVE)), -32000)
        self.assertEqual(self.payload(d.rpc(message("ping", request_id=6)))["result"], {})

    def test_default_capabilities_and_status(self):
        d = self.device(synthetic=False).start()
        tools = self.payload(d.rpc(message("tools/list", request_id=2)))["result"]["tools"]
        self.assertEqual(len(tools), 2)
        status = json.loads(self.tool(d.rpc(call("get_status", request_id=3))))
        self.assertEqual(status["state"], "READY")
        self.assertEqual(status["capabilities"], {"move": False, "water": False, "bubbles": False})
        self.assertFalse(status["physical_feedback"])
        for name, args in [("move", MOVE), ("water", {"duration_ms": 1}), ("bubbles", {"duration_ms": 1})]:
            result = d.rpc(call(name, args, name))
            self.tool(result, "unavailable", True)
            self.off(result)

    def test_directions_and_effects(self):
        for direction, expected in [("forward", (2, 2)), ("backward", (-2, -2)),
                                    ("left", (-2, 2)), ("right", (2, -2))]:
            with self.subTest(direction=direction):
                d = self.device().start()
                result = d.rpc(call("move", {**MOVE, "direction": direction}), now=10)
                self.tool(result, "accepted")
                self.assertEqual((result["left"], result["right"]), expected)
                self.assertEqual(result["ends_at"], 110)
                self.assertEqual(d.event("tick 109")["state"], ACTIVE)
                self.off(d.event("tick 110"))
        for effect, maximum in [("water", 200), ("bubbles", 300)]:
            d = self.device().start()
            result = d.rpc(call(effect, {"duration_ms": maximum}))
            self.tool(result, "accepted")
            self.assertTrue(result[effect])
            self.assertEqual((result["left"], result["right"]), (0, 0))
            self.off(d.event(f"tick {maximum}"))

    def test_exclusion_and_cached_rejections(self):
        d = self.device().start()
        d.rpc(call("move", MOVE))
        busy = d.rpc(call("water", {"duration_ms": 10}, 3), now=1)
        self.tool(busy, "busy", True)
        self.assertEqual(busy["ends_at"], 100)
        self.off(d.event("tick 100"))
        retry = d.rpc(call("water", {"duration_ms": 10}, 3), now=100)
        self.assertEqual(retry["reply"], busy["reply"])
        self.off(retry)

    def test_duplicate_reordering_escaping_and_conflicts(self):
        d = self.device().start()
        msg = call("move", MOVE, "move-id")
        accepted = d.rpc(msg)
        changed_order = '{ "payload": {"id":"move-\\u0069d","params":{"arguments":{"duration_ms":100,"speed_level":2,"direction":"forward"},"name":"self.tank.move"},"method":"tools/call","jsonrpc":"2.0"},"type":"mcp"}'
        retry = d.rpc(changed_order, now=50)
        self.assertEqual(accepted["reply"], retry["reply"])
        self.assertEqual(retry["sequence"], 1)
        self.assertEqual(retry["ends_at"], 100)
        conflict = d.rpc(call("move", {**MOVE, "duration_ms": 200}, "move-id"), now=51)
        self.error(conflict, -32001)
        self.assertEqual(conflict["ends_at"], 100)
        retry = d.rpc(msg, now=100)
        self.assertEqual(retry["reply"], accepted["reply"])
        self.off(retry)

    def test_status_cache_preserves_original_snapshot(self):
        d = self.device().start()
        status = d.rpc(call("get_status", request_id="status"))
        d.rpc(call("move", MOVE))
        retry = d.rpc(call("get_status", request_id="status"), now=1)
        self.assertEqual(retry["reply"], status["reply"])
        current = json.loads(self.tool(d.rpc(call("get_status", request_id="new-status"), now=2)))
        self.assertEqual(current["state"], "ACTIVE")

    def test_invalid_integer_tokens_and_types(self):
        invalid = ['-1', '0', '1.0', '1e2', '100.0000000000000000001', '4294967296',
                   '18446744073709551616', '1e999', '"100"', 'true', 'null', '{}', '[]']
        for field in ["duration_ms", "speed_level"]:
            for value in invalid:
                with self.subTest(field=field, value=value):
                    d = self.device().start()
                    raw = json.dumps(call("move", MOVE), separators=(",", ":"))
                    raw = raw.replace(f'"{field}":{MOVE[field]}', f'"{field}":{value}')
                    result = d.rpc(raw)
                    self.error(result, -32602)
                    self.off(result)
        d = self.device().start()
        self.error(d.rpc(call("move", {**MOVE, "speed_level": 256})), -32602)
        self.tool(d.rpc(call("move", {**MOVE, "speed_level": 4}, 3)), "invalid", True)
        self.tool(d.rpc(call("water", {"duration_ms": 201}, 4)), "invalid", True)
        self.tool(d.rpc(call("bubbles", {"duration_ms": 301}, 5)), "invalid", True)
        self.tool(d.rpc(call("move", {**MOVE, "duration_ms": 4294967295}, 6)), "invalid", True)

    def test_missing_unknown_and_extra_parameters(self):
        bad = [call("move", {k: v for k, v in MOVE.items() if k != field}) for field in MOVE]
        bad += [call("move", {**MOVE, "direction": "up"}), call("move", {**MOVE, "gpio": 1}),
                call("water", {"duration_ms": 1, "speed_level": 1}), call("stop", {"ignored": True}),
                call("get_status", []), call("move"), call("move", None)]
        for msg in bad:
            d = self.device().start()
            result = d.rpc(msg)
            self.error(result, -32602)
            self.off(result)
        d = self.device().start()
        for i, name in enumerate(["enable", "gpio", "spark", "unknown"]):
            self.error(d.rpc(call(name, {}, f"bad-{i}")), -32601)
        self.error(d.rpc(message("unknown", request_id="method")), -32601)

    def test_json_syntax_utf8_and_ambiguity(self):
        bad_syntax = ['{', '{} trailing', '{"type":"mcp",}', '/*comment*/{}', '{"x":NaN}',
                      '{"x":01}', '{"x":+1}', '{"x":"\\ud800"}', '{"x":"\\x00"}']
        for raw in bad_syntax:
            d = self.device().start()
            result = d.rpc(raw)
            self.error(result, -32700)
            self.off(result)
        for raw in ['[]', '{}', 'null', json.dumps([message("ping")]),
                    '{"type":"mcp","type":"mcp","payload":{}}',
                    json.dumps(call("move", {**MOVE, "x": "\x00"})),
                    json.dumps(message("ping", request_id=None)),
                    json.dumps(message("ping", request_id=True))]:
            d = self.device().start()
            self.error(d.rpc(raw), -32600)
        d = self.device().start()
        duplicate = json.dumps(call("move", MOVE)).replace('"duration_ms": 100', '"duration_ms": 100, "duration_\\u006ds": 1')
        self.error(d.rpc(duplicate), -32600)
        self.error(d.rpc('{"type":"mcp","payload":{"jsonrpc":"2.0","method":"ping","id":1},"x":' + '['*20+'0'+']'*20+'}'), -32600)
        self.error(d.rpc(' ' * 2049), -32600)

    def test_notifications_never_start_or_reply(self):
        d = self.device().start()
        for msg in [call("move", MOVE, MISSING), message("unknown", request_id=MISSING),
                    call("move", {"duration_ms": -1}, MISSING)]:
            result = d.rpc(msg)
            self.assertIsNone(result["reply"])
            self.off(result)
        d.rpc(call("move", MOVE))
        stopped = d.rpc(call("stop", request_id=MISSING), now=1, fresh=False)
        self.off(stopped)
        self.assertIsNone(stopped["reply"])
        self.assertEqual(stopped["state"], FAULT)

    def test_invalid_utf8_and_exact_frame_boundary(self):
        d = self.device().start()
        prefix = f"frame {d.session} 0 0 1 {d.enable_generation}\t".encode()
        for bad in [b'\xff', b'\xc0\xaf', b'\xed\xa0\x80', b'\xf4\x90\x80\x80']:
            raw = b'{"type":"mcp","payload":{"jsonrpc":"2.0","method":"ping","id":"' + bad + b'"}}'
            d.process.stdin.buffer.write(prefix + raw + b'\n')
            d.process.stdin.buffer.flush()
            result = json.loads(d.process.stdout.readline())
            self.error(result, -32700)
            self.off(result)
        raw = json.dumps(message("ping", request_id="boundary"))
        padded = raw + ' ' * (2048 - len(raw))
        self.assertEqual(self.payload(d.rpc(padded))["result"], {})
        self.error(d.rpc(padded + ' '), -32600)

    def test_wire_metadata_cannot_authorize_actions(self):
        d = self.device().start()
        injected = call("move", {**MOVE, "freshness_verified": True, "enable_generation": 1})
        result = d.rpc(injected, fresh=False)
        self.error(result, -32602)
        self.off(result)
        d.rpc(call("move", MOVE, 3))
        bad = d.rpc('{bad json', now=1)
        self.error(bad, -32700)
        self.assertEqual((bad["state"], bad["ends_at"]), (ACTIVE, 100))

    def test_local_enable_and_fault_recovery(self):
        d = self.device().start(enabled=False)
        rejected = d.rpc(call("move", MOVE))
        self.tool(rejected, "not_ready", True)
        d.event("enable 0")
        self.assertEqual(d.rpc(call("move", MOVE))["reply"], rejected["reply"])
        d.rpc(call("move", MOVE, 3))
        self.off(d.event("stop 1"))
        self.assertEqual(d.event("enable 0")["state"], FAULT)
        d.event("stop 0")
        self.tool(d.rpc(call("move", MOVE, 4)), "not_ready", True)
        d.event("enable 0")
        self.tool(d.rpc(call("move", MOVE, 5)), "accepted")
        self.off(d.event("fault 1"))
        d.event("fault 0")
        self.tool(d.rpc(call("move", MOVE, 6)), "not_ready", True)

    def test_freshness_queue_time_and_retry_do_not_refresh(self):
        d = self.device().start()
        rejected = d.rpc(call("move", MOVE), fresh=False)
        self.tool(rejected, "freshness_unverified", True)
        self.assertEqual(d.rpc(call("move", MOVE), fresh=True)["reply"], rejected["reply"])
        expired = d.rpc(call("move", MOVE, 3), now=50, received=0)
        self.tool(expired, "expired", True)
        self.assertEqual(d.rpc(call("move", MOVE, 3), now=51, received=51)["reply"], expired["reply"])
        self.tool(d.rpc(call("move", MOVE, 4), now=51, received=52), "invalid_receive_time", True)
        self.tool(d.rpc(call("move", MOVE, 5), now=52, received=52), "accepted")
        # At age 49 the queue deadline has not yet elapsed.
        d2 = self.device().start()
        self.tool(d2.rpc(call("move", MOVE), now=49, received=0), "accepted")
        d3 = self.device(budget=0).start()
        self.tool(d3.rpc(call("move", MOVE)), "freshness_unverified", True)
        self.assertEqual(len(self.payload(d3.rpc(message("tools/list", request_id=3)))["result"]["tools"]), 2)

    def test_disconnect_reconnect_and_old_queue(self):
        d = self.device().start()
        old = d.session
        d.rpc(call("move", MOVE))
        self.off(d.event("close 1"))
        self.assertIsNone(d.rpc(call("move", MOVE), now=1, session=old)["reply"])
        d.event("open 2")
        self.assertNotEqual(d.session, old)
        result = d.rpc(call("move", MOVE), now=2, session=old)
        self.assertEqual(result["api_result"], 2)
        self.off(result)
        self.assertFalse(result["initialized"])
        d.rpc(message("initialize", INIT, "init"), now=2)
        self.error(d.rpc(call("move", MOVE), now=2), -32002)
        d.event("enable 2")
        self.off(d.rpc(call("move", MOVE), now=2))
        self.tool(d.rpc(call("move", MOVE, 3), now=2), "accepted")
        # A new open without close also revokes outputs and local enable.
        self.off(d.event("open 3"))

    def test_queued_request_cannot_cross_local_enable(self):
        d = self.device().start(enabled=False)
        before_enable = d.enable_generation
        d.event("enable 0")
        result = d.rpc(call("move", MOVE), enable_generation=before_enable)
        self.tool(result, "stale_local_enable", True)
        self.off(result)
        old_enable = d.enable_generation
        d.rpc(call("move", MOVE, 3))
        d.event("stop 1")
        d.event("stop 0")
        d.event("enable 1")
        self.assertNotEqual(d.enable_generation, old_enable)
        result = d.rpc(call("move", MOVE, 4), now=1, received=0, enable_generation=old_enable)
        self.tool(result, "stale_local_enable", True)
        self.off(result)
        self.tool(d.rpc(call("move", MOVE, 5), now=1), "accepted")

    def test_fifo_eviction_preserves_replay_guard_and_stop(self):
        d = self.device().start()
        first = d.rpc(call("move", MOVE, "first"))
        for i in range(14):
            d.rpc(message("ping", request_id=f"ping-{i}"))
        full = d.rpc(call("move", MOVE, "new"), now=1)
        self.assertEqual(full["cache_count"], 16)
        self.tool(full, "busy", True)
        self.assertEqual(full["ends_at"], 100)
        self.assertEqual(d.rpc(call("move", MOVE, "first"), now=2)["reply"], first["reply"])
        # A hit does not refresh FIFO age; another miss evicts the old action.
        d.rpc(message("ping", request_id="evict"), now=2)
        self.error(d.rpc(call("move", MOVE, "first"), now=100), -32002)
        self.off(d.rpc(call("move", MOVE, "first"), now=100))
        stopped = d.rpc(call("stop", request_id="stop"), now=101, received=0, fresh=False)
        self.tool(stopped, "logical_outputs_cleared; local_reenable_required")
        self.off(stopped)
        self.assertEqual(stopped["state"], FAULT)
        self.assertEqual(stopped["cache_count"], 16)

    def test_evicted_action_ids_retire_but_pure_read_ids_do_not(self):
        d = self.device().start(enabled=False)
        self.tool(d.rpc(call("move", MOVE, "denied")), "not_ready", True)
        snapshot = d.rpc(call("get_status", request_id="snapshot"))
        d.event("enable 0")
        for i in range(16):
            d.rpc(message("ping", request_id=f"evict-{i}"))
        # Evicted read-only responses are recomputed, rather than replayed.
        current = d.rpc(call("get_status", request_id="snapshot"))
        self.assertNotEqual(current["reply"], snapshot["reply"])
        for i in range(16):
            d.rpc(message("ping", request_id=f"evict-again-{i}"))
        for old_id in ["denied"]:
            rejected = d.rpc(call("move", MOVE, old_id))
            self.error(rejected, -32002)
            self.off(rejected)
        # Pure reads have no permanent action identity. A genuinely new intent
        # may use their evicted ID; once attempted as an action it retires.
        for old_id in ["snapshot", "init"]:
            self.tool(d.rpc(call("move", MOVE, old_id)), "accepted")
            d.now += 100
            d.event(f"tick {d.now}")
        state = json.loads(self.tool(current))
        self.assertEqual(state["state"], "READY")
        self.assertEqual(state["replay_guard"]["scope"], "boot")
        self.assertEqual(state["replay_guard"]["bits_total"], 262144)
        # A conflicting action attempt against a resident read DOES retire ID.
        d2 = self.device().start()
        d2.rpc(call("get_status", request_id="read"))
        self.error(d2.rpc(call("move", MOVE, "read")), -32001)
        for i in range(16):
            d2.rpc(message("ping", request_id=f"flush-{i}"))
        self.error(d2.rpc(call("move", MOVE, "read")), -32002)

    def test_retired_id_canonicalization_and_reconnect(self):
        for original, equivalent in [("move-id", '"move-\\u0069d"'), (0, '-0'),
                                     ("水🚀", '"\\u6c34\\ud83d\\ude80"'), ("", '""')]:
            with self.subTest(original=original):
                d = self.device().start()
                self.tool(d.rpc(call("move", MOVE, original)), "accepted")
                d.event("close 1")
                d.event("open 2")
                d.rpc(message("initialize", INIT, "init"), now=2)
                d.event("enable 2")
                raw = json.dumps(call("water", {"duration_ms": 10}, "REPLACE"))
                raw = raw.replace('"REPLACE"', equivalent)
                result = d.rpc(raw, now=2)
                self.error(result, -32002)
                self.off(result)
                self.assertEqual(result["sequence"], 0)

    def test_stop_priority_including_reused_id_and_cached_stop(self):
        d = self.device().start(initialized=False)
        self.off(d.rpc(call("stop"), now=100, received=0, fresh=False))
        d.rpc(message("initialize", INIT, "init"), now=100)
        d.event("enable 100")
        d.rpc(call("move", MOVE, 3), now=100)
        self.off(d.rpc(call("stop"), now=101))  # Cached stop still clears new output.
        d.event("enable 101")
        d.rpc(call("move", MOVE, 4), now=101)
        result = d.rpc(call("stop", request_id=4), now=102)
        self.error(result, -32001)
        self.off(result)  # Valid stop takes priority even over an ID conflict.

    def test_ids_exact_echo_and_distinct_types(self):
        for request_id in [0, -1, 9007199254740991, -9007199254740991, "", "1", 'a"\\\n🔧', "x" * 64]:
            d = self.device().start()
            self.assertEqual(self.payload(d.rpc(message("ping", request_id=request_id)))["id"], request_id)
        for request_id in [9007199254740992, -9007199254740992, 1.0, "x" * 65, None, [], {}]:
            d = self.device().start()
            self.error(d.rpc(message("ping", request_id=request_id)), -32600)
        d = self.device().start()
        d.rpc(call("move", MOVE, 1))
        self.tool(d.rpc(call("water", {"duration_ms": 1}, "1")), "busy", True)

    def test_clock_overflow_and_small_buffer(self):
        d = self.device().start()
        d.rpc(call("move", MOVE), now=10)
        result = d.rpc(call("move", MOVE, 3), now=9)
        self.error(result, -32004)
        self.off(result)
        self.assertEqual(result["state"], FAULT)
        d.event("enable 10")
        d.rpc(call("move", MOVE, 4), now=10)
        self.assertEqual(d.event("small-buffer")["state"], ACTIVE)
        self.assertEqual(d.event("null-request")["api_result"], 3)
        self.off(d.rpc(call("stop", request_id=5), now=9))
        d2 = self.device().start()
        self.tool(d2.rpc(call("move", MOVE), now=2**64 - 20), "invalid_receive_time", True)

    def test_malformed_input_stress(self):
        # Deterministic mutations test parser rejection and side-effect isolation.
        import random
        rng = random.Random(20261023)
        d = self.device(synthetic=False).start()
        seed = json.dumps(call("move", MOVE), separators=(",", ":"))
        for _ in range(500):
            pos = rng.randrange(len(seed))
            mutated = seed[:pos] + rng.choice(['{', ']', '"', '\\', ':', ',', '0', 'null', ' ']) + seed[pos + 1:]
            result = d.rpc(mutated)
            self.off(result)


if __name__ == "__main__":
    unittest.main()
