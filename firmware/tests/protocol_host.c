/* Test-only line transport. Local control directives are not MCP methods and
 * must never be exposed to a network connection. No hardware is linked. */
#include "cybertrack/protocol.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static ct_controller control;
static ct_protocol protocol;
static char reply[CT_RPC_REPLY_CAP];

int main(int argc, char **argv)
{
    bool synthetic = argc > 1 && strcmp(argv[1], "--synthetic-limits") == 0;
    uint32_t budget = argc > 2 ? (uint32_t)strtoul(argv[2], NULL, 10) : 50;
    ct_limits limits = synthetic ? (ct_limits){1000, 200, 300, 3} : (ct_limits){0};
    ct_init(&control, limits, 0);
    ct_protocol_init(&protocol, &control, budget);
    char line[8192];
    while (fgets(line, sizeof(line), stdin)) {
        size_t length = strlen(line);
        if (length && line[length - 1] == '\n') line[--length] = '\0';
        reply[0] = '\0';
        int result = 0;
        uint64_t now, received, session, enable_generation;
        unsigned value, fresh;
        if (strcmp(line, "boot") == 0) result = ct_boot_complete(&control);
        else if (sscanf(line, "open %" SCNu64, &now) == 1) {
            result = ct_protocol_open(&protocol, now) ? 0 : -1;
        } else if (sscanf(line, "close %" SCNu64, &now) == 1) {
            ct_protocol_close(&protocol, now);
        } else if (sscanf(line, "enable %" SCNu64, &now) == 1) {
            result = ct_local_enable(&control, now);
        } else if (sscanf(line, "tick %" SCNu64, &now) == 1) {
            result = ct_tick(&control, now);
        } else if (sscanf(line, "stop %u", &value) == 1) {
            ct_set_stop(&control, value != 0);
        } else if (sscanf(line, "fault %u", &value) == 1) {
            ct_set_fault(&control, value != 0);
        } else if (sscanf(line, "frame %" SCNu64 " %" SCNu64 " %" SCNu64 " %u %" SCNu64,
                          &session, &received, &now, &fresh, &enable_generation) == 5) {
            char *frame = strchr(line, '\t');
            if (!frame) return 2;
            ++frame;
            ct_rpc_delivery delivery = {session, received, enable_generation, fresh != 0};
            result = ct_protocol_handle(&protocol, frame, strlen(frame), delivery, now, reply, sizeof(reply));
        } else if (strcmp(line, "small-buffer") == 0) {
            ct_rpc_delivery delivery = {protocol.session, control.last_now_ms, control.enable_generation, true};
            result = ct_protocol_handle(&protocol, "{}", 2, delivery, control.last_now_ms, reply, 1);
        } else if (strcmp(line, "null-request") == 0) {
            ct_rpc_delivery delivery = {protocol.session, control.last_now_ms, control.enable_generation, true};
            result = ct_protocol_handle(&protocol, NULL, 0, delivery, control.last_now_ms, reply, sizeof(reply));
        } else return 2;
        printf("{\"api_result\":%d,\"session\":%" PRIu64 ",\"state\":%d,\"fault\":%d,"
               "\"left\":%d,\"right\":%d,\"water\":%s,\"bubbles\":%s,\"ends_at\":%" PRIu64 ","
               "\"sequence\":%" PRIu64 ",\"enable_generation\":%" PRIu64 ",\"cache_count\":%zu,\"initialized\":%s,\"adapter_bytes\":%zu,\"reply\":%s}\n",
               result, protocol.session, control.state, control.fault,
               control.output.left_level, control.output.right_level,
               control.output.water ? "true" : "false", control.output.bubbles ? "true" : "false",
               control.ends_at_ms, protocol.sequence, control.enable_generation, protocol.cache_count,
               protocol.initialized ? "true" : "false", sizeof(protocol), reply[0] ? reply : "null");
        fflush(stdout);
    }
    return ferror(stdin) ? 1 : 0;
}
