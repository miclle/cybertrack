#ifndef CYBERTRACK_INBOX_H
#define CYBERTRACK_INBOX_H

#include "cybertrack/runtime.h"

#define CT_INBOX_SLOTS 4

typedef struct {
    ct_event_kind kind;
    size_t length;
    ct_rpc_delivery delivery;
    char frame[CT_RPC_FRAME_MAX + 1];
} ct_inbox_item;

typedef enum {
    CT_INBOX_OK, CT_INBOX_STALE, CT_INBOX_OVERFLOW, CT_INBOX_OVERSIZE, CT_INBOX_INVALID
} ct_inbox_result;

/* Single owner, no internal locks or heap. Copy complete frames on ingress.
 * The platform must serialize producers/consumer and wake the control task on
 * disconnect/overflow. This is not a WebSocket fragment assembler. */
typedef struct {
    uint64_t session, last_session;
    size_t head, count;
    bool disconnect_pending;
    ct_inbox_item items[CT_INBOX_SLOTS];
} ct_inbox;

void ct_inbox_init(ct_inbox *q);
/* Bind only after runtime CONNECT assigned a new protocol session. A pending
 * disconnect must first be consumed AND applied to runtime before reconnect.
 * Session numbers must increase; init is once per boot, not per reconnect. */
bool ct_inbox_bind(ct_inbox *q, uint64_t session);
/* delivery is the original trusted ingress metadata, never reconstructed at
 * dequeue. Stale-session callbacks cannot poison a new connection's queue.
 * Overflow, oversize or invalid current-session input drops all pending frames
 * and schedules DISCONNECT, revoking enable when serviced by runtime. */
ct_inbox_result ct_inbox_push(ct_inbox *q, const char *frame, size_t length,
                             ct_rpc_delivery delivery);
void ct_inbox_disconnect(ct_inbox *q, uint64_t session);
/* DISCONNECT has priority over messages, with no slot needed. Returns IDLE if
 * empty. Caller constructs a runtime event using item's owned frame buffer.
 * Ordinary messages (including remote stop) are FIFO, at most one per cycle. */
ct_event_kind ct_inbox_take(ct_inbox *q, ct_inbox_item *item);

#endif
