#include "cybertrack/protocol.h"
#include "fake_store.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%d: %s; reply=%s\n", __LINE__, #x, reply); exit(1); } } while (0)
#define WRAP(x) "{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\"," x "}}"
static const char init[] = WRAP("\"id\":\"init\",\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"freshness\",\"version\":\"1\"}}");
static const char stop[] = WRAP("\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.stop\"}");
static ct_protocol p;
static ct_controller c;
static ct_replay_store store;
static ct_test_store disk;
static char reply[CT_RPC_REPLY_CAP];
static unsigned calls, rejected, cut_cases;
static void off(void) { CHECK(!c.output.left_level && !c.output.water && !c.output.bubbles && !c.ends_at_ms); }
static void handle(const char *frame, ct_action_proof proof, uint64_t received, uint64_t now)
{
    /* Local ingress tags deliberately use CURRENT scope. Origin proof must still
     * reject messages produced under old sessions/enables. */
    ct_rpc_delivery d = {p.session, received, c.enable_generation, proof};
    CHECK(ct_protocol_handle(&p, frame, strlen(frame), d, now, reply, sizeof(reply)) == CT_RPC_RESPONSE);
    ++calls;
}
static void action(unsigned rpc, ct_action_proof proof, uint64_t received, uint64_t now, const char *expected)
{
    char frame[256];
    snprintf(frame, sizeof(frame), WRAP("\"id\":%u,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.water\",\"arguments\":{\"duration_ms\":1}}"), rpc);
    uint64_t accepted = p.accepted_sequence;
    handle(frame, proof, received, now); CHECK(strstr(reply, expected));
    if (!strcmp(expected, "accepted")) CHECK(c.output.water);
    else { CHECK(p.accepted_sequence == accepted); off(); ++rejected; }
}
static void session(uint64_t now)
{
    CHECK(ct_protocol_open(&p, now)); handle(init, (ct_action_proof){0}, now, now);
    CHECK(p.initialized && ct_local_enable(&c, now) == CT_OK);
}
static bool boot(void)
{
    ct_test_store_power_cut(&disk);
    bool ready = ct_replay_store_load(&store, ct_test_store_io(&disk)) == CT_STORE_READY;
    ct_init(&c, (ct_limits){10,10,10,1}, 0); ct_protocol_init(&p, &c, 50);
    CHECK(ct_protocol_attach_store(&p, &store) == ready);
    CHECK(ct_boot_complete(&c) == CT_OK); session(0); off(); return ready;
}
static void reset(void)
{
    ct_test_store_blank(&disk);
    CHECK(ct_replay_store_load(&store, ct_test_store_io(&disk)) == CT_STORE_EMPTY);
    CHECK(ct_replay_store_provision(&store)); CHECK(boot());
}
static ct_action_proof issue(uint64_t intent, uint64_t now)
{
    ct_action_proof proof;
    CHECK(ct_protocol_issue_window(&p, now, &proof)); proof.intent = intent; return proof;
}
static void delayed_and_scope(void)
{
    reset(); ct_action_proof old = issue(1, 0);
    action(1, old, 50, 50, "expired"); /* Delayed BEFORE first ingress. */
    action(2, issue(1, 50), 50, 50, "-32002"); /* Re-label RPC + refresh window. */
    action(3, issue(2, 50), 50, 99, "accepted"); CHECK(ct_tick(&c, 100) == CT_OK);
    old = issue(3, 100); session(101);
    action(4, old, 101, 101, "freshness_unverified");
    old = issue(4, 101); ct_stop(&c); CHECK(ct_local_enable(&c, 101) == CT_OK);
    action(5, old, 101, 101, "freshness_unverified");
    old = issue(5, 101); (void)issue(6, 102);
    action(6, old, 102, 102, "freshness_unverified");
    old = issue(7, 102); action(7, old, 102, 152, "expired"); /* Queue age. */
    CHECK(boot()); action(8, issue(7, 0), 0, 0, "-32002");
}
static void retry_identity_and_reset(void)
{
    reset(); ct_action_proof old = issue(100, 0);
    action(1, old, 0, 0, "accepted"); CHECK(ct_tick(&c, 1) == CT_OK);
    action(2, old, 1, 1, "-32002");
    /* Changed action parameters, same intent, still rejected. */
    handle(WRAP("\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.bubbles\",\"arguments\":{\"duration_ms\":2}}"), old, 1, 1);
    CHECK(strstr(reply, "-32002")); off();
    session(1); action(4, issue(100, 1), 1, 1, "-32002");
    CHECK(boot()); action(5, issue(100, 0), 0, 0, "-32002");
    /* Unseen pre-reset intent is rejected by origin session, even though local
     * ingress metadata has the new session and local enable. */
    old.intent = 101; action(6, old, 0, 0, "freshness_unverified");
    action(7, issue(101, 0), 0, 0, "-32002");
    action(8, issue(102, 0), 0, 0, "accepted");
}
static void cached_and_evicted(void)
{
    reset(); ct_action_proof proof = issue(200, 0);
    action(1, proof, 0, 0, "accepted"); CHECK(ct_tick(&c, 1) == CT_OK);
    uint64_t accepted = p.accepted_sequence;
    /* Resident response is not a second execution, even if a caller violates
     * the stable-intent rule. Retire that supplied identity before replying. */
    proof.intent = 201;
    handle(WRAP("\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.water\",\"arguments\":{\"duration_ms\":1}}"), proof, 1, 1);
    CHECK(strstr(reply, "accepted") && p.accepted_sequence == accepted); off();
    action(2, proof, 1, 1, "-32002");
    for (unsigned i = 0; i < 20; ++i) {
        char frame[128]; snprintf(frame, sizeof(frame), WRAP("\"id\":%u,\"method\":\"ping\""), 100+i);
        handle(frame, (ct_action_proof){0}, 1, 1);
    }
    action(3, issue(200, 1), 1, 1, "-32002");
    CHECK(boot()); action(4, issue(201, 0), 0, 0, "-32002");
}
static void rejected_and_stop(void)
{
    reset(); ct_action_proof proof = issue(300, 0);
    ct_stop(&c); action(1, proof, 0, 0, "not_ready");
    CHECK(ct_local_enable(&c, 0) == CT_OK);
    action(2, issue(300, 0), 0, 0, "-32002");
    action(3, (ct_action_proof){0}, 0, 0, "freshness_unverified");
    action(4, issue(301, 0), 0, 0, "accepted");
    size_t io = disk.calls;
    ct_rpc_delivery d = {p.session, 0, 0, {0}};
    CHECK(ct_protocol_handle(&p, stop, strlen(stop), d, 0, reply, sizeof(reply)) == CT_RPC_NO_RESPONSE);
    off(); CHECK(disk.calls == io);
    CHECK(ct_local_enable(&c, 0) == CT_OK);
    action(5, issue(302, 0), 0, 0, "accepted"); CHECK(ct_tick(&c, 1) == CT_OK);
    /* Unknown/invalid methods also retire the trusted intent. */
    proof = issue(303, 1);
    handle(WRAP("\"id\":6,\"method\":\"unknown\""), proof, 1, 1); CHECK(strstr(reply, "-32601"));
    action(7, proof, 1, 1, "-32002");
}
static void cuts(void)
{
    const size_t sizes[] = {0, 4, 24, 32792, 32796, 32800};
    for (unsigned op = 1; op <= 6; ++op) for (unsigned durable = 0; durable < 2; ++durable)
        for (size_t i = 0; i < sizeof(sizes)/sizeof(sizes[0]); ++i) {
            reset(); action(1, issue(400, 0), 0, 0, "accepted"); CHECK(ct_tick(&c, 1) == CT_OK);
            ct_action_proof proof = issue(401, 1);
            disk.fail_at = disk.calls + op; disk.cut_bytes = sizes[i]; disk.persist_partial = durable != 0;
            action(2, proof, 1, 1, "-32005");
            bool ready = boot();
            ct_action_proof retry = {0};
            if (ready) retry = issue(400, 0);
            action(3, retry, 0, 0, ready ? "-32002" : "-32005");
            /* If a complete reservation reached durable media despite failure,
             * a different RPC ID cannot execute that intent after reboot. */
            if (ready && (op == 6 || (durable && ((op == 4 && sizes[i] >= 4) || (op == 5 && sizes[i] == 32800)))))
                action(4, issue(401, 0), 0, 0, "-32002");
            ++cut_cases;
        }
}
int main(void)
{
    delayed_and_scope(); retry_identity_and_reset(); cached_and_evicted(); rejected_and_stop(); cuts();
    printf("PASS: 5 freshness integration groups; calls=%u; rejected=%u; cuts=%u; unexpected_replays=0\n", calls, rejected, cut_cases);
    return 0;
}
