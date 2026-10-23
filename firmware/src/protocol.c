#include "cybertrack/protocol.h"
#include "cybertrack/replay_log.h"
#include "yyjson.h"

#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#define MCP_VERSION "2024-11-05"
#define MAX_DEPTH 16
#define SAFE_ID_MAX UINT64_C(9007199254740991)

typedef struct {
    char *data;
    size_t capacity;
    size_t length;
    bool failed;
} writer;

static void append(writer *w, const char *format, ...)
{
    if (w->failed) return;
    va_list args;
    va_start(args, format);
    int n = vsnprintf(w->data + w->length, w->capacity - w->length, format, args);
    va_end(args);
    if (n < 0 || (size_t)n >= w->capacity - w->length) {
        w->failed = true;
        return;
    }
    w->length += (size_t)n;
}

static void quote(writer *w, const char *text, size_t length)
{
    append(w, "\"");
    for (size_t i = 0; i < length; ++i) {
        unsigned char ch = (unsigned char)text[i];
        if (ch == '"' || ch == '\\') append(w, "\\%c", ch);
        else if (ch < 0x20) append(w, "\\u%04x", (unsigned)ch);
        else append(w, "%c", ch);
    }
    append(w, "\"");
}

static bool str_is(const yyjson_val *v, const char *s)
{
    return yyjson_equals_str(v, s);
}

/* yyjson validates syntax/UTF-8. This additional pass rejects ambiguous keys,
 * embedded NULs, and excessive depth, including inside otherwise ignored data. */
static bool unambiguous(const yyjson_val *v, unsigned depth)
{
    if (depth > MAX_DEPTH) return false;
    if (yyjson_is_str(v)) {
        return memchr(yyjson_get_str(v), 0, yyjson_get_len(v)) == NULL;
    }
    size_t i, n;
    yyjson_val *key, *child;
    if (yyjson_is_obj(v)) {
        yyjson_obj_foreach(v, i, n, key, child) {
            if (!unambiguous(key, depth + 1) || !unambiguous(child, depth + 1)) return false;
            /* obj_get returns the first occurrence, even for escaped keys. */
            if (yyjson_obj_getn(v, yyjson_get_str(key), yyjson_get_len(key)) != child) return false;
        }
    } else if (yyjson_is_arr(v)) {
        yyjson_arr_foreach(v, i, n, child) {
            if (!unambiguous(child, depth + 1)) return false;
        }
    }
    return true;
}

static bool only_keys(const yyjson_val *obj, const char *const *allowed, size_t count)
{
    if (!yyjson_is_obj(obj)) return false;
    size_t i, n;
    yyjson_val *key, *value;
    yyjson_obj_foreach(obj, i, n, key, value) {
        (void)value;
        bool found = false;
        for (size_t j = 0; j < count; ++j) found |= str_is(key, allowed[j]);
        if (!found) return false;
    }
    return true;
}

static bool digits(const char *s, size_t length, uint64_t maximum, uint64_t *out)
{
    if (length == 0) return false;
    uint64_t value = 0;
    for (size_t i = 0; i < length; ++i) {
        if (s[i] < '0' || s[i] > '9') return false;
        unsigned d = (unsigned)(s[i] - '0');
        if (value > maximum / 10 || (value == maximum / 10 && d > maximum % 10)) return false;
        value = value * 10 + d;
    }
    *out = value;
    return true;
}

static bool positive_integer(const yyjson_val *v, uint64_t maximum, uint64_t *out)
{
    return yyjson_is_raw(v) && digits(yyjson_get_raw(v), yyjson_get_len(v), maximum, out) && *out > 0;
}

static bool encode_id(const yyjson_val *v, char id[CT_RPC_ID_CAP])
{
    writer w = {id, CT_RPC_ID_CAP, 0, false};
    if (yyjson_is_str(v) && yyjson_get_len(v) <= CT_RPC_ID_MAX) {
        quote(&w, yyjson_get_str(v), yyjson_get_len(v));
        return !w.failed;
    }
    if (!yyjson_is_raw(v)) return false;
    const char *raw = yyjson_get_raw(v);
    size_t length = yyjson_get_len(v);
    bool negative = length > 0 && raw[0] == '-';
    uint64_t value;
    if (!digits(raw + negative, length - negative, SAFE_ID_MAX, &value)) return false;
    append(&w, "%s%" PRIu64, negative && value != 0 ? "-" : "", value);
    return !w.failed;
}

static void begin(writer *w, const char *id)
{
    append(w, "{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\",\"id\":%s,", id);
}

static void rpc_error(writer *w, const char *id, int code, const char *message)
{
    begin(w, id);
    append(w, "\"error\":{\"code\":%d,\"message\":", code);
    quote(w, message, strlen(message));
    append(w, "}}}");
}

static void tool_result(writer *w, const char *id, bool error, const char *text)
{
    begin(w, id);
    append(w, "\"result\":{\"isError\":%s,\"content\":[{\"type\":\"text\",\"text\":", error ? "true" : "false");
    quote(w, text, strlen(text));
    append(w, "}]}}}");
}

static bool empty_params(const yyjson_val *params)
{
    return params == NULL || (yyjson_is_obj(params) && yyjson_obj_size(params) == 0);
}

static bool tool_call(const yyjson_val *params, const char *name, bool no_args)
{
    static const char *const keys[] = {"name", "arguments"};
    return only_keys(params, keys, 2) && str_is(yyjson_obj_get(params, "name"), name) &&
           (!no_args || empty_params(yyjson_obj_get(params, "arguments")));
}

static bool move_available(const ct_protocol *p)
{
    return p->max_queue_ms && p->control->limits.move_max_ms && p->control->limits.max_speed_level;
}

static void tools_list(ct_protocol *p, writer *w, const char *id)
{
    begin(w, id);
    append(w, "\"result\":{\"tools\":["
           "{\"name\":\"self.tank.get_status\",\"description\":\"Read logical control state; no physical telemetry\","
           "\"inputSchema\":{\"type\":\"object\",\"properties\":{},\"additionalProperties\":false}},"
           "{\"name\":\"self.tank.stop\",\"description\":\"Cancel logical outputs and require local re-enable\","
           "\"inputSchema\":{\"type\":\"object\",\"properties\":{},\"additionalProperties\":false}}");
    if (move_available(p)) {
        append(w, ",{\"name\":\"self.tank.move\",\"description\":\"Request a bounded move; requires local enable and verified freshness\","
               "\"inputSchema\":{\"type\":\"object\",\"additionalProperties\":false,\"properties\":{"
               "\"direction\":{\"type\":\"string\",\"enum\":[\"forward\",\"backward\",\"left\",\"right\"]},"
               "\"speed_level\":{\"type\":\"integer\",\"minimum\":1,\"maximum\":%u},"
               "\"duration_ms\":{\"type\":\"integer\",\"minimum\":1,\"maximum\":%" PRIu32 "}},"
               "\"required\":[\"direction\",\"speed_level\",\"duration_ms\"]}}",
               (unsigned)p->control->limits.max_speed_level, p->control->limits.move_max_ms);
    }
    const char *names[] = {"water", "bubbles"};
    uint32_t limits[] = {p->control->limits.water_max_ms, p->control->limits.bubbles_max_ms};
    for (size_t i = 0; i < 2; ++i) {
        if (!p->max_queue_ms || !limits[i]) continue;
        append(w, ",{\"name\":\"self.tank.%s\",\"description\":\"Request a bounded effect; requires local enable and verified freshness\","
               "\"inputSchema\":{\"type\":\"object\",\"additionalProperties\":false,\"properties\":{"
               "\"duration_ms\":{\"type\":\"integer\",\"minimum\":1,\"maximum\":%" PRIu32 "}},"
               "\"required\":[\"duration_ms\"]}}", names[i], limits[i]);
    }
    append(w, "]}}}");
}

static const char *result_name(ct_result result)
{
    switch (result) {
    case CT_OK: return "accepted";
    case CT_NOT_READY: return "not_ready";
    case CT_UNAVAILABLE: return "unavailable";
    case CT_INVALID: return "invalid";
    case CT_BUSY: return "busy";
    case CT_SESSION_MISMATCH: return "session_mismatch";
    case CT_REPLAY: return "replay";
    case CT_EXPIRED: return "expired";
    case CT_CLOCK_ERROR: return "clock_error";
    }
    return "unknown";
}

static const char *state_name(ct_state state)
{
    switch (state) {
    case CT_BOOT: return "BOOT";
    case CT_DISARMED: return "DISARMED";
    case CT_READY: return "READY";
    case CT_ACTIVE: return "ACTIVE";
    case CT_FAULT: return "FAULT";
    }
    return "UNKNOWN";
}

static const char *fault_name(ct_fault fault)
{
    switch (fault) {
    case CT_NO_FAULT: return "none";
    case CT_STOPPED: return "stopped";
    case CT_EXTERNAL_FAULT: return "external_fault";
    case CT_SESSION_LOST: return "session_lost";
    case CT_CLOCK_FAULT: return "clock_fault";
    }
    return "unknown";
}

static void status_result(ct_protocol *p, writer *w, const char *id)
{
    const ct_controller *c = p->control;
    char text[512];
    writer status = {text, sizeof(text), 0, false};
    append(&status, "{\"state\":\"%s\",\"fault\":\"%s\",\"logical_output\":{"
           "\"left_level\":%d,\"right_level\":%d,\"water\":%s,\"bubbles\":%s},"
           "\"capabilities\":{\"move\":%s,\"water\":%s,\"bubbles\":%s},\"physical_feedback\":false,"
           "\"replay_guard\":{\"scope\":\"%s\",\"storage\":\"%s\",\"bits_set\":%" PRIu32 ",\"bits_total\":%u}}",
           state_name(c->state), fault_name(c->fault), c->output.left_level, c->output.right_level,
           c->output.water ? "true" : "false", c->output.bubbles ? "true" : "false",
           move_available(p) ? "true" : "false",
           p->max_queue_ms && c->limits.water_max_ms ? "true" : "false",
           p->max_queue_ms && c->limits.bubbles_max_ms ? "true" : "false",
           p->store_bound ? "persistent" : "boot",
           p->storage_fault ? "fault" : p->store_bound ? "ready" : "volatile",
           p->replay_bits_set, CT_RPC_REPLAY_BYTES * 8u);
    if (status.failed) { w->failed = true; return; }
    tool_result(w, id, false, text);
}

static void dispatch_action(ct_protocol *p, writer *w, const char *id,
                            const yyjson_val *params, ct_rpc_delivery delivery, uint64_t now)
{
    const yyjson_val *name = yyjson_obj_get(params, "name");
    const yyjson_val *args = yyjson_obj_get(params, "arguments");
    static const char *const call_keys[] = {"name", "arguments"};
    if (!only_keys(params, call_keys, 2) || !yyjson_is_str(name)) {
        rpc_error(w, id, -32602, "Invalid tool parameters");
        return;
    }
    if (str_is(name, "self.tank.get_status")) {
        if (!empty_params(args)) rpc_error(w, id, -32602, "Status takes no arguments");
        else status_result(p, w, id);
        return;
    }
    /* A malformed stop never falls through to an action. Valid stops have
     * already been handled before the initialized/cache/freshness gates. */
    if (str_is(name, "self.tank.stop")) {
        rpc_error(w, id, -32602, "Stop takes no arguments");
        return;
    }
    ct_request request = {0};
    if (str_is(name, "self.tank.move")) request.action = CT_MOVE;
    else if (str_is(name, "self.tank.water")) request.action = CT_WATER;
    else if (str_is(name, "self.tank.bubbles")) request.action = CT_BUBBLES;
    else { rpc_error(w, id, -32601, "Unknown tool"); return; }

    static const char *const move_keys[] = {"duration_ms", "direction", "speed_level"};
    uint64_t duration, speed;
    if (!only_keys(args, move_keys, request.action == CT_MOVE ? 3 : 1) ||
        !positive_integer(yyjson_obj_get(args, "duration_ms"), UINT32_MAX, &duration)) {
        rpc_error(w, id, -32602, "duration_ms must be a positive uint32 integer token");
        return;
    }
    request.duration_ms = (uint32_t)duration;
    if (request.action == CT_MOVE) {
        if (!positive_integer(yyjson_obj_get(args, "speed_level"), UINT8_MAX, &speed)) {
            rpc_error(w, id, -32602, "speed_level must be a positive uint8 integer token");
            return;
        }
        request.speed_level = (uint8_t)speed;
        const yyjson_val *direction = yyjson_obj_get(args, "direction");
        if (str_is(direction, "forward")) request.direction = CT_FORWARD;
        else if (str_is(direction, "backward")) request.direction = CT_BACKWARD;
        else if (str_is(direction, "left")) request.direction = CT_LEFT;
        else if (str_is(direction, "right")) request.direction = CT_RIGHT;
        else { rpc_error(w, id, -32602, "Unknown direction"); return; }
    }
    if (delivery.enable_generation != p->control->enable_generation) {
        tool_result(w, id, true, "stale_local_enable");
        return;
    }
    if (delivery.received_at_ms > now || delivery.received_at_ms > UINT64_MAX - p->max_queue_ms) {
        tool_result(w, id, true, "invalid_receive_time");
        return;
    }
    if (!p->max_queue_ms || !delivery.proof.intent || !delivery.proof.window) {
        tool_result(w, id, true, "freshness_unverified");
        return;
    }
    ct_fresh_result fresh = ct_freshness_check(&p->freshness, delivery.proof, p->session,
        p->control->enable_generation, delivery.received_at_ms, now);
    if (fresh != CT_FRESH) {
        tool_result(w, id, true, fresh == CT_FRESH_EXPIRED ? "expired" : "freshness_unverified");
        return;
    }
    if (p->sequence == UINT64_MAX) {
        tool_result(w, id, true, "sequence_exhausted");
        return;
    }
    request.session = p->session;
    request.sequence = ++p->sequence;
    request.expires_at_ms = p->freshness.expires_at_ms;
    ct_result result = ct_submit(p->control, &request, now);
    if (result == CT_OK) p->accepted_sequence = request.sequence;
    tool_result(w, id, result != CT_OK, result_name(result));
}

static void dispatch(ct_protocol *p, writer *w, const char *id, const yyjson_val *payload,
                     ct_rpc_delivery delivery, uint64_t now, bool clock_ok)
{
    const yyjson_val *method = yyjson_obj_get(payload, "method");
    const yyjson_val *params = yyjson_obj_get(payload, "params");
    if (!clock_ok) { rpc_error(w, id, -32004, "Control clock fault"); return; }
    if (str_is(method, "initialize")) {
        static const char *const keys[] = {"protocolVersion", "capabilities", "clientInfo"};
        const yyjson_val *info = yyjson_obj_get(params, "clientInfo");
        if (!only_keys(params, keys, 3) || !str_is(yyjson_obj_get(params, "protocolVersion"), MCP_VERSION) ||
            !yyjson_is_obj(yyjson_obj_get(params, "capabilities")) || !yyjson_is_obj(info) ||
            !yyjson_is_str(yyjson_obj_get(info, "name")) || !yyjson_is_str(yyjson_obj_get(info, "version"))) {
            rpc_error(w, id, -32602, "Expected MCP 2024-11-05 initialize parameters");
        } else if (p->initialized) {
            rpc_error(w, id, -32000, "Already initialized; open a new session to renegotiate");
        } else {
            begin(w, id);
            append(w, "\"result\":{\"protocolVersion\":\"" MCP_VERSION "\",\"capabilities\":{\"tools\":{}},"
                   "\"serverInfo\":{\"name\":\"CyberTrack offline adapter\",\"version\":\"0.1.0\"}}}}");
            p->initialized = true;
        }
    } else if (str_is(method, "ping")) {
        if (!empty_params(params)) rpc_error(w, id, -32602, "Ping takes no parameters");
        else { begin(w, id); append(w, "\"result\":{}}}"); }
    } else if (str_is(method, "tools/list") || str_is(method, "tools/call")) {
        if (!p->initialized) { rpc_error(w, id, -32000, "Not initialized"); return; }
        if (str_is(method, "tools/list")) {
            if (!empty_params(params)) rpc_error(w, id, -32602, "No pagination cursor is available");
            else tools_list(p, w, id);
        } else dispatch_action(p, w, id, params, delivery, now);
    } else rpc_error(w, id, -32601, "Method not found");
}

void ct_protocol_init(ct_protocol *p, ct_controller *control, uint32_t max_queue_ms)
{
    memset(p, 0, sizeof(*p));
    p->control = control;
    p->max_queue_ms = max_queue_ms;
}

bool ct_protocol_set_allocator(ct_protocol *p, ct_rpc_allocator allocator)
{
    if (!p || !p->control || p->opened || p->session || p->cache_count ||
        !allocator.allocate || !allocator.resize || !allocator.release) return false;
    p->allocator = allocator;
    return true;
}

static bool attach_store(ct_protocol *p, ct_replay_store *store, bool guarded, bool logged)
{
    if (!p || !p->control || p->opened || p->store_bound) return false;
    p->store_bound = true;
    p->store = store;
    if (!store || (guarded && !store->anchor_bound) ||
        (logged && (!store->log || !store->log->ready)) || !ct_replay_store_check(store)) {
        p->storage_fault = true;
        ct_stop(p->control);
        return false;
    }
    p->generation = store->session;
    memcpy(p->replay_filter, store->filter, sizeof(p->replay_filter));
    p->replay_bits_set = 0;
    for (size_t i = 0; i < sizeof(p->replay_filter); ++i)
        for (unsigned j = 0; j < 8; ++j) p->replay_bits_set += (p->replay_filter[i] >> j) & 1u;
    return true;
}

bool ct_protocol_attach_store(ct_protocol *p, ct_replay_store *store)
{
    return attach_store(p, store, false, false);
}

bool ct_protocol_attach_guarded_store(ct_protocol *p, ct_replay_store *store)
{
    return attach_store(p, store, true, false);
}

bool ct_protocol_attach_logged_store(ct_protocol *p, ct_replay_store *store)
{
    return attach_store(p, store, true, true);
}

static bool persist(ct_protocol *p, uint64_t session)
{
    if (!p->store_bound) return true; /* Existing host-only volatile mode. */
    if (!p->storage_fault && ct_replay_store_save(p->store, p->replay_filter, session)) return true;
    p->storage_fault = true;
    ct_stop(p->control);
    return false;
}

static yyjson_doc *read_json(const ct_protocol *p, const char *frame, size_t length,
                             yyjson_read_err *error)
{
    yyjson_alc allocator = {p->allocator.allocate, p->allocator.resize,
                            p->allocator.release, p->allocator.context};
    /* INSITU is not enabled; yyjson does not modify this borrowed input. The
     * document copies the allocator, so this local descriptor can expire. */
    return yyjson_read_opts((char *)frame, length, YYJSON_READ_NUMBER_AS_RAW,
                            allocator.malloc ? &allocator : NULL, error);
}

bool ct_protocol_issue_window(ct_protocol *p, uint64_t now, ct_action_proof *out)
{
    if (out) *out = (ct_action_proof){0};
    if (!p || !p->control || !p->session || p->storage_fault || now < p->control->last_now_ms)
        return false;
    return ct_freshness_issue(&p->freshness, p->session, p->control->enable_generation,
                              now, p->max_queue_ms, out);
}

uint64_t ct_protocol_open(ct_protocol *p, uint64_t now_ms)
{
    p->opened = true;
    if (p->generation == UINT64_MAX) {
        ct_protocol_close(p, now_ms);
        return 0;
    }
    uint64_t next = p->generation + 1;
    /* Reserve before publishing a session. On a storage fault keep a local
     * read/stop-only connection for diagnostics, never volatile action fallback. */
    (void)persist(p, next);
    if (ct_set_session(p->control, next, now_ms) != CT_OK) {
        ct_protocol_close(p, now_ms);
        return 0;
    }
    p->generation = next;
    p->session = next;
    p->initialized = false;
    p->sequence = 0;
    p->accepted_sequence = 0;
    p->cache_count = 0;
    p->cache_next = 0;
    memset(p->cache, 0, sizeof(p->cache));
    return next;
}

void ct_protocol_close(ct_protocol *p, uint64_t now_ms)
{
    /* ct_set_session also trips on clock rollback. In that case the adapter
     * closes immediately even though the core retains its old session number. */
    (void)ct_set_session(p->control, 0, now_ms);
    p->session = 0;
    p->initialized = false;
    p->cache_count = 0;
    p->cache_next = 0;
    memset(p->cache, 0, sizeof(p->cache));
}

/* Four positions in a fixed monotone Bloom filter. Hash collisions only deny
 * actions: bits are never removed, aged, or cleared on a reconnect. This is not
 * authentication or a defense against deliberate resource exhaustion. IDs use
 * encode_id's canonical spelling, including escaped strings and numeric -0. */
static bool remember_id(ct_protocol *p, const char *id)
{
    uint64_t hash = UINT64_C(14695981039346656037);
    for (const unsigned char *s = (const unsigned char *)id; *s; ++s) {
        hash ^= *s;
        hash *= UINT64_C(1099511628211);
    }
    uint32_t position = (uint32_t)hash;
    uint32_t step = (uint32_t)(hash >> 32) | 1u;
    bool seen = true;
    for (unsigned i = 0; i < 4; ++i, position += step) {
        uint32_t bit = position % (CT_RPC_REPLAY_BYTES * 8u);
        unsigned char mask = (unsigned char)(1u << (bit % 8));
        if (!(p->replay_filter[bit / 8] & mask)) {
            seen = false;
            p->replay_filter[bit / 8] |= mask;
            ++p->replay_bits_set;
        }
    }
    return seen;
}

/* This prefix cannot be a canonical RPC ID (quoted string or decimal).
 * Preserve the v1 RPC hash mapping and storage format: adding this namespace
 * only sets additional monotone bits, so older durable IDs remain protected. */
static bool remember_intent(ct_protocol *p, ct_action_proof proof)
{
    if (!proof.intent) return false;
    char key[32];
    (void)snprintf(key, sizeof(key), "intent:%016" PRIx64, proof.intent);
    return remember_id(p, key);
}

static bool replay_safe(const yyjson_val *payload)
{
    const yyjson_val *method = yyjson_obj_get(payload, "method");
    return str_is(method, "initialize") || str_is(method, "ping") ||
           str_is(method, "tools/list") ||
           (str_is(method, "tools/call") &&
            tool_call(yyjson_obj_get(payload, "params"), "self.tank.get_status", true));
}

ct_rpc_result ct_protocol_handle(ct_protocol *p, const char *frame, size_t length,
                                ct_rpc_delivery delivery, uint64_t now_ms,
                                char *reply, size_t reply_cap)
{
    if (!p || !p->control || !frame || !reply || reply_cap < CT_RPC_REPLY_CAP) return CT_RPC_BAD_ARGUMENT;
    reply[0] = '\0';
    if (p->session == 0 || delivery.session != p->session) return CT_RPC_STALE_SESSION;
    bool clock_ok = ct_tick(p->control, now_ms) == CT_OK;
    writer w = {reply, reply_cap, 0, false};
    if (length > CT_RPC_FRAME_MAX) {
        rpc_error(&w, "null", -32600, "Frame too large");
        return CT_RPC_RESPONSE;
    }
    yyjson_read_err parse_error;
    yyjson_doc *doc = read_json(p, frame, length, &parse_error);
    if (!doc) {
        bool allocation_failed = parse_error.code == YYJSON_READ_ERROR_MEMORY_ALLOCATION;
        if (allocation_failed) ct_stop(p->control);
        rpc_error(&w, "null", allocation_failed ? -32603 : -32700,
                  allocation_failed ? "JSON allocation failed" : "Parse error");
        return CT_RPC_RESPONSE;
    }
    const yyjson_val *root = yyjson_doc_get_root(doc);
    const yyjson_val *payload = yyjson_obj_get(root, "payload");
    static const char *const root_keys[] = {"type", "payload"};
    static const char *const payload_keys[] = {"jsonrpc", "id", "method", "params"};
    if (!unambiguous(root, 0) || !only_keys(root, root_keys, 2) || !str_is(yyjson_obj_get(root, "type"), "mcp") ||
        !only_keys(payload, payload_keys, 4) || !str_is(yyjson_obj_get(payload, "jsonrpc"), "2.0") ||
        !yyjson_is_str(yyjson_obj_get(payload, "method"))) {
        rpc_error(&w, "null", -32600, "Invalid request envelope");
        yyjson_doc_free(doc);
        return CT_RPC_RESPONSE;
    }
    const yyjson_val *id_value = yyjson_obj_get(payload, "id");
    char id[CT_RPC_ID_CAP];
    bool notification = id_value == NULL;
    if (!notification && !encode_id(id_value, id)) {
        rpc_error(&w, "null", -32600, "Invalid request ID");
        yyjson_doc_free(doc);
        return CT_RPC_RESPONSE;
    }
    bool stop = str_is(yyjson_obj_get(payload, "method"), "tools/call") &&
                tool_call(yyjson_obj_get(payload, "params"), "self.tank.stop", true);
    if (stop) ct_stop(p->control);
    if (notification) {
        yyjson_doc_free(doc);
        return CT_RPC_NO_RESPONSE;
    }

    for (size_t i = 0; i < p->cache_count; ++i) {
        ct_rpc_cache_entry *entry = &p->cache[i];
        if (strcmp(entry->id, id) != 0) continue;
        yyjson_doc *previous = read_json(p, entry->frame, strlen(entry->frame), &parse_error);
        bool cache_storage_ok = true;
        if (previous && !stop && !replay_safe(payload)) {
            (void)remember_id(p, id);
            (void)remember_intent(p, delivery.proof);
            cache_storage_ok = persist(p, p->session);
        }
        if (!previous) {
            ct_stop(p->control);
            rpc_error(&w, id, -32603, parse_error.code == YYJSON_READ_ERROR_MEMORY_ALLOCATION
                ? "Cache allocation failed" : "Cache parse failure");
        }
        else if (!cache_storage_ok)
            rpc_error(&w, id, -32005, "Replay storage unavailable; actions locked");
        else if (!yyjson_equals(payload, yyjson_obj_get(yyjson_doc_get_root(previous), "payload")))
            rpc_error(&w, id, -32001, "Request ID reused with different content");
        else memcpy(reply, entry->reply, strlen(entry->reply) + 1);
        yyjson_doc_free(previous);
        yyjson_doc_free(doc);
        return CT_RPC_RESPONSE;
    }
    /* Reserve before dispatch, including rejected requests. A resident retry
     * above preserves the FIFO and may reserve a newly supplied intent. */
    bool unsafe = !stop && !replay_safe(payload);
    /* Read/stop traffic has no action to replay. Keep its ID only in the bounded
     * response cache; never spend permanent history on polling/handshakes. */
    bool seen = unsafe && remember_id(p, id);
    /* Retire even rejected/expired intents before semantic dispatch, together
     * with the RPC ID in ONE durable save. Changing the RPC ID cannot revive it. */
    if (unsafe) seen = remember_intent(p, delivery.proof) || seen;
    if (stop) tool_result(&w, id, false, "logical_outputs_cleared; local_reenable_required");
    else if (!replay_safe(payload) && !persist(p, p->session))
        rpc_error(&w, id, -32005, "Replay storage unavailable; actions locked");
    else if (seen && !replay_safe(payload))
        rpc_error(&w, id, -32002, "Action ID retired or replay filter collision; no action executed");
    else dispatch(p, &w, id, payload, delivery, now_ms, clock_ok);
    if (w.failed) {
        /* A response serialization failure after accepting a request must not
         * leave an unreported action running. All normal responses fit the cap. */
        ct_stop(p->control);
        w = (writer){reply, reply_cap, 0, false};
        rpc_error(&w, id, -32603, "Response capacity exceeded");
    }
    {
        ct_rpc_cache_entry *entry = &p->cache[p->cache_next];
        p->cache_next = (p->cache_next + 1) % CT_RPC_CACHE_SLOTS;
        if (p->cache_count < CT_RPC_CACHE_SLOTS) ++p->cache_count;
        memcpy(entry->id, id, strlen(id) + 1);
        memcpy(entry->frame, frame, length);
        entry->frame[length] = '\0';
        memcpy(entry->reply, reply, strlen(reply) + 1);
    }
    yyjson_doc_free(doc);
    return CT_RPC_RESPONSE;
}
