#include "cybertrack/protocol.h"
#include "fake_anchor.h"
#include "fake_store.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%d: %s; reply=%s\n", __LINE__, #x, reply); exit(1); } } while (0)
#define WRAP(x) "{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\"," x "}}"
static const char initialize[] = WRAP("\"id\":\"init\",\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"recovery\",\"version\":\"1\"}}");
static const char stop[] = WRAP("\"id\":\"stop\",\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.stop\"}");
static const char status[] = WRAP("\"id\":\"status\",\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.get_status\"}");
static ct_test_store disks[2], older_image;
static ct_replay_store stores[2];
static ct_test_anchor anchor;
static ct_protocol protocol;
static ct_controller control;
static char reply[CT_RPC_REPLY_CAP];
static size_t rejections, recovery_cuts, write_cuts, anchor_cuts, cycles;
static void off(void)
{
    CHECK(!control.output.water && !control.output.bubbles && !control.output.left_level &&
          !control.output.right_level && !control.ends_at_ms);
}
static void handle(const char *frame, uint64_t intent)
{
    ct_action_proof proof = {0};
    if (!protocol.storage_fault) CHECK(ct_protocol_issue_window(&protocol, 0, &proof));
    proof.intent = intent;
    ct_rpc_delivery delivery = {protocol.session, 0, control.enable_generation, proof};
    CHECK(ct_protocol_handle(&protocol, frame, strlen(frame), delivery, 0, reply, sizeof(reply)) == CT_RPC_RESPONSE);
}
static void action(unsigned rpc, uint64_t intent, const char *expected)
{
    char frame[256];
    snprintf(frame, sizeof(frame), WRAP("\"id\":%u,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.water\",\"arguments\":{\"duration_ms\":1}}"), rpc);
    handle(frame, intent);
    if (expected) CHECK(strstr(reply, expected)); else CHECK(!strstr(reply, "accepted"));
    if (expected && !strcmp(expected, "accepted")) CHECK(control.output.water);
    else { off(); ++rejections; }
}
static void attach(ct_replay_store *s, bool ready)
{
    ct_init(&control, (ct_limits){10,10,10,1}, 0); ct_protocol_init(&protocol, &control, 50);
    CHECK(ct_protocol_attach_guarded_store(&protocol, s) == ready);
    CHECK(ct_boot_complete(&control) == CT_OK && ct_protocol_open(&protocol, 0));
    handle(initialize, 0); CHECK(protocol.initialized); off();
}
static bool reload(unsigned i)
{
    ct_test_store_power_cut(&disks[i]); ct_test_anchor_power_cut(&anchor);
    (void)ct_replay_store_load(&stores[i], ct_test_store_io(&disks[i]));
    return ct_replay_store_bind(&stores[i], ct_test_anchor_io(&anchor), i + 1);
}
static bool boot(unsigned i)
{
    bool ready = reload(i); attach(&stores[i], ready); return ready;
}
static void enable(void) { CHECK(ct_local_enable(&control, 0) == CT_OK); }
static void blank(unsigned i)
{
    ct_test_store_blank(&disks[i]);
    CHECK(ct_replay_store_load(&stores[i], ct_test_store_io(&disks[i])) == CT_STORE_EMPTY);
}
static void damage_companion(unsigned i)
{
    CHECK(stores[i].state == CT_STORE_READY);
    disks[i].durable[1 - stores[i].slot][0] ^= 1;
    CHECK(!reload(i));
}
static void prepare(bool damage)
{
    memset(&anchor, 0, sizeof(anchor)); blank(0); blank(1);
    CHECK(ct_replay_store_provision(&stores[0]));
    CHECK(ct_replay_store_enroll(&stores[0], ct_test_anchor_io(&anchor), 1));
    attach(&stores[0], true); enable(); action(1, 10, "accepted"); ct_stop(&control);
    older_image = disks[0]; enable(); action(2, 20, "accepted");
    ct_protocol_close(&protocol, 0); off();
    if (damage) damage_companion(0);
}
static ct_replay_recovery_result recover(unsigned source)
{
    return ct_replay_store_recover(&stores[source], ct_test_anchor_io(&anchor), source + 1,
                                  &stores[1-source], 2 - source);
}
static void prior_actions_rejected(unsigned rpc)
{
    action(rpc, 10, "-32002"); action(rpc + 1, 20, "-32002"); action(2, rpc + 100, "-32002");
}
static void local_gates_and_rollback(void)
{
    prepare(true); uint64_t session = anchor.durable.session;
    CHECK(recover(0) == CT_RECOVERY_OK); off();
    CHECK(boot(1) && protocol.session > session);
    CHECK(!control.enable_generation && !protocol.accepted_sequence);
    action(90, 90, NULL); /* Recovery cannot auto-enable a fresh action. */
    enable(); prior_actions_rejected(3); action(6, 30, "accepted");
    CHECK(boot(1)); enable(); action(7, 30, "-32002"); /* Lost response stays retired. */
    CHECK(!boot(0)); enable(); action(8, 30, "-32005");
    blank(1); CHECK(recover(0) == CT_RECOVERY_WRONG_BACKEND); /* Even maintenance cannot choose old source. */
    prepare(false); disks[0] = older_image; CHECK(!boot(0));
    CHECK(recover(0) == CT_RECOVERY_HISTORY_UNAVAILABLE);
    attach(&stores[1], false); enable(); action(4, 20, "-32005");
    size_t calls = anchor.calls + disks[0].calls + disks[1].calls;
    handle(stop, 0); CHECK(strstr(reply, "logical_outputs_cleared")); handle(status, 0); CHECK(strstr(reply, "fault"));
    CHECK(calls == anchor.calls + disks[0].calls + disks[1].calls);
}
static void recovery_interrupted(void)
{
    const size_t boundaries[] = {0,1,4,24,32796,32800};
    for (unsigned op = 1; op <= 14; ++op) for (unsigned durable = 0; durable < 2; ++durable)
        for (size_t b = 0; b < sizeof(boundaries)/sizeof(boundaries[0]); ++b) {
            prepare(true); disks[1].fail_at = disks[1].calls + op;
            disks[1].cut_bytes = boundaries[b]; disks[1].persist_partial = durable != 0;
            CHECK(recover(0) == CT_RECOVERY_DESTINATION_UNAVAILABLE);
            CHECK(!boot(1)); enable(); action(3, 20, "-32005");
            CHECK(!boot(0)); enable(); action(3, 20, "-32005");
            ct_protocol_close(&protocol, 0); blank(1);
            CHECK(recover(0) == CT_RECOVERY_OK); CHECK(boot(1)); enable(); prior_actions_rejected(3);
            ++recovery_cuts;
        }
    for (unsigned op = 1; op <= 4; ++op) for (unsigned commit = 0; commit < 2; ++commit) {
        prepare(true); anchor.fail_at = anchor.calls + op; anchor.commit_on_failure = commit != 0;
        CHECK(recover(0) != CT_RECOVERY_OK);
        if (anchor.durable.backend_id == 2) {
            CHECK(!boot(0)); enable(); action(3, 20, "-32005");
            CHECK(boot(1)); enable(); prior_actions_rejected(3);
        } else {
            CHECK(!boot(1)); enable(); action(3, 20, "-32005");
            CHECK(!reload(0)); blank(1); CHECK(recover(0) == CT_RECOVERY_OK);
            CHECK(boot(1)); enable(); prior_actions_rejected(3);
        }
        ++recovery_cuts;
    }
}
static void finish_interrupted_action(void)
{
    CHECK(protocol.storage_fault); off();
    ct_protocol_close(&protocol, 0);
    bool exact = reload(0);
    ct_replay_recovery_result result = recover(0);
    CHECK(result == (exact ? CT_RECOVERY_OK : CT_RECOVERY_HISTORY_UNAVAILABLE));
    if (exact) { CHECK(boot(1)); enable(); prior_actions_rejected(4); }
    else { CHECK(!boot(1)); enable(); action(4, 20, "-32005"); }
}
static void original_write_interrupted(void)
{
    const size_t boundaries[] = {0,1,4,24,32796,32800};
    for (unsigned op = 1; op <= 6; ++op) for (unsigned durable = 0; durable < 2; ++durable)
        for (size_t b = 0; b < sizeof(boundaries)/sizeof(boundaries[0]); ++b) {
            prepare(false); CHECK(boot(0)); enable();
            disks[0].fail_at = disks[0].calls + op; disks[0].cut_bytes = boundaries[b];
            disks[0].persist_partial = durable != 0;
            action(3, 30, "-32005"); finish_interrupted_action(); ++write_cuts;
        }
    for (unsigned op = 1; op <= 4; ++op) for (unsigned commit = 0; commit < 2; ++commit) {
        prepare(false); CHECK(boot(0)); enable();
        anchor.fail_at = anchor.calls + op; anchor.commit_on_failure = commit != 0;
        action(3, 30, "-32005"); finish_interrupted_action(); ++anchor_cuts;
    }
}
static void repeated_recovery(void)
{
    prepare(false); unsigned selected = 0; uint64_t last_session = anchor.durable.session;
    for (unsigned i = 0; i < 50; ++i) {
        ct_protocol_close(&protocol, 0); off(); damage_companion(selected); blank(1-selected);
        CHECK(recover(selected) == CT_RECOVERY_OK);
        CHECK(!boot(selected)); enable(); action(4000 + i, 20, "-32005");
        selected = 1 - selected; CHECK(boot(selected)); CHECK(protocol.session > last_session);
        last_session = protocol.session;
        enable(); action(1000 + i, 20, "-32002"); action(2000 + i, 100 + i, "accepted");
        CHECK(boot(selected)); enable(); action(3000 + i, 100 + i, "-32002");
        ++cycles;
    }
}
int main(void)
{
    local_gates_and_rollback(); recovery_interrupted(); original_write_interrupted(); repeated_recovery();
    printf("PASS: 4 recovery integration groups; recovery_cuts=%zu; original_write_cuts=%zu; original_anchor_cuts=%zu; repeated_recoveries=%zu; rejection_checks=%zu; unexpected_replays=0\n",
           recovery_cuts, write_cuts, anchor_cuts, cycles, rejections);
    return 0;
}
