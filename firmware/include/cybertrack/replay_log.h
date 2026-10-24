#ifndef CYBERTRACK_REPLAY_LOG_H
#define CYBERTRACK_REPLAY_LOG_H
#include "cybertrack/replay_store.h"

#define CT_REPLAY_LOG_SLOT_BYTES (CT_REPLAY_BYTES + 48u)
/* Independent two-slot evidence journal. Same exact-transfer/durable-sync
 * contract as ct_replay_io, but each slot is CT_REPLAY_LOG_SLOT_BYTES bytes.
 * Physically isolated from primary/repair media AND rollback-resistant anchor.
 * Single serialized owner; static/heap allocation, no internal heap use. */
struct ct_replay_log {
    ct_replay_io io;
    bool ready;
    unsigned char scratch[CT_REPLAY_LOG_SLOT_BYTES];
};
/* Configures callbacks only: does not erase, provision or trust existing data.
 * Failure during reads/writes latches !ready; reboot/init is required. */
bool ct_replay_log_init(ct_replay_log *log, ct_replay_io io);
/* Existing anchor: seed/verify its exact complete history before attaching.
 * Requires bound READY primary; no second matching record or silent conflict.
 * Only success establishes independent evidence. For first registration use
 * enroll_logged below so evidence exists BEFORE initial anchor selection. */
bool ct_replay_store_attach_log(ct_replay_store *store, ct_replay_log *log);
/* Explicit local first-use/attested legacy enrollment, outputs off. Requires
 * NEVER-enrolled anchor; prepares full initial evidence before atomic selection.
 * Failure requires reload and actual-anchor inspection, never re-enrollment. */
bool ct_replay_store_enroll_logged(ct_replay_store *store, ct_replay_log *log,
                                    ct_replay_anchor_io anchor, uint64_t backend_id);
/* Explicit local maintenance, all outputs off/owners retired, fresh EMPTY
 * independent destination. Exact current anchor record selects the journal
 * snapshot by scanning both slots; primary bytes may be unavailable. A durable
 * unchanged-history bridge precedes each attempt epoch allocation, so it
 * remains recoverable while the new candidate is incomplete. Primary is not
 * mutated. Preserves selected source log and prepares target evidence in the
 * other slot BEFORE selecting it; target inherits the log. */
ct_replay_recovery_result ct_replay_store_recover_log(
    ct_replay_store *source, ct_replay_log *log, ct_replay_anchor_io anchor,
    uint64_t source_id, ct_replay_store *destination, uint64_t destination_id);
#endif
