#include "cybertrack/runtime.h"

#include <string.h>

static bool is_off(ct_output output)
{
    return output.left_level == 0 && output.right_level == 0 && !output.water && !output.bubbles;
}

static bool force_off(ct_runtime *r)
{
    r->off_acknowledged = r->io.force_off && r->io.force_off(r->io.context);
    if (!r->off_acknowledged) r->faults |= CT_RUNTIME_OFF_FAILED;
    return r->off_acknowledged;
}

static bool fail(ct_runtime *r, uint32_t reason)
{
    r->faults |= reason;
    ct_set_fault(&r->control, true);
    ct_protocol_close(r->protocol, r->control.last_now_ms);
    (void)force_off(r);
    return false;
}

static bool read_clock(ct_runtime *r, uint64_t *now)
{
    if (!r->io.now_ms(r->io.context, now) || *now < r->control.last_now_ms) {
        return fail(r, CT_RUNTIME_CLOCK);
    }
    (void)ct_tick(&r->control, *now);
    return true;
}

static bool check_time(ct_runtime *r, uint64_t start, uint64_t *now)
{
    if (!read_clock(r, now)) return false;
    if (*now - start > r->max_cycle_ms) return fail(r, CT_RUNTIME_SCHEDULING);
    return true;
}

static bool sample_inputs(ct_runtime *r, bool allow_enable, uint64_t now)
{
    ct_local_inputs inputs = {0};
    if (!r->io.read_inputs(r->io.context, &inputs)) return fail(r, CT_RUNTIME_INPUT);
    bool was_blocked = r->control.stop_held || r->control.fault_present;
    bool rising = inputs.enable_button && !r->previous_enable;
    r->previous_enable = inputs.enable_button;
    ct_set_stop(&r->control, inputs.stop);
    ct_set_fault(&r->control, inputs.fault);
    if (allow_enable && rising && !was_blocked && !inputs.stop && !inputs.fault) {
        (void)ct_local_enable(&r->control, now);
    }
    return true;
}

/* Poll safety inputs before a write and again after it. No enable is accepted
 * during these polls: a press overlapping a safety event must be released. */
static bool finish_cycle(ct_runtime *r, uint64_t start)
{
    uint64_t now;
    if (!sample_inputs(r, false, r->control.last_now_ms) || !check_time(r, start, &now)) return false;
    if (is_off(r->control.output)) {
        if (!force_off(r)) return fail(r, CT_RUNTIME_OFF_FAILED);
    } else {
        r->off_acknowledged = false;
        if (!r->io.write_outputs(r->io.context, &r->control.output)) return fail(r, CT_RUNTIME_OUTPUT);
    }
    if (!sample_inputs(r, false, now) || !check_time(r, start, &now)) return false;
    /* A callback may consume time or observe a stop during output application. */
    if (is_off(r->control.output) && !r->off_acknowledged) {
        if (!force_off(r)) return fail(r, CT_RUNTIME_OFF_FAILED);
        if (!check_time(r, start, &now)) return false;
    }
    if (!r->io.watchdog_kick(r->io.context)) return fail(r, CT_RUNTIME_WATCHDOG);
    if (!sample_inputs(r, false, now) || !check_time(r, start, &now)) return false;
    if (is_off(r->control.output) && !r->off_acknowledged) {
        if (!force_off(r)) return fail(r, CT_RUNTIME_OFF_FAILED);
        if (!check_time(r, start, &now)) return false;
    }
    r->last_cycle_start_ms = start;
    return true;
}

bool ct_runtime_init(ct_runtime *r, ct_protocol *protocol, ct_board_io io,
                     ct_limits limits, uint32_t queue_ms, uint32_t max_cycle_ms)
{
    if (!r || !protocol) return false;
    memset(r, 0, sizeof(*r));
    r->protocol = protocol;
    r->io = io;
    r->max_cycle_ms = max_cycle_ms;
    ct_init(&r->control, limits, 0);
    ct_protocol_init(protocol, &r->control, queue_ms);
    /* Shutdown is attempted even if the rest of the adapter is incomplete. */
    if (!force_off(r)) return fail(r, CT_RUNTIME_OFF_FAILED);
    if (!max_cycle_ms || !io.self_test || !io.now_ms || !io.read_inputs ||
        !io.write_outputs || !io.watchdog_kick) return fail(r, CT_RUNTIME_CONFIG);
    if (!io.self_test(io.context)) return fail(r, CT_RUNTIME_SELF_TEST);
    uint64_t now;
    if (!read_clock(r, &now) || !sample_inputs(r, false, now)) return false;
    (void)ct_boot_complete(&r->control);
    /* Self-test ran with outputs off, before periodic control/watchdog service.
     * The platform must separately bound startup and configure its boot WDT. */
    if (!finish_cycle(r, now)) return false;
    r->started = true;
    return true;
}

bool ct_runtime_step(ct_runtime *r, const ct_runtime_event *event,
                     ct_runtime_response *response)
{
    if (response) {
        response->result = CT_RPC_NO_RESPONSE;
        response->reply[0] = '\0';
    }
    if (!r || !r->protocol) return false;
    if (!r->started || r->faults) return fail(r, r->faults ? r->faults : CT_RUNTIME_CONFIG);
    uint64_t now;
    if (!check_time(r, r->last_cycle_start_ms, &now)) return false;
    uint64_t start = now;
    if (!sample_inputs(r, true, now) || !check_time(r, start, &now)) return false;
    /* Cancel a timed-out/stopped target before parsing any potentially costly
     * message. This off path is independent of cache or request validity. */
    if (is_off(r->control.output) && !force_off(r)) return fail(r, CT_RUNTIME_OFF_FAILED);
    if (!check_time(r, start, &now)) return false;
    if (event) {
        switch (event->kind) {
        case CT_EVENT_IDLE:
            break;
        case CT_EVENT_CONNECT:
            if (!ct_protocol_open(r->protocol, now)) return fail(r, CT_RUNTIME_CLOCK);
            break;
        case CT_EVENT_DISCONNECT:
            ct_protocol_close(r->protocol, now);
            break;
        case CT_EVENT_MESSAGE:
            if (!response || !event->frame) return fail(r, CT_RUNTIME_CONFIG);
            response->result = ct_protocol_handle(r->protocol, event->frame, event->length,
                event->delivery, now, response->reply, sizeof(response->reply));
            if (response->result == CT_RPC_BAD_ARGUMENT) return fail(r, CT_RUNTIME_CONFIG);
            break;
        default:
            return fail(r, CT_RUNTIME_CONFIG);
        }
    }
    if (finish_cycle(r, start)) return true;
    /* An accepted logical target is not an acknowledgement of a failed write.
     * fail() also closed the session and discarded cached acceptance replies. */
    if (response) {
        response->result = CT_RPC_NO_RESPONSE;
        response->reply[0] = '\0';
    }
    return false;
}
