#ifndef CYBERTRACK_INPUTS_H
#define CYBERTRACK_INPUTS_H

#include "cybertrack/runtime.h"

/* Logical observations only: true means asserted, independent of GPIO polarity.
 * Single owner; platform must serialize capture/read, including ISR handoff.
 * Unobserved pulses cannot be recovered by this software. */
typedef struct {
    uint32_t release_ms, enable_ms;
    uint64_t last_ms, stop_release_ms, fault_release_ms, enable_since_ms;
    ct_local_inputs raw;
    bool stop_active, fault_active, stop_pending, fault_pending;
    bool enable_candidate, enable_stable, enable_armed, valid;
} ct_input_filter;

/* Both debounce intervals must be nonzero and supplied by the adapter. A held
 * enable at boot never arms; a stable release and a new press are required. */
bool ct_inputs_init(ct_input_filter *f, uint32_t release_ms, uint32_t enable_ms,
                    ct_local_inputs initial, uint64_t now_ms);
/* Assert stop/fault immediately; debounce only their release. Latch observed
 * pulses until read. Clock rollback invalidates the filter until a new boot. */
bool ct_inputs_observe(ct_input_filter *f, ct_local_inputs raw, uint64_t now_ms);
/* Consume pending stop/fault assertions, but preserve asserted/debouncing levels.
 * Use as the implementation of read_inputs; false must propagate to runtime. */
bool ct_inputs_read(ct_input_filter *f, ct_local_inputs *inputs);

#endif
