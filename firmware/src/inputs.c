#include "cybertrack/inputs.h"

#include <string.h>

static void safety_level(bool raw, bool previous, uint64_t now, uint32_t delay,
                         uint64_t *released_at, bool *active, bool *pending)
{
    if (raw) {
        *active = true;
        *pending = true;
    } else {
        if (previous) *released_at = now;
        if (*active && now - *released_at >= delay) *active = false;
    }
}

bool ct_inputs_init(ct_input_filter *f, uint32_t release_ms, uint32_t enable_ms,
                    ct_local_inputs initial, uint64_t now_ms)
{
    if (!f) return false;
    memset(f, 0, sizeof(*f));
    f->release_ms = release_ms;
    f->enable_ms = enable_ms;
    f->last_ms = f->stop_release_ms = f->fault_release_ms = f->enable_since_ms = now_ms;
    f->raw = initial;
    f->enable_candidate = initial.enable_button;
    f->stop_active = f->stop_pending = initial.stop;
    f->fault_active = f->fault_pending = initial.fault;
    f->valid = release_ms != 0 && enable_ms != 0;
    return f->valid;
}

bool ct_inputs_observe(ct_input_filter *f, ct_local_inputs raw, uint64_t now_ms)
{
    if (!f || !f->valid) return false;
    if (now_ms < f->last_ms) {
        f->valid = false;
        f->enable_stable = false;
        return false;
    }
    f->last_ms = now_ms;
    safety_level(raw.stop, f->raw.stop, now_ms, f->release_ms,
                 &f->stop_release_ms, &f->stop_active, &f->stop_pending);
    safety_level(raw.fault, f->raw.fault, now_ms, f->release_ms,
                 &f->fault_release_ms, &f->fault_active, &f->fault_pending);
    if (raw.enable_button != f->enable_candidate) {
        f->enable_candidate = raw.enable_button;
        f->enable_since_ms = now_ms;
    }
    if (f->stop_active || f->fault_active || f->stop_pending || f->fault_pending) {
        f->enable_stable = false;
        f->enable_armed = false;
        f->enable_since_ms = now_ms;
    } else if (now_ms - f->enable_since_ms >= f->enable_ms) {
        if (!f->enable_candidate) {
            f->enable_stable = false;
            f->enable_armed = true;
        } else if (f->enable_armed) {
            f->enable_stable = true;
        }
    }
    f->raw = raw;
    return true;
}

bool ct_inputs_read(ct_input_filter *f, ct_local_inputs *inputs)
{
    if (!inputs) return false;
    *inputs = (ct_local_inputs){0};
    if (!f || !f->valid) return false;
    *inputs = (ct_local_inputs){f->stop_active || f->stop_pending,
                               f->fault_active || f->fault_pending, f->enable_stable};
    f->stop_pending = f->fault_pending = false;
    return true;
}
