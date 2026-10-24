#include "water_mcp.h"
#include "yyjson.h"
#include "cJSON.h"
#include <string.h>
#include <stdio.h>

static bool str(yyjson_val *v, const char *s)
{
    return yyjson_is_str(v) && yyjson_get_len(v) == strlen(s) && !memcmp(yyjson_get_str(v), s, strlen(s));
}
static bool keys(yyjson_val *v, const char *const *allowed, size_t n)
{
    if (!yyjson_is_obj(v) || yyjson_obj_size(v) > n) return false;
    yyjson_obj_iter it = yyjson_obj_iter_with(v); yyjson_val *key;
    unsigned seen = 0;
    while ((key = yyjson_obj_iter_next(&it))) {
        size_t i;
        for (i = 0; i < n; ++i) if (str(key, allowed[i])) break;
        if (i == n || (seen & (1u << i))) return false;
        seen |= 1u << i;
    }
    return true;
}
static bool id_ok(yyjson_val *v)
{
    if (yyjson_is_uint(v)) return yyjson_get_uint(v) <= UINT64_C(9007199254740991);
    return yyjson_is_str(v) && yyjson_get_len(v) > 0 && yyjson_get_len(v) <= CT_RPC_ID_MAX &&
           !memchr(yyjson_get_str(v), 0, yyjson_get_len(v));
}
static cJSON *result(cJSON *outer)
{
    return cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(outer, "payload"), "result");
}
static bool serialize(cJSON *root, char *out, size_t cap)
{
    bool ok = root && cJSON_PrintPreallocated(root, out, (int)cap, false);
    cJSON_Delete(root);
    return ok;
}
static bool augment_status(cJSON *res, water_policy s)
{
    cJSON *item = cJSON_GetArrayItem(cJSON_GetObjectItemCaseSensitive(res, "content"), 0);
    if (!cJSON_IsObject(item)) return false;
    char status[1024];
    int length = snprintf(status, sizeof(status),
        "{\"state\":\"%s\",\"fault\":\"%s\",\"logical_output\":{\"left_level\":0,\"right_level\":0,\"water\":%s,\"bubbles\":false},"
        "\"capabilities\":{\"move\":false,\"water\":true,\"bubbles\":false},\"physical_feedback\":false,"
        "\"water_bench\":{\"local_permit_armed\":%s,\"permit_used\":%s,\"boot_held\":%s,\"max_duration_ms\":5000,\"starts_this_boot\":%u,"
        "\"authorization\":\"local_single_use_intent; no_autonomous_actions\",\"completion\":\"%s\"}}",
        s.active ? "ACTIVE" : s.armed ? "READY" : s.stopped ? "FAULT" : "DISARMED",
        s.clock_fault ? "clock_fault" : s.stopped ? "stopped" : "none",
        s.active ? "true" : "false", s.armed ? "true" : "false", s.used ? "true" : "false", s.held ? "true" : "false", s.starts,
        s.active ? "running" : s.stopped ? "stopped_or_disconnected" : s.used ? "deadline_elapsed" : "idle");
    if (length < 0 || (size_t)length >= sizeof(status)) return false;
    cJSON *text = cJSON_CreateString(status);
    if (!text) return false;
    if (!cJSON_ReplaceItemInObjectCaseSensitive(item, "text", text)) { cJSON_Delete(text); return false; }
    return true;
}

ct_rpc_result water_mcp_handle(ct_protocol *p, const char *frame, size_t size,
    ct_rpc_delivery delivery, uint64_t now, char *reply, size_t cap, water_callbacks cb)
{
    yyjson_doc *doc = yyjson_read(frame, size, 0);
    yyjson_val *root = yyjson_doc_get_root(doc);
    yyjson_val *payload = yyjson_obj_get(root, "payload");
    yyjson_val *params = yyjson_obj_get(payload, "params");
    bool water = str(yyjson_obj_get(payload, "method"), "tools/call") &&
                 str(yyjson_obj_get(params, "name"), "self.tank.water");
    bool stop = str(yyjson_obj_get(payload, "method"), "tools/call") &&
                str(yyjson_obj_get(params, "name"), "self.tank.stop");
    bool status = str(yyjson_obj_get(payload, "method"), "tools/call") &&
                  str(yyjson_obj_get(params, "name"), "self.tank.get_status");
    bool list = str(yyjson_obj_get(payload, "method"), "tools/list");
    if (stop) cb.stop(); /* Malformed stop can revoke a permit, never energize. */
    if (water) {
        static const char *const outer_keys[] = {"type", "payload"};
        static const char *const rpc_keys[] = {"jsonrpc", "id", "method", "params"};
        static const char *const param_keys[] = {"name", "arguments"};
        static const char *const arg_keys[] = {"duration_ms", "permit"};
        yyjson_val *args = yyjson_obj_get(params, "arguments");
        yyjson_val *token = yyjson_obj_get(args, "permit");
        yyjson_val *duration = yyjson_obj_get(args, "duration_ms");
        bool valid = size <= CT_RPC_FRAME_MAX && cap >= CT_RPC_REPLY_CAP && p->initialized &&
            delivery.session == p->session && p->session &&
            keys(root, outer_keys, 2) && str(yyjson_obj_get(root, "type"), "mcp") &&
            keys(payload, rpc_keys, 4) && str(yyjson_obj_get(payload, "jsonrpc"), "2.0") &&
            id_ok(yyjson_obj_get(payload, "id")) && keys(params, param_keys, 2) && keys(args, arg_keys, 2) &&
            yyjson_is_uint(duration) && yyjson_get_uint(duration) == WATER_MS &&
            yyjson_is_str(token) && yyjson_get_len(token) == WATER_TOKEN_LEN &&
            !memchr(yyjson_get_str(token), 0, WATER_TOKEN_LEN);
        /* Invalid calls use the original strict parser; it cannot start an action
         * because its limits and freshness budget stay zero. Notifications never act. */
        if (valid) {
            cJSON *input = cJSON_ParseWithLength(frame, size);
            cJSON *response = cJSON_CreateObject();
            cJSON_AddStringToObject(response, "type", "mcp");
            cJSON *body = cJSON_AddObjectToObject(response, "payload");
            cJSON_AddStringToObject(body, "jsonrpc", "2.0");
            cJSON_AddItemToObject(body, "id", cJSON_Duplicate(cJSON_GetObjectItemCaseSensitive(
                cJSON_GetObjectItemCaseSensitive(input, "payload"), "id"), true));
            cJSON *res = cJSON_AddObjectToObject(body, "result");
            cJSON *content = cJSON_AddArrayToObject(res, "content");
            cJSON *item = cJSON_CreateObject(); cJSON_AddItemToArray(content, item);
            cJSON_AddStringToObject(item, "type", "text");
            /* Allocate and verify reply capacity before consuming the intent. */
            cJSON *message = cJSON_AddStringToObject(item, "text", "duration_must_match_5000ms_intent");
            cJSON *error = cJSON_AddBoolToObject(res, "isError", true);
            bool allocated = input && response && body && res && content && item && message && error &&
                cJSON_GetObjectItemCaseSensitive(body, "id") && cJSON_GetObjectItemCaseSensitive(body, "jsonrpc") &&
                cJSON_GetObjectItemCaseSensitive(response, "type") && cJSON_GetObjectItemCaseSensitive(item, "type") && cJSON_PrintPreallocated(response, reply, (int)cap, false);
            if (allocated) {
                const char *outcome = cb.request(yyjson_get_str(token), WATER_MS);
                /* Existing buffer is large enough for every policy outcome. */
                strcpy(message->valuestring, outcome);
                error->type = !strcmp(outcome, "accepted") ? cJSON_False : cJSON_True;
            }
            cJSON_Delete(input); yyjson_doc_free(doc);
            if (!allocated || !serialize(response, reply, cap)) {
                if (!allocated) cJSON_Delete(response);
                cb.stop(); return CT_RPC_BAD_ARGUMENT;
            }
            return CT_RPC_RESPONSE;
        }
    }
    yyjson_doc_free(doc);
    ct_rpc_result r = ct_protocol_handle(p, frame, size, delivery, now, reply, cap);
    if (r != CT_RPC_RESPONSE) return r;
    cJSON *response = cJSON_Parse(reply);
    cJSON *res = result(response);
    if (list && res) {
        cJSON *tools = cJSON_GetObjectItemCaseSensitive(res, "tools");
        if (cJSON_IsArray(tools)) {
            cJSON *tool = cJSON_Parse("{\"name\":\"self.tank.water\",\"description\":\"Run one locally authorized 5-second water bench pulse. Requires the exact permit from the current user request; never invent, reuse or retry a permit. BOOT or stop cancels.\",\"inputSchema\":{\"type\":\"object\",\"properties\":{\"duration_ms\":{\"type\":\"integer\",\"enum\":[5000]},\"permit\":{\"type\":\"string\",\"minLength\":32,\"maxLength\":32}},\"required\":[\"duration_ms\",\"permit\"],\"additionalProperties\":false}}");
            if (!tool || !cJSON_AddItemToArray(tools, tool)) { cJSON_Delete(tool); cJSON_Delete(response); cb.stop(); return CT_RPC_BAD_ARGUMENT; }
        }
    }
    if (status && res && !augment_status(res, cb.snapshot())) { cJSON_Delete(response); cb.stop(); return CT_RPC_BAD_ARGUMENT; }
    if (!serialize(response, reply, cap)) { cb.stop(); return CT_RPC_BAD_ARGUMENT; }
    return r;
}
