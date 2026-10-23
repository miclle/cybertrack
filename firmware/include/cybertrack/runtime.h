#ifndef CYBERTRACK_RUNTIME_H
#define CYBERTRACK_RUNTIME_H

#include "cybertrack/protocol.h"

/* Board adapter returns normalized, debounced local levels. It must latch brief
 * stop/fault assertions until sampled. inputs.h provides a portable filter for
 * captured observations; physical capture remains the adapter's responsibility.
 * No GPIO numbers or active levels here. */
typedef struct {
    bool stop;
    bool fault;
    bool enable_button;
} ct_local_inputs;

typedef struct {
    void *context;
    bool (*force_off)(void *context);
    bool (*self_test)(void *context); /* Must never enable an actuator. */
    bool (*now_ms)(void *context, uint64_t *now);
    bool (*read_inputs)(void *context, ct_local_inputs *inputs);
    bool (*write_outputs)(void *context, const ct_output *output);
    bool (*watchdog_kick)(void *context);
} ct_board_io;

typedef enum {
    CT_RUNTIME_CONFIG = 1u << 0,
    CT_RUNTIME_SELF_TEST = 1u << 1,
    CT_RUNTIME_CLOCK = 1u << 2,
    CT_RUNTIME_SCHEDULING = 1u << 3,
    CT_RUNTIME_INPUT = 1u << 4,
    CT_RUNTIME_OUTPUT = 1u << 5,
    CT_RUNTIME_OFF_FAILED = 1u << 6,
    CT_RUNTIME_WATCHDOG = 1u << 7,
    CT_RUNTIME_FRESHNESS = 1u << 8
} ct_runtime_fault;

typedef enum { CT_EVENT_IDLE, CT_EVENT_CONNECT, CT_EVENT_DISCONNECT, CT_EVENT_MESSAGE } ct_event_kind;

typedef struct {
    ct_event_kind kind;
    const char *frame;
    size_t length;
    ct_rpc_delivery delivery; /* Original trusted ingress metadata, unchanged. */
} ct_runtime_event;

typedef struct {
    ct_rpc_result result;
    char reply[CT_RPC_REPLY_CAP];
} ct_runtime_response;

/* Single-owner API; no ISR/network thread may call it concurrently. Protocol
 * storage is supplied separately so its large cache never goes on a task stack.
 * fields are diagnostics, not configuration setters or physical feedback. */
typedef struct {
    ct_controller control;
    ct_protocol *protocol;
    ct_board_io io;
    uint32_t max_cycle_ms;
    uint32_t faults; /* Runtime faults latch until a new boot; no remote reset. */
    uint64_t last_cycle_start_ms;
    bool started;
    bool previous_enable;
    bool off_acknowledged; /* Only the board callback's return, not measurement. */
} ct_runtime;

/* Once per boot. Calls force_off before self_test, input handling or any output.
 * Zero cycle budget / missing callback fails closed; limits remain caller-owned
 * evidence and default to zero. There is deliberately no default board adapter. */
bool ct_runtime_init(ct_runtime *r, ct_protocol *protocol, ct_board_io io,
                     ct_limits limits, uint32_t queue_ms, uint32_t max_cycle_ms);

/* One bounded iteration. NULL event means idle tick; periodic idle calls are
 * required even without network traffic. For messages response must be non-NULL.
 * true means runtime infrastructure remained healthy, not action acceptance.
 * On false: best-effort off, close session, suppress reply, never kick again.
 * Send a returned response only after this function returns true. */
bool ct_runtime_step(ct_runtime *r, const ct_runtime_event *event,
                     ct_runtime_response *response);

#endif
