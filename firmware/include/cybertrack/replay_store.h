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

/* Single owner; use static/heap storage, not a small task stack. Wire encoding
 * is explicit little endian, never a dump of this struct. No dynamic memory. */
typedef struct {
    ct_replay_io io;
    ct_store_state state;
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
 * No-op saves do no I/O. UINT64_MAX revision cannot wrap. */
bool ct_replay_store_save(ct_replay_store *s, const unsigned char *filter, uint64_t session);

#endif
