#include "cybertrack/link.h"

#include <string.h>

static void drop(ct_link *l, ct_link_error error, uint64_t now, bool halt)
{
    l->error = error;
    l->state = halt ? CT_LINK_HALTED : CT_LINK_BACKOFF;
    l->phase_ms = now;
    l->close_required = l->attempt != 0;
    l->disconnect_pending = true;
    l->ready_pending = l->message_open = l->frame_open = false;
    l->message_length = l->frame_received = l->frame_total = 0;
    memset(l->message, 0, sizeof(l->message));
    l->tx_pending = l->tx_taken = false;
    memset(&l->tx, 0, sizeof(l->tx));
    ct_inbox_disconnect(&l->inbox, l->inbox.session);
}

static bool current(const ct_link *l, uint64_t attempt)
{
    return l && l->valid && attempt != 0 && attempt == l->attempt;
}

static bool advance(ct_link *l, uint64_t now)
{
    if (!l || !l->valid) return false;
    if (now < l->last_ms || now < l->runtime->control.last_now_ms) {
        drop(l, CT_LINK_CLOCK_ERROR, l->last_ms, true);
        return false;
    }
    l->last_ms = now;
    if (l->state == CT_LINK_HALTED) return false;
    ct_link_error error = CT_LINK_NO_ERROR;
    if (l->state == CT_LINK_CONNECTING && now - l->phase_ms >= l->limits.connect_ms)
        error = CT_LINK_CONNECT_TIMEOUT;
    else if (l->state == CT_LINK_HANDSHAKE && now - l->phase_ms >= l->limits.handshake_ms)
        error = CT_LINK_HANDSHAKE_TIMEOUT;
    else if (l->state == CT_LINK_ONLINE) {
        if (l->tx_pending && now - l->tx_started_ms >= l->limits.send_ms)
            error = CT_LINK_SEND_TIMEOUT;
        else if ((l->message_open || l->frame_open) && now - l->fragment_started_ms >= l->limits.fragment_ms)
            error = CT_LINK_FRAGMENT_TIMEOUT;
    }
    if (error != CT_LINK_NO_ERROR) { drop(l, error, now, false); return false; }
    return true;
}

bool ct_link_init(ct_link *l, ct_runtime *r, ct_link_limits limits)
{
    if (!l) return false;
    memset(l, 0, sizeof(*l));
    if (!r || !r->started || r->faults || !r->protocol || r->protocol->session ||
        !limits.connect_ms || !limits.handshake_ms || !limits.fragment_ms ||
        !limits.send_ms || !limits.retry_ms) return false;
    l->runtime = r;
    l->limits = limits;
    l->last_ms = r->control.last_now_ms;
    l->valid = true;
    ct_inbox_init(&l->inbox);
    return true;
}

uint64_t ct_link_begin(ct_link *l, uint64_t now)
{
    if (!advance(l, now)) return 0;
    if ((l->state != CT_LINK_DOWN && l->state != CT_LINK_BACKOFF) ||
        l->close_required || l->disconnect_pending || l->runtime->faults) return 0;
    if (l->state == CT_LINK_BACKOFF && now - l->phase_ms < l->limits.retry_ms) return 0;
    if (l->attempt == UINT64_MAX) { drop(l, CT_LINK_EXHAUSTED, now, true); return 0; }
    ++l->attempt;
    l->state = CT_LINK_CONNECTING;
    l->phase_ms = now;
    return l->attempt;
}

bool ct_link_connected(ct_link *l, uint64_t attempt, uint64_t now)
{
    if (!current(l, attempt) || l->state != CT_LINK_CONNECTING || !advance(l, now)) return false;
    l->state = CT_LINK_HANDSHAKE;
    l->phase_ms = now;
    return true;
}

bool ct_link_ready(ct_link *l, uint64_t attempt, uint64_t now)
{
    if (!current(l, attempt) || l->state != CT_LINK_HANDSHAKE || l->ready_pending || !advance(l, now)) return false;
    l->ready_pending = true;
    return true;
}

void ct_link_closed(ct_link *l, uint64_t attempt, uint64_t now)
{
    if (!current(l, attempt)) return;
    if ((l->state == CT_LINK_BACKOFF || l->state == CT_LINK_HALTED) && !l->close_required) return;
    (void)advance(l, now);
    if (l->state != CT_LINK_BACKOFF && l->state != CT_LINK_HALTED)
        drop(l, CT_LINK_DISCONNECTED, now, false);
    l->close_required = false; /* Also acknowledges an already-requested abort. */
}

static bool reject(ct_link *l, ct_link_error reason, uint64_t now)
{
    drop(l, reason, now, false);
    return false;
}

bool ct_link_receive(ct_link *l, uint64_t attempt, ct_ws_chunk c, ct_action_proof proof, uint64_t now)
{
    if (!current(l, attempt) || l->state != CT_LINK_ONLINE || !advance(l, now)) return false;
    bool control = c.opcode == CT_WS_CLOSE || c.opcode == CT_WS_PING || c.opcode == CT_WS_PONG;
    if (c.opcode != CT_WS_TEXT && c.opcode != CT_WS_CONT && !control)
        return reject(l, CT_LINK_UNSUPPORTED, now);
    if (c.total > (control ? 125u : CT_RPC_FRAME_MAX)) return reject(l, CT_LINK_OVERSIZE, now);
    if (c.offset > c.total || c.length > c.total - c.offset || (c.length && !c.data) ||
        (!c.length && c.total) || (control && !c.fin)) return reject(l, CT_LINK_FRAME_ERROR, now);
    if (!l->frame_open) {
        if (c.offset) return reject(l, CT_LINK_FRAME_ERROR, now);
        if (control && !l->message_open) l->fragment_started_ms = now;
        if (!control) {
            if ((c.opcode == CT_WS_TEXT && l->message_open) || (c.opcode == CT_WS_CONT && !l->message_open))
                return reject(l, CT_LINK_FRAME_ERROR, now);
            if (c.opcode == CT_WS_TEXT) {
                l->message_open = true;
                l->message_length = 0;
                l->fragment_started_ms = now;
                l->delivery = (ct_rpc_delivery){l->runtime->protocol->session, now,
                                               l->runtime->control.enable_generation, proof};
            }
            if (c.total > CT_RPC_FRAME_MAX - l->message_length) return reject(l, CT_LINK_OVERSIZE, now);
        }
        l->frame_open = true;
        l->frame_opcode = c.opcode;
        l->frame_fin = c.fin;
        l->frame_total = c.total;
        l->frame_received = 0;
    } else if (c.opcode != l->frame_opcode || c.fin != l->frame_fin || c.total != l->frame_total) {
        return reject(l, CT_LINK_FRAME_ERROR, now);
    }
    if (c.offset != l->frame_received) return reject(l, CT_LINK_FRAME_ERROR, now);
    if (!control && c.length) {
        memcpy(l->message + l->message_length, c.data, c.length);
        l->message_length += c.length;
    }
    l->frame_received += c.length;
    if (l->frame_received != l->frame_total) return true;
    l->frame_open = false;
    if (c.opcode == CT_WS_CLOSE) return reject(l, CT_LINK_DISCONNECTED, now);
    if (control || !c.fin) return true; /* Ping/pong do not finish or renew text. */
    l->message[l->message_length] = '\0';
    if (ct_inbox_push(&l->inbox, l->message, l->message_length, l->delivery) != CT_INBOX_OK)
        return reject(l, CT_LINK_QUEUE_ERROR, now);
    l->message_open = false;
    l->message_length = 0;
    return true;
}

bool ct_link_take_tx(ct_link *l, ct_link_tx *tx, uint64_t now)
{
    if (!l || !l->valid || !tx || !l->tx_pending || l->tx_taken || l->state != CT_LINK_ONLINE) return false;
    if (!advance(l, now)) return false;
    *tx = l->tx;
    l->tx_taken = true;
    return true;
}

bool ct_link_sent(ct_link *l, uint64_t attempt, uint64_t id, bool success, size_t bytes, uint64_t now)
{
    /* Stale acknowledgements cannot affect a newer response or its clock. */
    if (!current(l, attempt) || !l->tx_pending || id != l->tx.id) return false;
    if (!advance(l, now) || l->state != CT_LINK_ONLINE) return false;
    if (!l->tx_taken || !success || bytes != l->tx.length) return reject(l, CT_LINK_SEND_ERROR, now);
    l->tx_pending = l->tx_taken = false;
    memset(&l->tx, 0, sizeof(l->tx));
    return true;
}

bool ct_link_service(ct_link *l, uint64_t now)
{
    if (!l || !l->valid) return false;
    (void)advance(l, now);
    ct_runtime_event event = {.kind = CT_EVENT_IDLE};
    if (l->disconnect_pending) {
        (void)ct_inbox_take(&l->inbox, &l->item); /* Consume priority disconnect. */
        event.kind = CT_EVENT_DISCONNECT;
        l->disconnect_pending = false;
    } else if (l->ready_pending) {
        event.kind = CT_EVENT_CONNECT;
        l->ready_pending = false;
    } else if (l->state == CT_LINK_ONLINE && !l->tx_pending) {
        event.kind = ct_inbox_take(&l->inbox, &l->item);
        event.frame = l->item.frame;
        event.length = l->item.length;
        event.delivery = l->item.delivery;
    }
    if (!ct_runtime_step(l->runtime, &event, &l->response)) {
        drop(l, CT_LINK_RUNTIME_ERROR, l->last_ms, true);
        return false;
    }
    /* Board callbacks may consume time. Never release a response after a link
     * deadline crossed inside runtime; apply resulting disconnect this cycle. */
    if (!advance(l, l->runtime->control.last_now_ms)) {
        if (l->disconnect_pending) {
            (void)ct_inbox_take(&l->inbox, &l->item);
            l->disconnect_pending = false;
            ct_runtime_event closed = {.kind = CT_EVENT_DISCONNECT};
            if (!ct_runtime_step(l->runtime, &closed, &l->response)) {
                drop(l, CT_LINK_RUNTIME_ERROR, l->last_ms, true);
                return false;
            }
        }
        return l->state != CT_LINK_HALTED;
    }
    if (event.kind == CT_EVENT_CONNECT) {
        if (!ct_inbox_bind(&l->inbox, l->runtime->protocol->session)) {
            drop(l, CT_LINK_RUNTIME_ERROR, l->last_ms, true);
            return false;
        }
        l->state = CT_LINK_ONLINE;
    }
    if (l->state == CT_LINK_ONLINE && l->response.result == CT_RPC_RESPONSE) {
        if (l->tx_generation == UINT64_MAX) {
            drop(l, CT_LINK_EXHAUSTED, l->last_ms, true);
            /* An action may just have been accepted; revoke it before return. */
            ct_runtime_event closed = {.kind = CT_EVENT_DISCONNECT};
            (void)ct_runtime_step(l->runtime, &closed, &l->response);
            return false;
        }
        l->tx.id = ++l->tx_generation;
        l->tx.attempt = l->attempt;
        l->tx.length = strlen(l->response.reply);
        memcpy(l->tx.frame, l->response.reply, l->tx.length + 1);
        l->tx_started_ms = l->last_ms;
        l->tx_pending = true;
        l->tx_taken = false;
    }
    return l->state != CT_LINK_HALTED;
}
