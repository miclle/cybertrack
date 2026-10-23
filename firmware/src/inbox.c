#include "cybertrack/inbox.h"

#include <string.h>

void ct_inbox_init(ct_inbox *q)
{
    if (q) memset(q, 0, sizeof(*q));
}

bool ct_inbox_bind(ct_inbox *q, uint64_t session)
{
    if (!q || !session || session <= q->last_session || q->session || q->disconnect_pending) return false;
    q->session = q->last_session = session;
    return true;
}

void ct_inbox_disconnect(ct_inbox *q, uint64_t session)
{
    if (!q || !session || session != q->session) return;
    q->head = q->count = 0;
    q->session = 0;
    q->disconnect_pending = true;
}

ct_inbox_result ct_inbox_push(ct_inbox *q, const char *frame, size_t length,
                             ct_rpc_delivery delivery)
{
    if (!q) return CT_INBOX_INVALID;
    if (!delivery.session || delivery.session != q->session) return CT_INBOX_STALE;
    ct_inbox_result result = CT_INBOX_OK;
    if (!frame) result = CT_INBOX_INVALID;
    else if (length > CT_RPC_FRAME_MAX) result = CT_INBOX_OVERSIZE;
    else if (q->count == CT_INBOX_SLOTS) result = CT_INBOX_OVERFLOW;
    if (result != CT_INBOX_OK) {
        ct_inbox_disconnect(q, delivery.session);
        return result;
    }
    ct_inbox_item *slot = &q->items[(q->head + q->count) % CT_INBOX_SLOTS];
    slot->kind = CT_EVENT_MESSAGE;
    slot->length = length;
    slot->delivery = delivery;
    memcpy(slot->frame, frame, length);
    slot->frame[length] = '\0';
    ++q->count;
    return CT_INBOX_OK;
}

ct_event_kind ct_inbox_take(ct_inbox *q, ct_inbox_item *item)
{
    if (!item) return CT_EVENT_IDLE;
    memset(item, 0, sizeof(*item));
    if (!q) return CT_EVENT_IDLE;
    if (q->disconnect_pending) {
        q->disconnect_pending = false;
        item->kind = CT_EVENT_DISCONNECT;
    } else if (q->count) {
        *item = q->items[q->head];
        q->head = (q->head + 1) % CT_INBOX_SLOTS;
        --q->count;
    }
    return item->kind;
}
