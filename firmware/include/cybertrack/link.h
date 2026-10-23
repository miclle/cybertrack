#ifndef CYBERTRACK_LINK_H
#define CYBERTRACK_LINK_H

#include "cybertrack/inbox.h"

/* Normalized WebSocket frame payload chunks, not raw TCP bytes. Offset/total are
 * within ONE WebSocket frame; opcode/fin must remain constant across its chunks.
 * The SDK adapter must reject negative lengths before converting to size_t. */
typedef enum { CT_WS_CONT = 0, CT_WS_TEXT = 1, CT_WS_BINARY = 2,
               CT_WS_CLOSE = 8, CT_WS_PING = 9, CT_WS_PONG = 10 } ct_ws_opcode;
typedef struct {
    ct_ws_opcode opcode;
    bool fin;
    size_t offset, total, length;
    const char *data;
} ct_ws_chunk;

typedef struct {
    uint32_t connect_ms, handshake_ms, fragment_ms, send_ms, retry_ms;
} ct_link_limits;

typedef enum { CT_LINK_DOWN, CT_LINK_CONNECTING, CT_LINK_HANDSHAKE,
               CT_LINK_ONLINE, CT_LINK_BACKOFF, CT_LINK_HALTED } ct_link_state;
typedef enum {
    CT_LINK_NO_ERROR, CT_LINK_CONNECT_TIMEOUT, CT_LINK_HANDSHAKE_TIMEOUT,
    CT_LINK_FRAGMENT_TIMEOUT, CT_LINK_FRAME_ERROR, CT_LINK_OVERSIZE,
    CT_LINK_UNSUPPORTED, CT_LINK_QUEUE_ERROR, CT_LINK_SEND_ERROR,
    CT_LINK_SEND_TIMEOUT, CT_LINK_DISCONNECTED, CT_LINK_CLOCK_ERROR,
    CT_LINK_RUNTIME_ERROR, CT_LINK_EXHAUSTED
} ct_link_error;

typedef struct {
    uint64_t attempt, id;
    size_t length;
    char frame[CT_RPC_REPLY_CAP];
} ct_link_tx;

/* One serial owner for link/runtime/inbox; callbacks/ISRs must hand off events.
 * No network calls, locks, heap, SDK or default hardware/time configuration.
 * Storage is large: allocate statically or on the heap, not a small task stack. */
typedef struct {
    ct_runtime *runtime;
    ct_link_limits limits;
    ct_link_state state;
    ct_link_error error;
    uint64_t attempt, tx_generation, last_ms, phase_ms, fragment_started_ms, tx_started_ms;
    bool valid, close_required, disconnect_pending, ready_pending;
    bool message_open, frame_open, frame_fin, tx_pending, tx_taken;
    ct_ws_opcode frame_opcode;
    size_t frame_total, frame_received, message_length;
    ct_rpc_delivery delivery;
    char message[CT_RPC_FRAME_MAX + 1];
    ct_inbox inbox;
    ct_inbox_item item;
    ct_runtime_response response;
    ct_link_tx tx;
} ct_link;

/* Once per boot, after runtime init while disconnected. All budgets nonzero. */
bool ct_link_init(ct_link *link, ct_runtime *runtime, ct_link_limits limits);
/* Returns a new attempt token or zero if not eligible. After failure, adapter
 * must close/abort old handle and report closed, and service must apply the
 * disconnect, before retry. Backoff uses subtraction, no deadline wraparound. */
uint64_t ct_link_begin(ct_link *link, uint64_t now_ms);
bool ct_link_connected(ct_link *link, uint64_t attempt, uint64_t now_ms);
/* Trusted adapter signal AFTER TLS/auth and platform hello validation, not a
 * wire field. This module simulates that boundary, it does not validate hello.
 * Protocol CONNECT is applied at next service; no data accepted before then. */
bool ct_link_ready(ct_link *link, uint64_t attempt, uint64_t now_ms);
/* Only this offline MCP text path is implemented. Binary/audio must be routed
 * separately by a future platform dispatcher; here it closes the connection.
 * freshness_verified is trusted evidence at FIRST chunk; never inferred from
 * connection or fragment completion. Pass false without actual evidence. */
bool ct_link_receive(ct_link *link, uint64_t attempt, ct_ws_chunk chunk,
                     bool freshness_verified, uint64_t now_ms);
void ct_link_closed(ct_link *link, uint64_t attempt, uint64_t now_ms);
/* Must run periodically even offline, during connect/backoff, partial receive
 * and pending send. Applies disconnect before queued messages and services the
 * local safety inputs independently. false means link/runtime is halted.
 * No raw runtime/protocol/inbox calls while the link owns them. */
bool ct_link_service(ct_link *link, uint64_t now_ms);
/* Copy response once to worker-owned storage; no borrowed pointer escapes.
 * Worker sends once, then reports completion. No automatic resend. Timeout
 * starts at response creation, including time waiting for a worker. */
bool ct_link_take_tx(ct_link *link, ct_link_tx *tx, uint64_t now_ms);
bool ct_link_sent(ct_link *link, uint64_t attempt, uint64_t id,
                  bool success, size_t bytes, uint64_t now_ms);

#endif
