#include "synthetic_proof.h"
#include "cybertrack/protocol.h"
#include "fault_allocator.h"

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(EXIT_FAILURE); } } while (0)
#define WRAP(x) "{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\"," x "}}"
#define ACTIONS 20000u
#define READS 100000u
#define RECOVERIES 500u
static const char initialize[] = WRAP("\"id\":\"init\",\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"stress\",\"version\":\"1\"}}");
static const char stop[] = WRAP("\"id\":\"stop\",\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.stop\"}");
static ct_controller control;
static ct_protocol protocol, saved;
static ct_test_heap heap;
static uint64_t now;
static size_t requests, accepted, collisions, recovery_accepted, replay_checks;
static char frame[CT_RPC_FRAME_MAX + 1], reply[CT_RPC_REPLY_CAP], original[CT_RPC_REPLY_CAP];

static void off(void)
{
    CHECK(!control.output.left_level && !control.output.right_level);
    CHECK(!control.output.water && !control.output.bubbles && !control.ends_at_ms);
}

static void handle(const char *text)
{
    ct_rpc_delivery delivery = ct_test_delivery(&protocol, protocol.session, now, control.enable_generation, true);
    unsigned action_id;
    if (sscanf(text, "{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\",\"id\":\"action-%u", &action_id) == 1)
        delivery.proof.intent = (uint64_t)action_id + 1; /* Synthetic producer's stable intent. */
    CHECK(ct_protocol_handle(&protocol, text, strlen(text), delivery, now, reply, sizeof(reply)) == CT_RPC_RESPONSE);
    ct_test_heap_empty(&heap);
    CHECK(protocol.cache_count <= CT_RPC_CACHE_SLOTS && protocol.cache_next < CT_RPC_CACHE_SLOTS);
    CHECK(protocol.replay_bits_set <= CT_RPC_REPLAY_BYTES * 8u);
    ++requests;
}

static void action(unsigned id)
{
    const char *tool = id % 3 == 0 ? "move" : id % 3 == 1 ? "water" : "bubbles";
    const char *extra = id % 3 == 0 ? ",\"direction\":\"forward\",\"speed_level\":1" : "";
    int n = snprintf(frame, sizeof(frame), WRAP("\"id\":\"action-%u\",\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.%s\",\"arguments\":{\"duration_ms\":1%s}}"), id, tool, extra);
    CHECK(n > 0 && (size_t)n < sizeof(frame));
}

static void status(unsigned id, bool padded)
{
    int n = snprintf(frame, sizeof(frame), WRAP("\"id\":\"status-%u\",\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.get_status\"}"), id);
    CHECK(n > 0 && (size_t)n < sizeof(frame));
    if (padded) {
        memset(frame + n, ' ', CT_RPC_FRAME_MAX - (size_t)n);
        frame[CT_RPC_FRAME_MAX] = '\0';
    }
}

static bool accepted_or_collision(void)
{
    if (strstr(reply, "\"text\":\"accepted\"")) {
        CHECK(control.state == CT_ACTIVE && control.ends_at_ms == now + 1);
        return true;
    }
    CHECK(strstr(reply, "\"code\":-32002"));
    off();
    return false;
}

static void mixed_actions_and_retries(void)
{
    for (unsigned i = 0; i < ACTIONS; ++i) {
        now += 1000; action(i);
        uint64_t sequence = protocol.sequence;
        handle(frame);
        bool ran = accepted_or_collision();
        accepted += ran; collisions += !ran;
        CHECK(protocol.sequence == sequence + (ran ? 1u : 0u));
        memcpy(original, reply, sizeof(original));
        ++now; CHECK(ct_tick(&control, now) == CT_OK); off();
        sequence = protocol.sequence;
        handle(frame); /* Resident duplicate returns the original bytes. */
        CHECK(!strcmp(reply, original) && protocol.sequence == sequence); off();
        ++replay_checks;
    }
    CHECK(accepted > ACTIONS * 9 / 10); /* Availability budget for this corpus only. */
    uint64_t sequence = protocol.sequence;
    for (unsigned i = 0; i < ACTIONS; ++i) {
        action(i); handle(frame);
        CHECK(strstr(reply, "\"code\":-32002"));
        CHECK(protocol.sequence == sequence); off(); ++replay_checks;
    }
    printf("MIXED actions=%u accepted=%zu conservative_rejections=%zu replay_checks=%zu\n", ACTIONS, accepted, collisions, replay_checks);
}

static void continuous_reads(void)
{
    uint64_t sequence = protocol.sequence;
    for (unsigned i = 0; i < READS; ++i) {
        now += 1000;
        status(i, i % 1000 == 0); /* Include 100 maximum-size frames. */
        handle(frame);
        CHECK(strstr(reply, "replay_guard") && !strstr(reply, "\"error\""));
        CHECK(protocol.sequence == sequence); off();
    }
    action(0); handle(frame);
    CHECK(strstr(reply, "\"code\":-32002") && protocol.sequence == sequence); off();
    ++replay_checks;
    printf("READS count=%u max_frames=%u bits_set=%" PRIu32 "\n", READS, READS / 1000, protocol.replay_bits_set);
}

static void repeated_recovery(void)
{
    for (unsigned i = 0; i < RECOVERIES; ++i) {
        uint64_t old_session = protocol.session;
        uint32_t bits = protocol.replay_bits_set;
        now += 1000;
        if (i % 2 == 0) ct_protocol_close(&protocol, now);
        CHECK(ct_protocol_open(&protocol, now) > old_session); /* With and without close. */
        CHECK(protocol.replay_bits_set == bits && protocol.cache_count == 0);
        off(); CHECK(control.state != CT_READY && !protocol.initialized);
        action(i);
        ct_rpc_delivery stale = ct_test_delivery(&protocol, old_session, now, control.enable_generation, true);
        CHECK(ct_protocol_handle(&protocol, frame, strlen(frame), stale, now, reply, sizeof(reply)) == CT_RPC_STALE_SESSION);
        handle(initialize);
        CHECK(protocol.initialized && ct_local_enable(&control, now) == CT_OK);
        handle(frame); /* Fresh metadata cannot launder an old ID into a new action. */
        CHECK(strstr(reply, "\"code\":-32002") && protocol.sequence == 0); off();
        ++replay_checks;
        action(ACTIONS + i); handle(frame);
        recovery_accepted += accepted_or_collision();
        ++now; CHECK(ct_tick(&control, now) == CT_OK); off();
    }
    CHECK(recovery_accepted > 0);
    printf("RECOVERY count=%u fresh_actions_accepted=%zu replay_checks=%zu\n", RECOVERIES, recovery_accepted, replay_checks);
}

static void full_cache_allocation_failure(void)
{
    for (unsigned i = 0; i < CT_RPC_CACHE_SLOTS; ++i) { status(READS + i, false); handle(frame); }
    saved = protocol;
    ct_test_heap_reset(&heap, 1, true);
    action(ACTIONS + RECOVERIES); handle(frame);
    CHECK(strstr(reply, "\"code\":-32603"));
    CHECK(!memcmp(&protocol, &saved, sizeof(protocol))); off();
    ct_test_heap_reset(&heap, 0, false);
    CHECK(ct_local_enable(&control, now) == CT_OK);
    action(0); handle(frame);
    CHECK(strstr(reply, "\"code\":-32002")); off(); ++replay_checks;
}

static void saturated_guard(void)
{
    /* Deterministically exercise the terminal state without probabilistic waits.
     * This is test-only state injection, not a production reset/config API. */
    memset(protocol.replay_filter, 0xff, sizeof(protocol.replay_filter));
    protocol.replay_bits_set = CT_RPC_REPLAY_BYTES * 8u;
    ct_protocol_close(&protocol, now);
    CHECK(ct_protocol_open(&protocol, now)); handle(initialize);
    CHECK(protocol.initialized && ct_local_enable(&control, now) == CT_OK);
    for (unsigned i = 0; i < 1000; ++i) {
        action(ACTIONS + RECOVERIES + i); handle(frame);
        CHECK(strstr(reply, "\"code\":-32002") && protocol.sequence == 0); off();
        status(READS + 1000 + i, false); handle(frame);
        CHECK(strstr(reply, "replay_guard") && !strstr(reply, "\"error\""));
    }
    handle(stop); CHECK(strstr(reply, "logical_outputs_cleared")); off();
    CHECK(control.state == CT_FAULT && protocol.replay_bits_set == CT_RPC_REPLAY_BYTES * 8u);
}

int main(void)
{
    ct_init(&control, (ct_limits){10, 10, 10, 1}, 0);
    ct_protocol_init(&protocol, &control, 50);
    CHECK(ct_protocol_set_allocator(&protocol, ct_test_allocator(&heap)));
    CHECK(ct_boot_complete(&control) == CT_OK && ct_protocol_open(&protocol, 0));
    handle(initialize); CHECK(ct_local_enable(&control, 0) == CT_OK);
    mixed_actions_and_retries(); continuous_reads(); repeated_recovery();
    size_t peak = heap.peak_bytes;
    full_cache_allocation_failure(); saturated_guard();
    ct_test_heap_empty(&heap);
    printf("PASS: 5 stress groups; requests=%zu; replay_checks=%zu; virtual_ms=%" PRIu64 "; protocol_bytes=%zu; sampled_peak_json_bytes=%zu; live_blocks=%zu\n",
           requests, replay_checks, now, sizeof(protocol), peak, heap.live_blocks);
    return EXIT_SUCCESS;
}
