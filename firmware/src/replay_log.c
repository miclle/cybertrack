#include "replay_log_internal.h"
#include <string.h>
#define FILTER_OFFSET 40u
#define CRC_OFFSET (FILTER_OFFSET + CT_REPLAY_BYTES)
#define MARK_OFFSET (CRC_OFFSET + 4u)
static const unsigned char magic[8] = {'C','T','L','G',1,0,0,0};
static const unsigned char marker[4] = {'D','O','N','E'};
static void put64(unsigned char *p, uint64_t n)
{
    for (unsigned i = 0; i < 8; ++i) { p[i] = (unsigned char)n; n >>= 8; }
}
static uint64_t get64(const unsigned char *p)
{
    uint64_t n = 0; for (unsigned i = 0; i < 8; ++i) n |= (uint64_t)p[i] << (8*i);
    return n;
}
static uint32_t checksum(const unsigned char *p)
{
    uint32_t crc = UINT32_MAX;
    for (size_t i = 0; i < CRC_OFFSET; ++i) {
        crc ^= p[i];
        for (unsigned b = 0; b < 8; ++b)
            crc = (crc >> 1) ^ ((crc & 1u) ? UINT32_C(0xedb88320) : 0u);
    }
    return ~crc;
}
static bool record_valid(ct_replay_anchor_record r)
{
    return r.epoch && r.backend_id && r.revision >= 2 && r.session < r.revision;
}
static bool matches(const unsigned char *p, ct_replay_anchor_record r)
{
    if (memcmp(p, magic, 8) || memcmp(p + MARK_OFFSET, marker, 4) ||
        get64(p+8) != r.epoch || get64(p+16) != r.backend_id ||
        get64(p+24) != r.revision || get64(p+32) != r.session) return false;
    uint32_t crc = checksum(p);
    for (unsigned i = 0; i < 4; ++i)
        if (p[CRC_OFFSET+i] != (unsigned char)(crc >> (8*i))) return false;
    return true;
}
bool ct_replay_log_init(ct_replay_log *log, ct_replay_io io)
{
    if (!log) return false;
    memset(log, 0, sizeof(*log)); log->io = io;
    log->ready = io.read && io.erase && io.write && io.sync;
    return log->ready;
}
bool ct_replay_log_init_redundant(ct_replay_log *log, ct_replay_io io,
                                  ct_replay_log_redundancy *workspace)
{
    if (!ct_replay_log_init(log, io)) return false;
    if (!workspace) { log->ready = false; return false; }
    log->redundancy = workspace;
    return true;
}
/* One pair holds the selected history while the other prepares its successor.
 * A bad/read-failed slot is not evidence. All readable exact-key replicas must
 * agree byte-for-byte and belong to ONE pair; never choose an older key. */
static bool find_replicas(ct_replay_log *log, ct_replay_anchor_record r,
                          unsigned *mask, const unsigned char *expected)
{
    *mask = 0;
    bool unreadable = false;
    for (unsigned slot = 0; slot < CT_REPLAY_LOG_REDUNDANT_SLOTS; ++slot) {
        if (!log->io.read(log->io.context, slot, 0, log->scratch, sizeof(log->scratch))) {
            unreadable = true; continue;
        }
        if (!matches(log->scratch, r)) continue;
        const unsigned char *bits = log->scratch + FILTER_OFFSET;
        if ((*mask && memcmp(log->redundancy->filter, bits, CT_REPLAY_BYTES)) ||
            (expected && memcmp(expected, bits, CT_REPLAY_BYTES))) goto failure;
        if (!*mask) memcpy(log->redundancy->filter, bits, CT_REPLAY_BYTES);
        *mask |= 1u << slot;
    }
    if (((*mask & 3u) && (*mask & 12u)) || (!*mask && unreadable)) goto failure;
    return true;
failure:
    log->ready = false; return false;
}
/* A revision can now have several attempt epochs. Keep the uniquely selected
 * slot, irrespective of revision parity; a candidate never overwrites it.
 * Read both slots before mutation and reject ambiguous matching evidence. */
static bool find_selected(ct_replay_log *log, ct_replay_anchor_record r,
                          unsigned *selected, unsigned char *filter, const unsigned char *expected)
{
    *selected = 2;
    for (unsigned slot = 0; slot < 2; ++slot) {
        if (!log->io.read(log->io.context, slot, 0, log->scratch, sizeof(log->scratch)))
            goto failure;
        if (!matches(log->scratch, r)) continue;
        if (*selected != 2 || (expected && memcmp(log->scratch + FILTER_OFFSET, expected, CT_REPLAY_BYTES))) goto failure;
        *selected = slot;
        if (filter) memcpy(filter, log->scratch + FILTER_OFFSET, CT_REPLAY_BYTES);
    }
    return true;
failure:
    log->ready = false;
    return false;
}
bool ct_replay_log_read(ct_replay_log *log, ct_replay_anchor_record r, unsigned char *filter)
{
    if (!log || !log->ready || !filter || !record_valid(r)) return false;
    unsigned selected;
    if (log->redundancy) {
        if (!find_replicas(log, r, &selected, NULL)) return false;
        if (!selected) { log->ready = false; return false; }
        memcpy(filter, log->redundancy->filter, CT_REPLAY_BYTES);
        return true;
    }
    if (!find_selected(log, r, &selected, filter, NULL)) return false;
    if (selected == 2) { log->ready = false; return false; }
    return true;
}
static bool write_record(ct_replay_log *log, unsigned slot,
                          ct_replay_anchor_record next, const unsigned char *filter)
{
    unsigned char *p = log->scratch;
    memcpy(p, magic, 8); put64(p+8, next.epoch); put64(p+16, next.backend_id);
    put64(p+24, next.revision); put64(p+32, next.session);
    memcpy(p + FILTER_OFFSET, filter, CT_REPLAY_BYTES);
    uint32_t crc = checksum(p);
    for (unsigned i = 0; i < 4; ++i) p[CRC_OFFSET+i] = (unsigned char)(crc >> (8*i));
    if (!log->io.erase(log->io.context, slot) ||
        !log->io.write(log->io.context, slot, 0, p, MARK_OFFSET) ||
        !log->io.sync(log->io.context) ||
        !log->io.write(log->io.context, slot, MARK_OFFSET, marker, 4) ||
        !log->io.sync(log->io.context) ||
        !log->io.read(log->io.context, slot, 0, p, sizeof(log->scratch)) ||
        !matches(p, next) || memcmp(p + FILTER_OFFSET, filter, CT_REPLAY_BYTES)) {
        log->ready = false; return false;
    }
    return true;
}
bool ct_replay_log_prepare(ct_replay_log *log, ct_replay_anchor_record current,
                           ct_replay_anchor_record next, const unsigned char *filter)
{
    if (!log || !log->ready || !filter || !record_valid(current) || !record_valid(next)) return false;
    bool seed = current.epoch == next.epoch && current.backend_id == next.backend_id &&
                current.revision == next.revision && current.session == next.session;
    unsigned selected;
    if (log->redundancy) {
        if (!find_replicas(log, current, &selected, seed ? filter : NULL)) return false;
        unsigned pair = selected & 3u ? 0 : 2;
        if (!selected) pair = 0; /* Only attested full primary may seed missing evidence. */
        else if (!seed) pair = 2 - pair;
        for (unsigned slot = pair; slot < pair + 2; ++slot) {
            if (seed && (selected & (1u << slot))) continue;
            if (!write_record(log, slot, next, filter)) return false;
        }
        return true;
    }
    if (!find_selected(log, current, &selected, NULL, seed ? filter : NULL)) return false;
    if (seed && selected != 2) return true;
    return write_record(log, selected == 2 ? 0 : 1 - selected, next, filter);
}
