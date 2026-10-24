#ifndef LINX_WATER_MCP_H
#define LINX_WATER_MCP_H
#include "cybertrack/protocol.h"
#include "water_policy.h"
/* Hardware callbacks are bounded, serialized policy operations; never network I/O. */
typedef struct {
    water_policy (*snapshot)(void);
    void (*stop)(void);
    const char *(*request)(const char *token, uint32_t duration);
} water_callbacks;
ct_rpc_result water_mcp_handle(ct_protocol *p, const char *frame, size_t size,
    ct_rpc_delivery delivery, uint64_t now, char *reply, size_t cap, water_callbacks cb);
#endif
