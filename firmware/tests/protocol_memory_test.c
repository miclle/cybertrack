#include "synthetic_proof.h"
#include "cybertrack/protocol.h"
#include "fault_allocator.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(EXIT_FAILURE); } } while (0)
#define WRAP(body) "{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\"," body "}}"
static const char initialize[] = WRAP("\"id\":0,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"memory-test\",\"version\":\"1\"}}");
static const char move[] = WRAP("\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.move\",\"arguments\":{\"direction\":\"forward\",\"speed_level\":2,\"duration_ms\":100}}");
static const char conflict[] = WRAP("\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.move\",\"arguments\":{\"direction\":\"backward\",\"speed_level\":2,\"duration_ms\":100}}");
static const char water[] = WRAP("\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.water\",\"arguments\":{\"duration_ms\":100}}");
static const char bubbles[] = WRAP("\"id\":4,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.bubbles\",\"arguments\":{\"duration_ms\":100}}");
static const char stop[] = WRAP("\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.stop\"}");
static const char status[] = WRAP("\"id\":5,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.get_status\"}");
static const char stop_notification[] = WRAP("\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.stop\"}");
static const char move_notification[] = WRAP("\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.move\",\"arguments\":{\"direction\":\"forward\",\"speed_level\":2,\"duration_ms\":100}}");
static char dense[CT_RPC_FRAME_MAX + 1], pretty[CT_RPC_FRAME_MAX + 1];
static ct_protocol protocol;
static ct_controller control;
static ct_test_heap heap;
static char reply[CT_RPC_REPLY_CAP];
static ct_rpc_cache_entry saved_cache[CT_RPC_CACHE_SLOTS];
static unsigned char saved_filter[CT_RPC_REPLAY_BYTES];
static size_t injections, cache_failures, resize_failures, peak_bytes;

typedef enum { UNINITIALIZED, READY, ACTIVE, CACHED_STOP, CACHED_DENSE, CACHED_PRETTY } setup_kind;
typedef struct {
    const char *name, *frame, *expected;
    setup_kind setup;
    bool notification, requires_resize;
} scenario;

static ct_rpc_delivery delivery(void)
{
    return ct_test_delivery(&protocol, protocol.session, 0, control.enable_generation, true);
}

static ct_rpc_result handle(const char *frame)
{
    ct_rpc_result result = ct_protocol_handle(&protocol, frame, strlen(frame), delivery(), 0, reply, sizeof(reply));
    ct_test_heap_empty(&heap); /* Includes partial parse and simultaneous docs. */
    return result;
}

static void off(void)
{
    CHECK(control.output.left_level == 0 && control.output.right_level == 0);
    CHECK(!control.output.water && !control.output.bubbles && control.ends_at_ms == 0);
}

static void prepare(setup_kind setup)
{
    ct_test_heap_reset(&heap, 0, false);
    ct_init(&control, (ct_limits){1000, 200, 300, 3}, 0);
    ct_protocol_init(&protocol, &control, 50);
    CHECK(ct_protocol_set_allocator(&protocol, ct_test_allocator(&heap)));
    CHECK(ct_boot_complete(&control) == CT_OK);
    CHECK(ct_protocol_open(&protocol, 0) == 1);
    if (setup != UNINITIALIZED) {
        const char *init = setup == CACHED_DENSE ? dense : setup == CACHED_PRETTY ? pretty : initialize;
        CHECK(handle(init) == CT_RPC_RESPONSE && protocol.initialized);
        CHECK(ct_local_enable(&control, 0) == CT_OK);
    }
    if (setup == CACHED_STOP) {
        CHECK(handle(stop) == CT_RPC_RESPONSE);
        CHECK(ct_local_enable(&control, 0) == CT_OK);
    }
    if (setup == ACTIVE || setup == CACHED_STOP) {
        CHECK(handle(move) == CT_RPC_RESPONSE && control.state == CT_ACTIVE);
    }
    ct_test_heap_reset(&heap, 0, false);
}

static void make_dense(char *frame, bool formatted)
{
    const char *prefix = formatted
        ? "{  \"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\",\"id\":0,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{\"items\":["
        : "{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\",\"id\":0,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{\"items\":[";
    const char *suffix = "]},\"clientInfo\":{\"name\":\"memory-test\",\"version\":\"1\"}}}}";
    size_t length = strlen(prefix);
    memcpy(frame, prefix, length);
    while (length + 3 + strlen(suffix) <= CT_RPC_FRAME_MAX) {
        frame[length++] = '0'; frame[length++] = ',';
    }
    frame[length++] = '0';
    memcpy(frame + length, suffix, strlen(suffix)); length += strlen(suffix);
    while (length < CT_RPC_FRAME_MAX) frame[length++] = ' ';
    frame[length] = '\0';
}

static void sweep(const scenario *s)
{
    prepare(s->setup);
    ct_rpc_result result = handle(s->frame);
    CHECK(result == (s->notification ? CT_RPC_NO_RESPONSE : CT_RPC_RESPONSE));
    if (s->expected) CHECK(strstr(reply, s->expected));
    size_t calls = heap.calls, resizes = heap.resizes, peak = heap.peak_bytes;
    CHECK(calls >= 1);
    if (s->requires_resize) CHECK(resizes > 0);
    if (peak > peak_bytes) peak_bytes = peak;
    printf("CASE %s: calls=%zu resizes=%zu peak_bytes=%zu\n", s->name, calls, resizes, peak);
    for (unsigned mode = 0; mode < 2; ++mode) {
        for (size_t nth = 1; nth <= calls; ++nth) {
            prepare(s->setup);
            size_t count = protocol.cache_count;
            size_t next = protocol.cache_next;
            uint32_t bits = protocol.replay_bits_set;
            uint64_t sequence = protocol.sequence, submitted = control.last_sequence;
            uint64_t generation = control.enable_generation, session = protocol.session;
            bool initialized = protocol.initialized;
            memcpy(saved_cache, protocol.cache, sizeof(saved_cache));
            memcpy(saved_filter, protocol.replay_filter, sizeof(saved_filter));
            ct_test_heap_reset(&heap, nth, mode != 0);
            CHECK(handle(s->frame) == CT_RPC_RESPONSE);
            CHECK(heap.failures == 1 && heap.calls == nth); /* No fallback allocation for error response. */
            CHECK(strstr(reply, "\"code\":-32603"));
            if (strstr(reply, "Cache allocation failed")) {
                ++cache_failures;
                CHECK(!strstr(reply, "\"id\":null"));
            } else {
                CHECK(strstr(reply, "JSON allocation failed") && strstr(reply, "\"id\":null"));
            }
            resize_failures += heap.resize_failures;
            CHECK(control.state == CT_FAULT);
            off();
            CHECK(protocol.cache_count == count && !memcmp(protocol.cache, saved_cache, sizeof(saved_cache)));
            CHECK(protocol.cache_next == next && protocol.replay_bits_set == bits);
            CHECK(!memcmp(protocol.replay_filter, saved_filter, sizeof(saved_filter)));
            CHECK(protocol.sequence == sequence && control.last_sequence == submitted);
            CHECK(control.enable_generation == generation && protocol.session == session);
            CHECK(protocol.initialized == initialized);
            ++injections;
            /* Recovery of heap alone never restores enable or restarts a cached
             * accepted action. Retained cache must still return its original reply. */
            ct_test_heap_reset(&heap, 0, false);
            for (size_t i = 0; i < count; ++i) {
                CHECK(handle(saved_cache[i].frame) == CT_RPC_RESPONSE);
                CHECK(strcmp(reply, saved_cache[i].reply) == 0);
                CHECK(protocol.sequence == sequence);
                off(); CHECK(control.state == CT_FAULT);
            }
        }
    }
}

static void allocator_configuration(void)
{
    prepare(UNINITIALIZED);
    ct_rpc_allocator other = ct_test_allocator(&heap);
    CHECK(!ct_protocol_set_allocator(&protocol, other)); /* Open, then closed, still too late. */
    ct_protocol_close(&protocol, 0);
    CHECK(!ct_protocol_set_allocator(&protocol, other));
    CHECK(!ct_protocol_set_allocator(NULL, other));
    ct_init(&control, (ct_limits){0}, 0);
    ct_protocol_init(&protocol, &control, 50);
    for (unsigned i = 0; i < 3; ++i) {
        ct_rpc_allocator invalid = other;
        if (i == 0) invalid.allocate = NULL;
        if (i == 1) invalid.resize = NULL;
        if (i == 2) invalid.release = NULL;
        CHECK(!ct_protocol_set_allocator(&protocol, invalid));
        CHECK(protocol.allocator.allocate == NULL);
    }
    CHECK(ct_protocol_set_allocator(&protocol, other));
    ct_rpc_allocator invalid = other; invalid.release = NULL;
    CHECK(!ct_protocol_set_allocator(&protocol, invalid));
    CHECK(protocol.allocator.release == other.release);
    CHECK(ct_protocol_open(&protocol, 0) != 0);
    CHECK(handle(initialize) == CT_RPC_RESPONSE && protocol.initialized);
}

static void preparse_gates_and_recovery(void)
{
    prepare(ACTIVE);
    ct_test_heap_reset(&heap, 1, true);
    ct_rpc_delivery old = delivery(); old.session = 0;
    CHECK(ct_protocol_handle(&protocol, move, strlen(move), old, 0, reply, sizeof(reply)) == CT_RPC_STALE_SESSION);
    CHECK(ct_protocol_handle(&protocol, move, strlen(move), delivery(), 0, reply, 1) == CT_RPC_BAD_ARGUMENT);
    CHECK(ct_protocol_handle(&protocol, move, CT_RPC_FRAME_MAX + 1, delivery(), 0, reply, sizeof(reply)) == CT_RPC_RESPONSE);
    CHECK(heap.calls == 0 && control.state == CT_ACTIVE);
    CHECK(handle(status) == CT_RPC_RESPONSE && strstr(reply, "-32603")); off();
    ct_test_heap_reset(&heap, 0, false);
    CHECK(handle(water) == CT_RPC_RESPONSE && strstr(reply, "not_ready")); off();
    CHECK(ct_local_enable(&control, 0) == CT_OK);
    CHECK(handle(move) == CT_RPC_RESPONSE && strstr(reply, "accepted")); off(); /* Original response only. */
    CHECK(handle(bubbles) == CT_RPC_RESPONSE && control.output.bubbles);
    ct_protocol_close(&protocol, 0); off();
    ct_test_heap_reset(&heap, 1, true);
    CHECK(ct_protocol_open(&protocol, 0) != 0);
    CHECK(handle(initialize) == CT_RPC_RESPONSE && strstr(reply, "-32603"));
    CHECK(!protocol.initialized); off(); /* Custom allocator survived reconnect. */
}

static void persistent_failure_and_initialize_recovery(void)
{
    prepare(UNINITIALIZED);
    ct_test_heap_reset(&heap, 1, true);
    for (unsigned i = 0; i < 20; ++i) {
        CHECK(handle(i % 2 ? initialize : stop_notification) == CT_RPC_RESPONSE);
        CHECK(strstr(reply, "\"code\":-32603") && strstr(reply, "\"id\":null"));
        CHECK(!protocol.initialized && protocol.cache_count == 0 && protocol.sequence == 0);
        off(); CHECK(control.state == CT_FAULT);
    }
    CHECK(heap.failures == 20 && heap.calls == 20);
    ct_test_heap_reset(&heap, 0, false);
    CHECK(handle(initialize) == CT_RPC_RESPONSE && protocol.initialized);
    CHECK(control.state == CT_FAULT); off();
    CHECK(ct_local_enable(&control, 0) == CT_OK);
    CHECK(handle(move) == CT_RPC_RESPONSE && control.state == CT_ACTIVE);
    CHECK(handle(stop_notification) == CT_RPC_NO_RESPONSE); off();
}

int main(void)
{
    make_dense(dense, false); make_dense(pretty, true);
    const scenario cases[] = {
        {"initialize", initialize, "protocolVersion", UNINITIALIZED, false, false},
        {"move", move, "accepted", READY, false, false},
        {"water", water, "accepted", READY, false, false},
        {"bubbles", bubbles, "accepted", READY, false, false},
        {"status-active", status, "ACTIVE", ACTIVE, false, false},
        {"stop-active", stop, "logical_outputs_cleared", ACTIVE, false, false},
        {"stop-notification", stop_notification, NULL, ACTIVE, true, false},
        {"move-notification", move_notification, NULL, ACTIVE, true, false},
        {"cached-move", move, "accepted", ACTIVE, false, false},
        {"conflicting-move", conflict, "-32001", ACTIVE, false, false},
        {"cached-stop", stop, "logical_outputs_cleared", CACHED_STOP, false, false},
        {"malformed-json", "{\"bad\":[1,2,", "-32700", ACTIVE, false, false},
        {"invalid-envelope", "{\"bad\":1}", "-32600", ACTIVE, false, false},
        {"max-frame-initialize", dense, "protocolVersion", UNINITIALIZED, false, true},
        {"max-frame-cached", dense, "protocolVersion", CACHED_DENSE, false, true},
        {"pretty-max-initialize", pretty, "protocolVersion", UNINITIALIZED, false, true},
        {"pretty-max-cached", pretty, "protocolVersion", CACHED_PRETTY, false, true}
    };
    for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) sweep(&cases[i]);
    allocator_configuration();
    preparse_gates_and_recovery();
    persistent_failure_and_initialize_recovery();
    CHECK(cache_failures > 0 && resize_failures > 0);
    ct_test_heap_empty(&heap);
    printf("PASS: 17 allocation sweeps, %zu injected failures (%zu cache failures, %zu resize failures); peak_bytes=%zu; protocol_bytes=%zu; outstanding=0; 3 contract/recovery groups\n",
           injections, cache_failures, resize_failures, peak_bytes, sizeof(protocol));
    return EXIT_SUCCESS;
}
