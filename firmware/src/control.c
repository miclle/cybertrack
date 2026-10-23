#include "cybertrack/control.h"

#include <string.h>

static void clear_output(ct_controller *c)
{
    c->output = (ct_output){0};
    c->ends_at_ms = 0;
}

static void trip(ct_controller *c, ct_fault reason)
{
    clear_output(c);
    /* An input during boot must not bypass the explicit self-test gate. */
    if (c->state != CT_BOOT) {
        c->state = CT_FAULT;
    }
    c->fault = reason;
}

void ct_init(ct_controller *c, ct_limits limits, uint64_t now_ms)
{
    memset(c, 0, sizeof(*c));
    c->state = CT_BOOT;
    c->limits = limits;
    c->last_now_ms = now_ms;
}

ct_result ct_boot_complete(ct_controller *c)
{
    if (c->state != CT_BOOT) {
        return CT_NOT_READY;
    }
    c->state = (c->stop_held || c->fault_present || c->fault != CT_NO_FAULT)
        ? CT_FAULT : CT_DISARMED;
    return CT_OK;
}

ct_result ct_tick(ct_controller *c, uint64_t now_ms)
{
    if (now_ms < c->last_now_ms) {
        trip(c, CT_CLOCK_FAULT);
        return CT_CLOCK_ERROR;
    }
    c->last_now_ms = now_ms;
    if (c->state == CT_ACTIVE && now_ms >= c->ends_at_ms) {
        clear_output(c);
        c->state = CT_READY;
    }
    return CT_OK;
}

ct_result ct_set_session(ct_controller *c, uint64_t session, uint64_t now_ms)
{
    ct_result result = ct_tick(c, now_ms);
    if (result != CT_OK) {
        return result;
    }
    if (session == c->session) {
        return CT_OK;
    }
    if (c->state == CT_ACTIVE) {
        trip(c, CT_SESSION_LOST);
    } else if (c->state == CT_READY) {
        clear_output(c);
        c->state = CT_DISARMED;
    }
    c->session = session;
    c->last_sequence = 0;
    return CT_OK;
}

void ct_stop(ct_controller *c)
{
    trip(c, CT_STOPPED);
}

void ct_set_stop(ct_controller *c, bool held)
{
    c->stop_held = held;
    if (held) {
        ct_stop(c);
    }
}

void ct_set_fault(ct_controller *c, bool present)
{
    c->fault_present = present;
    if (present) {
        trip(c, CT_EXTERNAL_FAULT);
    }
}

ct_result ct_local_enable(ct_controller *c, uint64_t now_ms)
{
    ct_result result = ct_tick(c, now_ms);
    if (result != CT_OK) {
        return result;
    }
    if (c->state == CT_BOOT || c->state == CT_ACTIVE || c->stop_held ||
        c->fault_present || c->session == 0 || c->enable_generation == UINT64_MAX) {
        return CT_NOT_READY;
    }
    clear_output(c);
    ++c->enable_generation;
    c->fault = CT_NO_FAULT;
    c->state = CT_READY;
    return CT_OK;
}

ct_result ct_submit(ct_controller *c, const ct_request *r, uint64_t now_ms)
{
    ct_result result = ct_tick(c, now_ms);
    if (result != CT_OK) {
        return result;
    }
    if (r == NULL) {
        return CT_INVALID;
    }
    if (c->session == 0 || r->session != c->session) {
        return CT_SESSION_MISMATCH;
    }
    if (r->sequence == 0 || r->sequence <= c->last_sequence) {
        return CT_REPLAY;
    }
    /* Consume even rejected requests: they cannot become executable after a
     * later enable or timeout. Transport retries must reuse this sequence. */
    c->last_sequence = r->sequence;
    if (now_ms >= r->expires_at_ms) {
        return CT_EXPIRED;
    }
    if (c->state == CT_ACTIVE) {
        return CT_BUSY;
    }
    if (c->state != CT_READY) {
        return CT_NOT_READY;
    }

    uint32_t maximum;
    ct_output output = {0};
    switch (r->action) {
    case CT_MOVE:
        maximum = c->limits.move_max_ms;
        if (maximum == 0 || c->limits.max_speed_level == 0) {
            return CT_UNAVAILABLE;
        }
        if (r->speed_level == 0 || r->speed_level > c->limits.max_speed_level) {
            return CT_INVALID;
        }
        switch (r->direction) {
        case CT_FORWARD:
            output.left_level = r->speed_level;
            output.right_level = r->speed_level;
            break;
        case CT_BACKWARD:
            output.left_level = -(int16_t)r->speed_level;
            output.right_level = -(int16_t)r->speed_level;
            break;
        case CT_LEFT:
            output.left_level = -(int16_t)r->speed_level;
            output.right_level = r->speed_level;
            break;
        case CT_RIGHT:
            output.left_level = r->speed_level;
            output.right_level = -(int16_t)r->speed_level;
            break;
        default:
            return CT_INVALID;
        }
        break;
    case CT_WATER:
        maximum = c->limits.water_max_ms;
        output.water = true;
        break;
    case CT_BUBBLES:
        maximum = c->limits.bubbles_max_ms;
        output.bubbles = true;
        break;
    default:
        return CT_INVALID;
    }
    if (maximum == 0) {
        return CT_UNAVAILABLE;
    }
    if (r->duration_ms == 0 || r->duration_ms > maximum ||
        now_ms > UINT64_MAX - r->duration_ms) {
        return CT_INVALID;
    }
    c->output = output;
    c->ends_at_ms = now_ms + r->duration_ms;
    c->state = CT_ACTIVE;
    return CT_OK;
}
