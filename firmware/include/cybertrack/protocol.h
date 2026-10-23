#ifndef CYBERTRACK_PROTOCOL_H
#define CYBERTRACK_PROTOCOL_H

#include "cybertrack/control.h"
#include <stddef.h>

#define CT_RPC_FRAME_MAX 2048
#define CT_RPC_REPLY_CAP 4096
#define CT_RPC_ID_MAX 64
#define CT_RPC_ID_CAP (CT_RPC_ID_MAX * 6 + 3)
#define CT_RPC_CACHE_SLOTS 16
#define CT_RPC_REPLAY_BYTES 32768

typedef enum {
    CT_RPC_RESPONSE, CT_RPC_NO_RESPONSE, CT_RPC_STALE_SESSION, CT_RPC_BAD_ARGUMENT
} ct_rpc_result;

/* Trusted transport metadata, NEVER populated from JSON arguments.
 * received_at_ms is the first local ingress time, not the dequeue/retry time.
 * freshness_verified requires evidence about pre-ingress command age. F1 tests
 * synthesize it; no production freshness mechanism is implemented yet. */
typedef struct {
    uint64_t session;
    uint64_t received_at_ms;
    uint64_t enable_generation;
    bool freshness_verified;
} ct_rpc_delivery;

typedef struct {
    char id[CT_RPC_ID_CAP];
    char frame[CT_RPC_FRAME_MAX + 1];
    char reply[CT_RPC_REPLY_CAP];
} ct_rpc_cache_entry;

/* Optional parser allocator. malloc/realloc/free semantics, including retaining
 * the original allocation when resize fails. Returned memory must have malloc
 * alignment. Callbacks/context must remain valid for this protocol's lifetime. */
typedef struct {
    void *(*allocate)(void *context, size_t size);
    void *(*resize)(void *context, void *ptr, size_t old_size, size_t size);
    void (*release)(void *context, void *ptr);
    void *context;
} ct_rpc_allocator;

/* Single-owner, like ct_controller. Use static/heap storage on embedded targets;
 * complete replies are a session-local FIFO; the monotone replay filter belongs
 * to the boot, never to a connection. Collisions may reject new actions. */
typedef struct {
    ct_controller *control;
    uint64_t generation;
    uint64_t session;
    uint64_t sequence;
    uint32_t max_queue_ms;
    bool initialized;
    size_t cache_count;
    size_t cache_next;
    uint32_t replay_bits_set;
    unsigned char replay_filter[CT_RPC_REPLAY_BYTES];
    ct_rpc_allocator allocator;
    ct_rpc_cache_entry cache[CT_RPC_CACHE_SLOTS];
} ct_protocol;

/* Initialize once per boot, while the controller is disconnected. A zero queue
 * budget disables actions. No actual operating limits are supplied here. */
void ct_protocol_init(ct_protocol *p, ct_controller *control, uint32_t max_queue_ms);
/* Optional local configuration after init and before the first open (including
 * with runtime: after runtime_init, before CONNECT). All callbacks are required;
 * invalid/late changes return false without altering the current allocator.
 * Default remains libc heap allocation. No test injector is in the library. */
bool ct_protocol_set_allocator(ct_protocol *p, ct_rpc_allocator allocator);
/* Open/reconnect revokes local enable and allocates a fresh generation. Returns
 * zero on failure. Tag queued deliveries with this value at ingress. Retains
 * the replay filter across close/open; only init at a genuine boot clears it. */
uint64_t ct_protocol_open(ct_protocol *p, uint64_t now_ms);
void ct_protocol_close(ct_protocol *p, uint64_t now_ms);
/* One complete {"type":"mcp","payload":{...}} frame. No network I/O or queue.
 * reply_cap must be >= CT_RPC_REPLY_CAP; smaller buffers cause no side effects.
 * No response is generated for notifications. Stop notifications are allowed;
 * action notifications are ignored. Current-session stop bypasses cache/TTL.
 * Parser allocation or cache-read failure clears logical output and requires
 * local re-enable, retaining the original cache and sequence. Temporary parser
 * allocations are released before return; error formatting does not allocate.
 * Call ct_tick independently even when no messages arrive. */
ct_rpc_result ct_protocol_handle(ct_protocol *p, const char *frame, size_t length,
                                ct_rpc_delivery delivery, uint64_t now_ms,
                                char *reply, size_t reply_cap);

#endif
