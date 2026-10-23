#include "cybertrack/protocol.h"
#include "fake_store.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%d: %s; reply=%s\n", __LINE__, #x, reply); exit(1); } } while (0)
#define WRAP(x) "{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\"," x "}}"
static const char initialize[] = WRAP("\"id\":\"init\",\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"migration\",\"version\":\"1\"}}");
static ct_test_store source_disk, target_disk, saved_disk;
static ct_replay_store source, target, stale;
static ct_protocol protocol;
static ct_controller control;
static char reply[CT_RPC_REPLY_CAP];
static size_t cuts, replay_checks;
static unsigned char snapshot[CT_REPLAY_BYTES];
static void off(void) { CHECK(!control.output.water && !control.output.left_level && !control.ends_at_ms); }
static void handle(const char *frame, uint64_t intent)
{
    ct_action_proof proof = {0};
    if (!protocol.storage_fault) CHECK(ct_protocol_issue_window(&protocol, 0, &proof));
    proof.intent = intent;
    ct_rpc_delivery delivery = {protocol.session, 0, control.enable_generation, proof};
    CHECK(ct_protocol_handle(&protocol, frame, strlen(frame), delivery, 0, reply, sizeof(reply)) == CT_RPC_RESPONSE);
}
static void boot(ct_replay_store *s)
{
    ct_init(&control, (ct_limits){10,10,10,1}, 0); ct_protocol_init(&protocol, &control, 50);
    CHECK(ct_protocol_attach_store(&protocol, s) == (s->state == CT_STORE_READY));
    CHECK(ct_boot_complete(&control) == CT_OK && ct_protocol_open(&protocol, 0));
    handle(initialize, 0); CHECK(ct_local_enable(&control, 0) == CT_OK); off();
}
static void action(unsigned rpc, uint64_t intent, const char *expected)
{
    char frame[256];
    snprintf(frame, sizeof(frame), WRAP("\"id\":%u,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.water\",\"arguments\":{\"duration_ms\":1}}"), rpc);
    handle(frame, intent); CHECK(strstr(reply, expected));
    if (!strcmp(expected, "accepted")) CHECK(control.output.water);
    else { off(); ++replay_checks; }
}
static void blank_target(void)
{
    ct_test_store_blank(&target_disk);
    CHECK(ct_replay_store_load(&target, ct_test_store_io(&target_disk)) == CT_STORE_EMPTY);
}
static void prepare(void)
{
    ct_test_store_blank(&source_disk);
    CHECK(ct_replay_store_load(&source, ct_test_store_io(&source_disk)) == CT_STORE_EMPTY);
    CHECK(ct_replay_store_provision(&source)); boot(&source);
    action(1, 10, "accepted"); ct_stop(&control); ct_protocol_close(&protocol, 0); off();
    /* Retire the source protocol owner. Simulate legacy read bits: provenance
     * cannot be inferred, so ALL of these bits must survive upgrade/migration. */
    memcpy(snapshot, source.filter, sizeof(snapshot)); snapshot[123] |= 0x55;
    CHECK(ct_replay_store_save(&source, snapshot, source.session));
    saved_disk = source_disk;
    blank_target();
}
static void source_unchanged(void)
{
    CHECK(!memcmp(source_disk.pending, saved_disk.pending, sizeof(source_disk.pending)));
    CHECK(!memcmp(source_disk.durable, saved_disk.durable, sizeof(source_disk.durable)));
    CHECK(!memcmp(source.filter, snapshot, sizeof(snapshot)));
}
static void lossless_and_cleanup(void)
{
    prepare(); uint64_t revision = source.revision, session = source.session;
    CHECK(ct_replay_store_migrate(&source, &target)); source_unchanged();
    CHECK(target.state == CT_STORE_READY && target.revision == revision + 2 && target.session == session);
    CHECK(!memcmp(target.filter, snapshot, sizeof(snapshot)));
    ct_test_store_power_cut(&target_disk);
    CHECK(ct_replay_store_load(&target, ct_test_store_io(&target_disk)) == CT_STORE_READY);
    boot(&target); CHECK(protocol.session > session);
    action(2, 10, "-32002"); /* New RPC ID, old intent, current window. */
    action(1, 11, "-32002"); /* New intent cannot reuse an old action RPC ID. */
    action(3, 12, "accepted"); ct_stop(&control); ct_protocol_close(&protocol, 0);
    ct_test_store_power_cut(&target_disk);
    CHECK(ct_replay_store_load(&target, ct_test_store_io(&target_disk)) == CT_STORE_READY);
    boot(&target); action(4, 12, "-32002");
    ct_protocol_close(&protocol, 0);
    /* Attempted cleanup cannot write a reduced set, even after a migration. */
    memset(snapshot, 0, sizeof(snapshot));
    CHECK(!ct_replay_store_save(&target, snapshot, target.session));
    CHECK(target.state == CT_STORE_FAULT);
    ct_test_store_power_cut(&target_disk);
    CHECK(ct_replay_store_load(&target, ct_test_store_io(&target_disk)) == CT_STORE_READY);
    boot(&target); action(5, 10, "-32002"); action(6, 12, "-32002");
}
static void interrupted_copy(void)
{
    prepare();
    const size_t boundaries[] = {0,1,4,24,32796,32800};
    for (unsigned op = 1; op <= 14; ++op) for (unsigned durable = 0; durable < 2; ++durable)
        for (size_t i = 0; i < sizeof(boundaries)/sizeof(boundaries[0]); ++i) {
            blank_target();
            target_disk.fail_at = target_disk.calls + op;
            target_disk.cut_bytes = boundaries[i]; target_disk.persist_partial = durable != 0;
            CHECK(!ct_replay_store_migrate(&source, &target) && target.state == CT_STORE_FAULT);
            source_unchanged();
            ct_test_store_power_cut(&target_disk);
            ct_store_state state = ct_replay_store_load(&target, ct_test_store_io(&target_disk));
            if (state == CT_STORE_READY) {
                CHECK(!memcmp(target.filter, snapshot, sizeof(snapshot)));
                CHECK(target.session == source.session && target.revision == source.revision + 2);
            }
            /* EMPTY is not automatic permission to provision or run. The
             * source remains intact; this only tests fail-closed target use. */
            boot(&target);
            action(2, 10, state == CT_STORE_READY ? "-32002" : "-32005");
            action(1, 99, state == CT_STORE_READY ? "-32002" : "-32005");
            ++cuts;
        }
}
static void repeated_copy(void)
{
    prepare();
    for (unsigned i = 0; i < 50; ++i) {
        blank_target();
        uint64_t session = source.session;
        CHECK(ct_replay_store_migrate(&source, &target));
        CHECK(!memcmp(target.filter, source.filter, CT_REPLAY_BYTES));
        boot(&target); CHECK(protocol.session > session);
        action(1000 + i, 10, "-32002");
        action(2000 + i, 100 + i, "accepted");
        ct_stop(&control); ct_protocol_close(&protocol, 0);
        /* Test-only backend selection AFTER successful copy. Retired media is
         * never used as a fallback; model the selected target as next source. */
        source_disk = target_disk;
        ct_test_store_power_cut(&source_disk);
        CHECK(ct_replay_store_load(&source, ct_test_store_io(&source_disk)) == CT_STORE_READY);
        boot(&source);
        action(3000 + i, 100 + i, "-32002");
        ct_protocol_close(&protocol, 0);
    }
}

static void invalid_sources_and_targets(void)
{
    prepare(); CHECK(!ct_replay_store_migrate(NULL, &target));
    CHECK(!ct_replay_store_migrate(&source, NULL));
    CHECK(!ct_replay_store_migrate(&source, &source));
    CHECK(ct_replay_store_provision(&target));
    size_t calls = target_disk.calls;
    CHECK(!ct_replay_store_migrate(&source, &target) && calls == target_disk.calls);
    blank_target(); target.io.context = source.io.context;
    CHECK(!ct_replay_store_migrate(&source, &target));
    for (unsigned slot = 0; slot < 2; ++slot) {
        blank_target(); source_disk.fail_at = source_disk.calls + slot + 1;
        calls = target_disk.calls;
        CHECK(!ct_replay_store_migrate(&source, &target));
        CHECK(calls == target_disk.calls); source_unchanged(); source_disk.fail_at = 0;
    }
    /* Destination changed since EMPTY load: never erase it. */
    blank_target(); target_disk.pending[0][0] = 0; calls = target_disk.calls;
    CHECK(!ct_replay_store_migrate(&source, &target));
    CHECK(target_disk.calls == calls + 1 && target_disk.pending[0][0] == 0);
    /* Source advanced after the caller's snapshot: do not copy stale history. */
    blank_target(); stale = source; snapshot[100] |= 1;
    CHECK(ct_replay_store_save(&source, snapshot, source.session)); calls = target_disk.calls;
    CHECK(!ct_replay_store_migrate(&stale, &target) && calls == target_disk.calls);
    blank_target(); source.revision = UINT64_MAX - 1; calls = target_disk.calls;
    CHECK(!ct_replay_store_migrate(&source, &target) && calls == target_disk.calls);
}
int main(void)
{
    lossless_and_cleanup(); interrupted_copy(); repeated_copy(); invalid_sources_and_targets();
    printf("PASS: 4 migration groups; repeated_migrations=50; cut_cases=%zu; replay_checks=%zu; source_erased=0; lost_bits=0\n", cuts, replay_checks);
    return 0;
}
