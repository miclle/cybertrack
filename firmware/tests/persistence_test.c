#include "synthetic_proof.h"
#include "cybertrack/runtime.h"
#include "fake_store.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(EXIT_FAILURE); } } while (0)
#define WRAP(x) "{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\"," x "}}"
static const char initialize[] = WRAP("\"id\":\"init\",\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"persistence\",\"version\":\"1\"}}");
static const char prior[] = WRAP("\"id\":\"prior\",\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.move\",\"arguments\":{\"direction\":\"forward\",\"speed_level\":1,\"duration_ms\":5}}");
static const char next[] = WRAP("\"id\":\"next\",\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.water\",\"arguments\":{\"duration_ms\":5}}");
static const char status[] = WRAP("\"id\":\"status\",\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.get_status\"}");
static const char stop[] = WRAP("\"id\":\"stop\",\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.stop\"}");
static ct_test_store disk, baseline;
static ct_replay_store store;
static ct_protocol protocol;
static ct_controller control;
static ct_limits limits = {10,10,10,1};
static char reply[CT_RPC_REPLY_CAP];
static size_t cut_cases, boot_replays;

static void off(const ct_controller *c)
{
    CHECK(!c->output.left_level && !c->output.right_level && !c->output.water && !c->output.bubbles);
    CHECK(c->ends_at_ms == 0);
}
static void call(const char *frame)
{
    ct_rpc_delivery d = ct_test_delivery(&protocol, protocol.session, 0, control.enable_generation, true);
    CHECK(ct_protocol_handle(&protocol, frame, strlen(frame), d, 0, reply, sizeof(reply)) == CT_RPC_RESPONSE);
}
static void new_media(void)
{
    ct_test_store_blank(&disk);
    CHECK(ct_replay_store_load(&store, ct_test_store_io(&disk)) == CT_STORE_EMPTY);
    CHECK(ct_replay_store_provision(&store));
}
static bool boot(void)
{
    ct_test_store_power_cut(&disk);
    ct_store_state loaded = ct_replay_store_load(&store, ct_test_store_io(&disk));
    ct_init(&control, limits, 0); ct_protocol_init(&protocol, &control, 50);
    CHECK(ct_protocol_attach_store(&protocol, &store) == (loaded == CT_STORE_READY));
    off(&control); CHECK(control.session == 0 && !protocol.initialized && protocol.cache_count == 0);
    CHECK(ct_boot_complete(&control) == CT_OK);
    CHECK(ct_protocol_open(&protocol, 0));
    call(initialize); CHECK(protocol.initialized);
    CHECK(control.state != CT_READY); off(&control);
    CHECK(ct_local_enable(&control, 0) == CT_OK);
    return loaded == CT_STORE_READY;
}
static void setup_prior(void)
{
    new_media(); CHECK(boot()); call(prior); CHECK(strstr(reply, "accepted"));
    ct_stop(&control); CHECK(ct_local_enable(&control, 0) == CT_OK);
    baseline = disk;
}
static void reboot_and_binding(void)
{
    setup_prior(); uint64_t old = protocol.session;
    call(prior); CHECK(strstr(reply, "accepted")); off(&control); /* Resident original reply. */
    CHECK(boot() && protocol.session > old && protocol.sequence == 0);
    ct_rpc_delivery stale = ct_test_delivery(&protocol, old, 0, control.enable_generation, true);
    CHECK(ct_protocol_handle(&protocol, prior, strlen(prior), stale, 0, reply, sizeof(reply)) == CT_RPC_STALE_SESSION);
    call(prior); CHECK(strstr(reply, "-32002")); off(&control); ++boot_replays;
    CHECK(!ct_protocol_attach_store(&protocol, NULL) && !protocol.storage_fault);
    call(next); CHECK(strstr(reply, "accepted") && control.output.water);
    CHECK(boot()); call(next); CHECK(strstr(reply, "-32002")); off(&control); ++boot_replays;
    call(status); CHECK(strstr(reply, "persistent") && strstr(reply, "ready"));
    /* A failed first bind cannot be repaired by silently switching to RAM. */
    ct_init(&control, limits, 0); ct_protocol_init(&protocol, &control, 50);
    CHECK(!ct_protocol_attach_store(&protocol, NULL) && protocol.storage_fault);
    CHECK(!ct_protocol_attach_store(&protocol, &store));
}
static void write_cuts(void)
{
    const size_t boundaries[] = {0,1,3,4,7,8,15,16,23,24,25,4095,4096,16384,32767,32768,32791,32792,32795,32796,32799,32800};
    setup_prior();
    for (size_t operation = 1; operation <= 6; ++operation) {
        for (unsigned durable = 0; durable < 2; ++durable) {
            for (size_t i = 0; i < sizeof(boundaries)/sizeof(boundaries[0]); ++i) {
                disk = baseline; CHECK(boot());
                disk.fail_at = disk.calls + operation; disk.cut_bytes = boundaries[i]; disk.persist_partial = durable != 0;
                call(next);
                CHECK(strstr(reply, "-32005") && protocol.storage_fault && protocol.sequence == 0);
                off(&control);
                size_t calls = disk.calls;
                CHECK(ct_local_enable(&control, 0) == CT_OK);
                call(prior); CHECK(strstr(reply, "-32005")); off(&control);
                call(stop); CHECK(strstr(reply, "logical_outputs_cleared"));
                call(status); CHECK(strstr(reply, "fault"));
                CHECK(disk.calls == calls); /* Stop/diagnostics and locked retries do no I/O. */
                bool recovered = boot();
                call(prior); CHECK(strstr(reply, recovered ? "-32002" : "-32005")); off(&control);
                ++boot_replays;
                if (recovered && (operation == 6 || (durable &&
                    ((operation == 4 && boundaries[i] >= 4) || (operation == 5 && boundaries[i] == 32800))))) {
                    call(next); CHECK(strstr(reply, "-32002")); off(&control);
                    ++boot_replays;
                }
                ++cut_cases;
            }
        }
    }
}
static void bad_storage_and_open(void)
{
    for (unsigned mode = 0; mode < 5; ++mode) {
        setup_prior();
        if (mode == 0) ct_test_store_blank(&disk);
        if (mode == 1) disk.durable[0][24] ^= 1;
        if (mode == 2) memset(disk.durable[1], 0xff, CT_REPLAY_SLOT_BYTES);
        if (mode < 3) CHECK(!boot());
        else {
            ct_test_store_power_cut(&disk);
            CHECK(ct_replay_store_load(&store, ct_test_store_io(&disk)) == CT_STORE_READY);
            ct_init(&control, limits, 0); ct_protocol_init(&protocol, &control, 50);
            CHECK(ct_protocol_attach_store(&protocol, &store));
            CHECK(ct_boot_complete(&control) == CT_OK);
            disk.fail_at = disk.calls + (mode == 3 ? 1 : 5); disk.cut_bytes = CT_REPLAY_SLOT_BYTES; disk.persist_partial = true;
            CHECK(ct_protocol_open(&protocol, 0));
            call(initialize); CHECK(ct_local_enable(&control, 0) == CT_OK);
        }
        CHECK(protocol.storage_fault); call(prior); CHECK(strstr(reply, "-32005")); off(&control);
        call(status); CHECK(strstr(reply, "fault")); call(stop); CHECK(strstr(reply, "logical_outputs_cleared"));
        CHECK(ct_protocol_open(&protocol, 0)); call(initialize);
        CHECK(ct_local_enable(&control, 0) == CT_OK);
        call(next); CHECK(strstr(reply, "-32005")); off(&control);
    }
}
static void repeated_boots(void)
{
    new_media(); uint64_t last_session = 0;
    for (unsigned i = 0; i < 100; ++i) {
        CHECK(boot()); CHECK(protocol.session > last_session); last_session = protocol.session;
        char frame[256];
        snprintf(frame, sizeof(frame), WRAP("\"id\":\"boot-%u\",\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.water\",\"arguments\":{\"duration_ms\":1}}"), i);
        call(frame); CHECK(strstr(reply, "accepted"));
        CHECK(boot()); CHECK(protocol.session > last_session); last_session = protocol.session;
        call(frame); CHECK(strstr(reply, "-32002")); off(&control); ++boot_replays;
    }
}

static void rejected_intents_and_read_checkpoints(void)
{
    new_media(); CHECK(boot());
    call(WRAP("\"id\":\"next\",\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.water\",\"arguments\":{\"duration_ms\":0}}"));
    CHECK(strstr(reply, "-32602")); off(&control);
    CHECK(boot()); call(next); CHECK(strstr(reply, "-32002")); off(&control); ++boot_replays;
    size_t calls = disk.calls;
    uint32_t bits = protocol.replay_bits_set;
    call(status); CHECK(strstr(reply, "persistent"));
    call(stop); CHECK(disk.calls == calls && protocol.replay_bits_set == bits);
    /* Reads/stop consume neither writes nor permanent replay bits. */
    CHECK(ct_local_enable(&control, 0) == CT_OK);
    call(prior); CHECK(strstr(reply, "accepted")); /* Pure read/stop IDs do not consume persistent capacity. */
    CHECK(boot());
    call(WRAP("\"id\":\"status\",\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.water\",\"arguments\":{\"duration_ms\":1}}"));
    CHECK(strstr(reply, "accepted")); /* New intent may use a pure read's old ID. */
    CHECK(boot());
    call(WRAP("\"id\":\"status\",\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.water\",\"arguments\":{\"duration_ms\":1}}"));
    CHECK(strstr(reply, "-32002")); off(&control); ++boot_replays;
}

/* Runtime integration: I/O failure/latency/stop while persisting must not reach
 * a physical-output callback. Loss after that callback must still retire ID. */
static ct_runtime runtime;
static ct_runtime_response response;
static struct { uint64_t now; ct_local_inputs inputs; ct_output output; unsigned writes; bool fail_output, stop_on_sync; unsigned sync_delay; } board;
static ct_replay_io raw_io;
static bool board_off(void *ctx) { (void)ctx; board.output = (ct_output){0}; return true; }
static bool board_ok(void *ctx) { (void)ctx; return true; }
static bool board_clock(void *ctx, uint64_t *now) { (void)ctx; *now = board.now; return true; }
static bool board_inputs(void *ctx, ct_local_inputs *out) { (void)ctx; *out = board.inputs; return true; }
static bool board_output(void *ctx, const ct_output *out)
{
    (void)ctx; CHECK(store.state == CT_STORE_READY && !memcmp(store.filter, protocol.replay_filter, CT_REPLAY_BYTES));
    CHECK(!memcmp(disk.durable, disk.pending, sizeof(disk.durable)));
    ++board.writes; board.output = *out; return !board.fail_output;
}
static bool timed_sync(void *ctx)
{
    board.now += board.sync_delay;
    if (board.stop_on_sync) board.inputs.stop = true;
    return raw_io.sync(ctx);
}
static bool step(ct_event_kind kind, const char *text)
{
    ct_runtime_event event = {0}; event.kind = kind; event.frame = text;
    if (text) event.length = strlen(text);
    event.delivery = ct_test_delivery(&protocol, protocol.session, board.now, runtime.control.enable_generation, true);
    return ct_runtime_step(&runtime, &event, &response);
}
static void runtime_ordering(void)
{
    for (unsigned mode = 0; mode < 6; ++mode) {
        new_media(); memset(&board, 0, sizeof(board));
        ct_board_io io = {NULL, board_off, board_ok, board_clock, board_inputs, board_output, board_ok};
        CHECK(ct_runtime_init(&runtime, &protocol, io, limits, mode == 5 ? 5 : 50, 20));
        raw_io = ct_test_store_io(&disk); ct_replay_io timed = raw_io; timed.sync = timed_sync;
        CHECK(ct_replay_store_load(&store, timed) == CT_STORE_READY);
        CHECK(ct_protocol_attach_store(&protocol, &store));
        CHECK(step(CT_EVENT_CONNECT, NULL)); CHECK(step(CT_EVENT_MESSAGE, initialize));
        board.inputs.enable_button = true; CHECK(step(CT_EVENT_IDLE, NULL));
        board.inputs.enable_button = false; CHECK(step(CT_EVENT_IDLE, NULL));
        if (mode == 0) disk.fail_at = disk.calls + 2;
        if (mode == 1) board.sync_delay = 11;
        if (mode == 2) board.stop_on_sync = true;
        if (mode == 3) board.fail_output = true;
        if (mode == 5) { board.now = 4; board.sync_delay = 1; }
        bool ok = step(CT_EVENT_MESSAGE, prior);
        CHECK(ok == (mode == 0 || mode == 2 || mode == 4));
        CHECK(board.writes == (mode == 3 || mode == 4 ? 1u : 0u));
        if (mode == 5) CHECK(runtime.faults & CT_RUNTIME_FRESHNESS);
        if (mode != 4) CHECK(!board.output.left_level);
        if (!ok) CHECK(!response.reply[0]);
        /* Simulate reset after the storage attempt, output attempt or lost reply. */
        bool recovered = boot(); call(prior);
        if (mode == 0 && recovered) {
            /* Save never succeeded, so execution on a later explicit retry is
             * allowed; it has not executed on the pre-cut board. */
            CHECK(strstr(reply, "accepted") || strstr(reply, "-32002"));
        } else {
            CHECK(strstr(reply, recovered ? "-32002" : "-32005")); off(&control);
        }
        ++boot_replays;
    }
}
int main(void)
{
    reboot_and_binding(); write_cuts(); bad_storage_and_open(); repeated_boots();
    rejected_intents_and_read_checkpoints(); runtime_ordering();
    printf("PASS: 6 persistence groups; action_cut_cases=%zu; boot_replay_checks=%zu; repeated_resets=200; protocol_bytes=%zu\n", cut_cases, boot_replays, sizeof(protocol));
    return EXIT_SUCCESS;
}
