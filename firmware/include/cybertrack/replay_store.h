#ifndef CYBERTRACK_REPLAY_STORE_H
#define CYBERTRACK_REPLAY_STORE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define CT_REPLAY_BYTES 32768u
#define CT_REPLAY_SLOT_BYTES (CT_REPLAY_BYTES + 32u)

typedef enum { CT_STORE_FAULT, CT_STORE_EMPTY, CT_STORE_READY } ct_store_state;

/* Two isolated slots, each CT_REPLAY_SLOT_BYTES. Exact-length transfers: false
 * may mean partial completion. sync(true) guarantees all earlier mutations are
 * durable and ordered across power loss, not merely readable in a write cache.
 * erase affects ONLY the selected slot. Calls must be bounded/non-reentrant.
 * Context and callbacks live as long as the store; no GPIO or network here. */
typedef struct {
    void *context;
    bool (*read)(void *context, unsigned slot, size_t offset, void *data, size_t size);
    bool (*erase)(void *context, unsigned slot);
    bool (*write)(void *context, unsigned slot, size_t offset, const void *data, size_t size);
    bool (*sync)(void *context);
} ct_replay_io;

/* Independent, device-bound rollback-resistant anchor. Zero record means NEVER
 * enrolled, not missing/corrupt/reset. read returns the durable record. replace
 * atomically compares ALL fields and durably installs next; mismatch leaves
 * the current record untouched. False may mean committed or unchanged. No torn
 * record, volatile success, rollback or
 * erase is permitted. This is a backend contract, NOT a Flash implementation.
 * Backend IDs are nonzero, immutable trusted identities, not network input.
 * Epoch-only advances with identical backend/revision/session allocate unique
 * log attempts. CAS must support these and compare epoch as well as data fields.
 * One serialized owner covers the anchor and all stores through each operation. */
typedef struct {
    uint64_t epoch, backend_id, revision, session;
} ct_replay_anchor_record;
typedef struct {
    void *context;
    bool (*read)(void *context, ct_replay_anchor_record *record);
    bool (*replace)(void *context, const ct_replay_anchor_record *expected,
                    const ct_replay_anchor_record *next);
} ct_replay_anchor_io;

typedef struct ct_replay_log ct_replay_log;

/* Single owner; use static/heap storage, not a small task stack. Wire encoding
 * is explicit little endian, never a dump of this struct. No dynamic memory. */
typedef struct {
    ct_replay_io io;
    ct_replay_log *log; /* Optional independent write-ahead evidence. */
    ct_store_state state;
    bool anchor_bound;
    ct_replay_anchor_io anchor;
    ct_replay_anchor_record selected;
    uint64_t revision, session;
    unsigned slot;
    unsigned char filter[CT_REPLAY_BYTES];
    unsigned char scratch[CT_REPLAY_SLOT_BYTES];
} ct_replay_store;

/* Boot-time read only. Both slots must validate; never silently fall back to
 * one old snapshot. Blank media is EMPTY, not permission to execute actions. */
ct_store_state ct_replay_store_load(ct_replay_store *s, ct_replay_io io);
/* Explicit local first-use provisioning, outputs off. Only a freshly loaded
 * EMPTY pair is eligible; rechecks media. Not a reset/repair/erase API. */
bool ct_replay_store_provision(ct_replay_store *s);
/* Persist a monotone superset and the same/next session BEFORE using them.
 * Failure latches FAULT (even ambiguous completion); reboot/load is required.
 * Anchored saves reserve a never-reused version BEFORE media writes; success
 * requires full media readback and a final anchor match. Interrupted reservation
 * may lock actions until maintenance; no automatic rollback/repair.
 * No-op saves read the anchor but do not write. UINT64_MAX revision cannot wrap. */
bool ct_replay_store_save(ct_replay_store *s, const unsigned char *filter, uint64_t session);

/* Bind an already loaded READY pair to its trusted backend identity and exact
 * anchored revision/session. Once attempted, cannot rebind without load. Failure
 * latches FAULT. enroll is explicit first-use/legacy enrollment with outputs off,
 * a locally verified history, and an anchor attesting NEVER enrolled; NOT repair.
 * bind/check/save never enroll or repair a missing anchor automatically. */
bool ct_replay_store_bind(ct_replay_store *s, ct_replay_anchor_io anchor, uint64_t backend_id);
bool ct_replay_store_enroll(ct_replay_store *s, ct_replay_anchor_io anchor, uint64_t backend_id);
/* Re-read anchor to fence stale owners. Unanchored READY returns true for legacy
 * tests only. All saves (including no-ops) check before any media mutation. */
bool ct_replay_store_check(ct_replay_store *s);
/* Offline lossless copy followed by atomic anchor selection; source must be
 * anchored, destination EMPTY/unbound and physically independent. Outputs off,
 * old protocol retired, no other writer until completion. Both RAM objects are
 * faulted on failure after validation starts; reload/bind the anchor-selected
 * backend after reboot. Success retires source and binds destination. Never
 * fall back to another backend if selected media is missing or invalid. */
bool ct_replay_store_switch(ct_replay_store *source, ct_replay_store *destination,
                            uint64_t destination_id);

/* Explicit LOCAL maintenance, outputs off and ALL protocol owners retired.
 * Unlike load, can use one complete current snapshot when its companion slot
 * is damaged. Never uses an older revision to repair an advanced anchor: that
 * is indistinguishable from rollback of already accepted action history.
 * Source must have been load-initialized (FAULT allowed); destination must be
 * freshly loaded EMPTY, independent, with a different trusted backend ID.
 * Re-reads anchor and source bytes; ignores cached filter/selected fields.
 * Retires both RAM objects once validation starts. Writes ONLY destination,
 * copies full history at two fresh revisions, then atomically selects it.
 * On failure no retry/rebind in-place: reboot/load and inspect anchor. Normal
 * boot remains strict; no automatic recovery, erase, reset or remote tool. */
typedef enum {
    CT_RECOVERY_OK,
    CT_RECOVERY_BAD_ARGUMENT,
    CT_RECOVERY_ANCHOR_UNAVAILABLE,
    CT_RECOVERY_WRONG_BACKEND,
    CT_RECOVERY_HISTORY_UNAVAILABLE,
    CT_RECOVERY_HISTORY_CONFLICT,
    CT_RECOVERY_DESTINATION_UNAVAILABLE,
    CT_RECOVERY_SELECTION_UNCERTAIN,
    CT_RECOVERY_EXHAUSTED
} ct_replay_recovery_result;
ct_replay_recovery_result ct_replay_store_recover(
    ct_replay_store *source, ct_replay_anchor_io anchor, uint64_t source_id,
    ct_replay_store *destination, uint64_t destination_id);

/* Offline copy to a freshly loaded EMPTY, physically independent pair. Outputs
 * must be off and source writers stopped for the entire copy AND cutover.
 * Revalidates source against its loaded snapshot and destination blankness.
 * Copies ALL bits and session without changing v1 hash/format; never erases the
 * source. Only true permits selecting the destination. False latches destination
 * FAULT after I/O begins; ambiguous completion still requires reload/validation.
 * Caller owns device binding and durable backend selection: after cutover never
 * resume the stale source or auto-fallback to it. No online relocation/GC. */
bool ct_replay_store_migrate(const ct_replay_store *source, ct_replay_store *destination);

#endif
