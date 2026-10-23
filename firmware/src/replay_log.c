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
bool ct_replay_log_read(ct_replay_log *log, ct_replay_anchor_record r, unsigned char *filter)
{
    if (!log || !log->ready || !filter || !record_valid(r)) return false;
    unsigned slot = (unsigned)((r.revision - 1) % 2);
    if (!log->io.read(log->io.context, slot, 0, log->scratch, sizeof(log->scratch)) ||
        !matches(log->scratch, r)) { log->ready = false; return false; }
    memcpy(filter, log->scratch + FILTER_OFFSET, CT_REPLAY_BYTES);
    return true;
}
bool ct_replay_log_prepare(ct_replay_log *log, ct_replay_anchor_record next,
                           const unsigned char *filter)
{
    if (!log || !log->ready || !filter || !record_valid(next)) return false;
    unsigned char *p = log->scratch;
    memcpy(p, magic, 8); put64(p+8, next.epoch); put64(p+16, next.backend_id);
    put64(p+24, next.revision); put64(p+32, next.session);
    memcpy(p + FILTER_OFFSET, filter, CT_REPLAY_BYTES);
    uint32_t crc = checksum(p);
    for (unsigned i = 0; i < 4; ++i) p[CRC_OFFSET+i] = (unsigned char)(crc >> (8*i));
    unsigned slot = (unsigned)((next.revision - 1) % 2);
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
