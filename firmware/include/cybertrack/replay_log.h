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
 * Failure during writes latches !ready; reboot/init is required. Attach after
 * store bind, before the protocol's first open. No retroactive evidence is
 * created until the first changed save has completed its journal write. */
bool ct_replay_log_init(ct_replay_log *log, ct_replay_io io);
bool ct_replay_store_attach_log(ct_replay_store *store, ct_replay_log *log);
/* Explicit local maintenance, all outputs off/owners retired, fresh EMPTY
 * independent destination. Exact current anchor record selects the journal
 * snapshot; primary bytes may be unavailable. Neither primary nor log is
 * mutated. Returns the same recovery statuses as snapshot maintenance. */
ct_replay_recovery_result ct_replay_store_recover_log(
    ct_replay_store *source, ct_replay_log *log, ct_replay_anchor_io anchor,
    uint64_t source_id, ct_replay_store *destination, uint64_t destination_id);
#endif
