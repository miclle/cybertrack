#include "cybertrack/runtime.h"
#include "fake_anchor.h"
#include "fake_store.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%d: %s; reply=%s\n", __LINE__, #x, reply); exit(1); } } while (0)
#define WRAP(x) "{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\"," x "}}"
static const char initialize[] = WRAP("\"id\":\"init\",\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"switch\",\"version\":\"1\"}}");
static const char stop[] = WRAP("\"id\":\"stop\",\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.stop\"}");
static const char status[] = WRAP("\"id\":\"status\",\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.get_status\"}");
static ct_test_store disks[2], old_disk;
static ct_replay_store stores[2], stale;
static ct_test_anchor anchor;
static ct_controller control;
static ct_protocol protocol;
static char reply[CT_RPC_REPLY_CAP];
static size_t rejections, switch_cuts, action_cuts, open_cuts, runtime_cases, cycles;
static ct_limits limits = {100,100,100,1};
static void off(void)
{
    CHECK(!control.output.water && !control.output.bubbles && !control.output.left_level &&
          !control.output.right_level && !control.ends_at_ms);
}
static ct_action_proof proof(uint64_t intent)
{
    ct_action_proof out = {0};
    if (!protocol.storage_fault) CHECK(ct_protocol_issue_window(&protocol, 0, &out));
    out.intent = intent; return out;
}
static void handle(const char *frame, ct_action_proof origin)
{
    ct_rpc_delivery delivery = {protocol.session, 0, control.enable_generation, origin};
    CHECK(ct_protocol_handle(&protocol, frame, strlen(frame), delivery, 0, reply, sizeof(reply)) == CT_RPC_RESPONSE);
}
static void frame_action(char *frame, size_t cap, unsigned rpc)
{
    snprintf(frame, cap, WRAP("\"id\":%u,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.water\",\"arguments\":{\"duration_ms\":50}}"), rpc);
}
static void action(unsigned rpc, uint64_t intent, const char *expected)
{
    char frame[256]; frame_action(frame, sizeof(frame), rpc);
    handle(frame, proof(intent)); CHECK(strstr(reply, expected));
    if (!strcmp(expected, "accepted")) CHECK(control.output.water);
    else { off(); ++rejections; }
}
static void attach(ct_replay_store *s, bool ready)
{
    ct_init(&control, limits, 0); ct_protocol_init(&protocol, &control, 50);
    CHECK(ct_protocol_attach_guarded_store(&protocol, s) == ready);
    CHECK(ct_boot_complete(&control) == CT_OK); off();
}
static void connect(void)
{
    CHECK(ct_protocol_open(&protocol, 0)); handle(initialize, (ct_action_proof){0});
    CHECK(protocol.initialized); off(); CHECK(ct_local_enable(&control, 0) == CT_OK);
}
static bool boot(unsigned i)
{
    ct_test_store_power_cut(&disks[i]); ct_test_anchor_power_cut(&anchor);
    (void)ct_replay_store_load(&stores[i], ct_test_store_io(&disks[i]));
    bool ready = ct_replay_store_bind(&stores[i], ct_test_anchor_io(&anchor), i + 1);
    attach(&stores[i], ready); connect(); return ready;
}
static void blank_target(unsigned i)
{
    ct_test_store_blank(&disks[i]);
    CHECK(ct_replay_store_load(&stores[i], ct_test_store_io(&disks[i])) == CT_STORE_EMPTY);
}
static void prepare(void)
{
    memset(&anchor, 0, sizeof(anchor)); blank_target(0); blank_target(1);
    CHECK(ct_replay_store_provision(&stores[0]));
    CHECK(ct_replay_store_enroll(&stores[0], ct_test_anchor_io(&anchor), 1));
    attach(&stores[0], true); connect(); action(1, 10, "accepted");
    ct_protocol_close(&protocol, 0); off(); old_disk = disks[0]; stale = stores[0];
}
static void normal_and_rollback(void)
{
    prepare(); uint64_t session = stores[0].session;
    CHECK(ct_replay_store_switch(&stores[0], &stores[1], 2)); CHECK(boot(1));
    CHECK(protocol.session > session); action(2, 10, "-32002"); action(1, 11, "-32002");
    old_disk = disks[1]; action(3, 12, "accepted"); /* Lose response, reset. */
    CHECK(boot(1)); action(4, 12, "-32002");
    CHECK(!boot(0)); action(5, 12, "-32005");
    disks[1] = old_disk; CHECK(!boot(1)); action(6, 12, "-32005");
    handle(status, (ct_action_proof){0}); CHECK(strstr(reply, "fault"));
    size_t calls = anchor.calls; handle(stop, (ct_action_proof){0});
    CHECK(strstr(reply, "logical_outputs_cleared") && anchor.calls == calls); off();
    /* New production entry cannot accidentally accept a plain loaded store. */
    prepare(); ct_protocol_close(&protocol, 0);
    CHECK(ct_replay_store_load(&stores[0], ct_test_store_io(&disks[0])) == CT_STORE_READY);
    attach(&stores[0], false); CHECK(!ct_protocol_attach_store(&protocol, &stores[0]));
    connect(); action(9, 99, "-32005");
    prepare(); CHECK(ct_replay_store_switch(&stores[0], &stores[1], 2));
    attach(&stale, false); connect(); action(9, 99, "-32005");
}
static void migration_failures(void)
{
    const size_t boundaries[] = {0,1,4,24,32796,32800};
    for (unsigned op = 1; op <= 14; ++op) for (unsigned durable = 0; durable < 2; ++durable)
        for (size_t b = 0; b < sizeof(boundaries)/sizeof(boundaries[0]); ++b) {
            prepare(); disks[1].fail_at = disks[1].calls + op;
            disks[1].cut_bytes = boundaries[b]; disks[1].persist_partial = durable != 0;
            CHECK(!ct_replay_store_switch(&stores[0], &stores[1], 2));
            CHECK(!boot(1)); action(2, 10, "-32005");
            CHECK(boot(0)); action(2, 10, "-32002"); action(1, 20, "-32002"); ++switch_cuts;
        }
    for (unsigned op = 1; op <= 3; ++op) for (unsigned commit = 0; commit < 2; ++commit) {
        prepare(); anchor.fail_at = anchor.calls + op; anchor.commit_on_failure = commit != 0;
        CHECK(!ct_replay_store_switch(&stores[0], &stores[1], 2));
        unsigned selected = (unsigned)anchor.durable.backend_id - 1;
        CHECK(!boot(1-selected)); action(2, 10, "-32005");
        CHECK(boot(selected)); action(2, 10, "-32002"); action(1, 20, "-32002"); ++switch_cuts;
    }
    for (unsigned op = 1; op <= 2; ++op) {
        prepare(); disks[0].fail_at = disks[0].calls + op;
        CHECK(!ct_replay_store_switch(&stores[0], &stores[1], 2));
        CHECK(boot(0)); action(2, 10, "-32002"); ++switch_cuts;
    }
}
static void action_and_open_failures(void)
{
    for (unsigned op = 1; op <= 4; ++op) for (unsigned commit = 0; commit < 2; ++commit) {
        prepare(); CHECK(boot(0)); action(2, 20, "accepted");
        anchor.fail_at = anchor.calls + op; anchor.commit_on_failure = commit != 0;
        action(3, 30, "-32005"); CHECK(protocol.storage_fault);
        CHECK(ct_local_enable(&control, 0) == CT_OK); action(4, 30, "-32005");
        size_t calls = anchor.calls; handle(stop, (ct_action_proof){0}); handle(status, (ct_action_proof){0});
        CHECK(calls == anchor.calls && strstr(reply, "fault"));
        bool recovered = boot(0); action(5, 20, recovered ? "-32002" : "-32005");
        if (op >= 3 || (op == 2 && commit)) action(6, 30, recovered ? "-32002" : "-32005");
        ++action_cuts;
        prepare(); attach(&stores[0], true);
        anchor.fail_at = anchor.calls + op; anchor.commit_on_failure = commit != 0;
        connect(); CHECK(protocol.storage_fault); action(2, 20, "-32005");
        recovered = boot(0); action(3, 10, recovered ? "-32002" : "-32005"); ++open_cuts;
    }
}
static void repeated_switches(void)
{
    prepare(); unsigned selected = 0; uint64_t session = stores[0].session;
    for (unsigned i = 0; i < 50; ++i) {
        unsigned destination = 1 - selected;
        /* Test harness supplies genuinely blank independent replacement media;
         * no production erase/repair API is implied by resetting a fake disk. */
        blank_target(destination);
        CHECK(ct_replay_store_switch(&stores[selected], &stores[destination], destination + 1));
        CHECK(!boot(selected)); action(4000 + i, 10, "-32005");
        CHECK(boot(destination)); CHECK(protocol.session > session); session = protocol.session;
        action(1000 + i, 10, "-32002"); action(2000 + i, 100 + i, "accepted");
        CHECK(boot(destination)); action(3000 + i, 100 + i, "-32002");
        ct_protocol_close(&protocol, 0); off(); selected = destination; ++cycles;
    }
}

static ct_runtime runtime;
static ct_runtime_response response;
static ct_replay_anchor_io raw_anchor;
static struct { uint64_t now; ct_local_inputs inputs; ct_output output; unsigned writes, delay; bool stop, fail_output; } board;
static bool board_off(void *ctx) { (void)ctx; board.output = (ct_output){0}; return true; }
static bool board_ok(void *ctx) { (void)ctx; return true; }
static bool board_clock(void *ctx, uint64_t *now) { (void)ctx; *now = board.now; return true; }
static bool board_inputs(void *ctx, ct_local_inputs *out) { (void)ctx; *out = board.inputs; return true; }
static bool board_output(void *ctx, const ct_output *out)
{
    (void)ctx; CHECK(anchor.durable.revision == stores[0].revision);
    CHECK(anchor.durable.session == protocol.session && anchor.durable.backend_id == 1);
    CHECK(!memcmp(stores[0].filter, protocol.replay_filter, CT_REPLAY_BYTES));
    CHECK(!memcmp(disks[0].durable, disks[0].pending, sizeof(disks[0].durable)));
    ++board.writes; board.output = *out; return !board.fail_output;
}
static bool timed_replace(void *ctx, const ct_replay_anchor_record *before, const ct_replay_anchor_record *after)
{
    board.now += board.delay; if (board.stop) board.inputs.stop = true;
    return raw_anchor.replace(ctx, before, after);
}
static bool step(ct_event_kind kind, const char *frame)
{
    ct_runtime_event event = {0}; event.kind = kind; event.frame = frame;
    if (frame) event.length = strlen(frame);
    ct_action_proof origin = {0};
    if (kind == CT_EVENT_MESSAGE && !strcmp(frame, initialize)) origin.intent = 0;
    else if (kind == CT_EVENT_MESSAGE) {
        CHECK(ct_protocol_issue_window(&protocol, board.now, &origin)); origin.intent = 90;
    }
    event.delivery = (ct_rpc_delivery){protocol.session, board.now, runtime.control.enable_generation, origin};
    return ct_runtime_step(&runtime, &event, &response);
}
static void runtime_ordering(void)
{
    for (unsigned mode = 0; mode < 6; ++mode) {
        prepare(); memset(&board, 0, sizeof(board)); raw_anchor = ct_test_anchor_io(&anchor);
        stores[0].anchor.replace = timed_replace;
        ct_board_io io = {NULL, board_off, board_ok, board_clock, board_inputs, board_output, board_ok};
        CHECK(ct_runtime_init(&runtime, &protocol, io, limits, mode == 5 ? 5 : 50, 20));
        CHECK(ct_protocol_attach_guarded_store(&protocol, &stores[0]));
        CHECK(step(CT_EVENT_CONNECT, NULL)); CHECK(step(CT_EVENT_MESSAGE, initialize));
        board.inputs.enable_button = true; CHECK(step(CT_EVENT_IDLE, NULL));
        board.inputs.enable_button = false; CHECK(step(CT_EVENT_IDLE, NULL));
        if (mode == 0) { anchor.fail_at = anchor.calls + 2; anchor.commit_on_failure = true; }
        if (mode == 1) board.delay = 21;
        if (mode == 2) board.stop = true;
        if (mode == 3) board.fail_output = true;
        if (mode == 5) board.delay = 5;
        char frame[256]; frame_action(frame, sizeof(frame), 9);
        bool ok = step(CT_EVENT_MESSAGE, frame);
        CHECK(ok == (mode == 0 || mode == 2 || mode == 4));
        CHECK(board.writes == (mode == 3 || mode == 4 ? 1u : 0u));
        if (mode == 5) CHECK(runtime.faults & CT_RUNTIME_FRESHNESS);
        if (mode != 4) CHECK(!board.output.water);
        if (!ok) CHECK(!response.reply[0]);
        bool recovered = boot(0); CHECK(recovered == (mode != 0));
        action(10, 90, recovered ? "-32002" : "-32005"); ++runtime_cases;
    }
}
int main(void)
{
    normal_and_rollback(); migration_failures(); action_and_open_failures(); repeated_switches(); runtime_ordering();
    printf("PASS: 5 switch integration groups; switch_cuts=%zu; action_anchor_cuts=%zu; open_anchor_cuts=%zu; repeated_switches=%zu; runtime_cases=%zu; rejection_checks=%zu; unexpected_replays=0\n",
           switch_cuts, action_cuts, open_cuts, cycles, runtime_cases, rejections);
    return 0;
}
