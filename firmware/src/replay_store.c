#include "cybertrack/replay_store.h"

#include <string.h>

#define FILTER_OFFSET 24u
#define CRC_OFFSET (FILTER_OFFSET + CT_REPLAY_BYTES)
#define MARK_OFFSET (CRC_OFFSET + 4u)
static const unsigned char magic[8] = {'C','T','R','P',1,0,0,0}; /* Format/hash policy v1. */
static const unsigned char marker[4] = {'D','O','N','E'};

static void put64(unsigned char *p, uint64_t value)
{
    for (unsigned i = 0; i < 8; ++i) { p[i] = (unsigned char)value; value >>= 8; }
}
static uint64_t get64(const unsigned char *p)
{
    uint64_t value = 0;
    for (unsigned i = 0; i < 8; ++i) value |= (uint64_t)p[i] << (8 * i);
    return value;
}
/* CRC-32, reflected polynomial; detects accidental corruption, not malicious
 * rollback/tampering. Backend/device identity and rollback resistance are
 * separate integration requirements. */
static uint32_t checksum(const unsigned char *p)
{
    uint32_t crc = UINT32_MAX;
    for (size_t i = 0; i < CRC_OFFSET; ++i) {
        crc ^= p[i];
        for (unsigned j = 0; j < 8; ++j)
            crc = (crc >> 1) ^ ((crc & 1u) ? UINT32_C(0xedb88320) : 0u);
    }
    return ~crc;
}
static bool blank(const unsigned char *p)
{
    for (size_t i = 0; i < CT_REPLAY_SLOT_BYTES; ++i) if (p[i] != 0xff) return false;
    return true;
}
static bool valid(const unsigned char *p, unsigned slot)
{
    uint64_t revision = get64(p + 8);
    uint32_t crc = checksum(p);
    if (memcmp(p, magic, sizeof(magic)) || memcmp(p + MARK_OFFSET, marker, sizeof(marker)) ||
        !revision || (revision - 1) % 2 != slot || get64(p + 16) >= revision) return false;
    for (unsigned i = 0; i < 4; ++i)
        if (p[CRC_OFFSET + i] != (unsigned char)(crc >> (8 * i))) return false;
    return true;
}
static bool superset(const unsigned char *newer, const unsigned char *older)
{
    for (size_t i = 0; i < CT_REPLAY_BYTES; ++i)
        if ((newer[i] & older[i]) != older[i]) return false;
    return true;
}
static bool fault(ct_replay_store *s) { s->state = CT_STORE_FAULT; return false; }

static bool same_record(ct_replay_anchor_record a, ct_replay_anchor_record b)
{
    return a.epoch == b.epoch && a.backend_id == b.backend_id &&
           a.revision == b.revision && a.session == b.session;
}

bool ct_replay_store_check(ct_replay_store *s)
{
    if (!s || s->state != CT_STORE_READY) return false;
    if (!s->anchor_bound) return true;
    ct_replay_anchor_record current = {0};
    if (!s->anchor.read || !s->anchor.replace || !s->selected.epoch ||
        !s->selected.backend_id || s->selected.revision != s->revision ||
        s->selected.session != s->session ||
        !s->anchor.read(s->anchor.context, &current) || !same_record(current, s->selected))
        return fault(s);
    return true;
}

static bool advance_anchor(ct_replay_store *s, ct_replay_anchor_record next)
{
    ct_replay_anchor_record actual = {0};
    if (!s->anchor.replace(s->anchor.context, &s->selected, &next) ||
        !s->anchor.read(s->anchor.context, &actual) || !same_record(actual, next)) return fault(s);
    s->selected = next;
    return true;
}

static bool bind_anchor(ct_replay_store *s, ct_replay_anchor_io anchor,
                        uint64_t id, bool enroll)
{
    if (!s || s->state != CT_STORE_READY || s->anchor_bound) return false;
    s->anchor_bound = true; s->anchor = anchor;
    if (!id || !anchor.read || !anchor.replace ||
        !anchor.read(anchor.context, &s->selected)) return fault(s);
    if (enroll) {
        if (!same_record(s->selected, (ct_replay_anchor_record){0}) ||
            !advance_anchor(s, (ct_replay_anchor_record){1, id, s->revision, s->session}))
            return fault(s);
    } else if (s->selected.backend_id != id) return fault(s);
    return ct_replay_store_check(s);
}

bool ct_replay_store_bind(ct_replay_store *s, ct_replay_anchor_io anchor, uint64_t id)
{
    return bind_anchor(s, anchor, id, false);
}
bool ct_replay_store_enroll(ct_replay_store *s, ct_replay_anchor_io anchor, uint64_t id)
{
    return bind_anchor(s, anchor, id, true);
}

ct_store_state ct_replay_store_load(ct_replay_store *s, ct_replay_io io)
{
    if (!s) return CT_STORE_FAULT;
    memset(s, 0, sizeof(*s)); s->io = io; /* FAULT until fully validated. */
    if (!io.read || !io.erase || !io.write || !io.sync) return s->state;
    if (!io.read(io.context, 0, 0, s->scratch, sizeof(s->scratch))) return s->state;
    bool first_blank = blank(s->scratch);
    if (!first_blank && !valid(s->scratch, 0)) return s->state;
    uint64_t first_revision = get64(s->scratch + 8), first_session = get64(s->scratch + 16);
    memcpy(s->filter, s->scratch + FILTER_OFFSET, sizeof(s->filter));
    if (!io.read(io.context, 1, 0, s->scratch, sizeof(s->scratch))) return s->state;
    if (first_blank && blank(s->scratch)) { s->state = CT_STORE_EMPTY; return s->state; }
    if (first_blank || !valid(s->scratch, 1)) return s->state;
    uint64_t second_revision = get64(s->scratch + 8), second_session = get64(s->scratch + 16);
    bool second_newer = second_revision > first_revision;
    uint64_t newer = second_newer ? second_revision : first_revision;
    uint64_t older = second_newer ? first_revision : second_revision;
    uint64_t new_session = second_newer ? second_session : first_session;
    uint64_t old_session = second_newer ? first_session : second_session;
    if (newer - older != 1 || new_session < old_session || new_session - old_session > 1 ||
        !superset(second_newer ? s->scratch + FILTER_OFFSET : s->filter,
                  second_newer ? s->filter : s->scratch + FILTER_OFFSET)) return s->state;
    s->revision = newer; s->session = new_session; s->slot = second_newer ? 1 : 0;
    if (second_newer) memcpy(s->filter, s->scratch + FILTER_OFFSET, sizeof(s->filter));
    s->state = CT_STORE_READY;
    return s->state;
}

static bool write_slot(ct_replay_store *s, unsigned slot, uint64_t revision,
                       uint64_t session, const unsigned char *filter)
{
    unsigned char *p = s->scratch;
    memcpy(p, magic, sizeof(magic)); put64(p + 8, revision); put64(p + 16, session);
    memcpy(p + FILTER_OFFSET, filter, CT_REPLAY_BYTES);
    uint32_t crc = checksum(p);
    for (unsigned i = 0; i < 4; ++i) p[CRC_OFFSET + i] = (unsigned char)(crc >> (8 * i));
    memcpy(p + MARK_OFFSET, marker, sizeof(marker));
    if (!s->io.erase(s->io.context, slot) ||
        !s->io.write(s->io.context, slot, 0, p, MARK_OFFSET) ||
        !s->io.sync(s->io.context) ||
        !s->io.write(s->io.context, slot, MARK_OFFSET, marker, sizeof(marker)) ||
        !s->io.sync(s->io.context) ||
        !s->io.read(s->io.context, slot, 0, p, sizeof(s->scratch))) return fault(s);
    if (!valid(p, slot) || get64(p + 8) != revision || get64(p + 16) != session ||
        memcmp(p + FILTER_OFFSET, filter, CT_REPLAY_BYTES)) return fault(s);
    s->revision = revision; s->session = session; s->slot = slot;
    if (filter != s->filter) memcpy(s->filter, filter, CT_REPLAY_BYTES);
    return true;
}

bool ct_replay_store_provision(ct_replay_store *s)
{
    if (!s || s->state != CT_STORE_EMPTY) return false;
    for (unsigned slot = 0; slot < 2; ++slot) {
        if (!s->io.read(s->io.context, slot, 0, s->scratch, sizeof(s->scratch)) || !blank(s->scratch))
            return fault(s);
    }
    memset(s->filter, 0, sizeof(s->filter));
    if (!write_slot(s, 0, 1, 0, s->filter) || !write_slot(s, 1, 2, 0, s->filter)) return false;
    s->state = CT_STORE_READY;
    return true;
}

bool ct_replay_store_save(ct_replay_store *s, const unsigned char *filter, uint64_t session)
{
    if (!ct_replay_store_check(s)) return false;
    if (!filter || session < s->session || session - s->session > 1 || !superset(filter, s->filter)) return fault(s);
    if (session == s->session && !memcmp(filter, s->filter, CT_REPLAY_BYTES)) return true;
    if (s->revision == UINT64_MAX || (s->anchor_bound && s->selected.epoch == UINT64_MAX))
        return fault(s);
    if (s->anchor_bound) {
        /* Reserve BEFORE touching media: an interrupted write must never leave
         * an unanchored candidate revision that can be reused for other bits
         * after restoring an older image. Otherwise two valid snapshots could
         * share an anchored revision while containing different histories. */
        ct_replay_anchor_record next = s->selected;
        ++next.epoch; next.revision = s->revision + 1; next.session = session;
        if (!advance_anchor(s, next)) return false;
    }
    if (!write_slot(s, 1 - s->slot, s->revision + 1, session, filter)) return false;
    return ct_replay_store_check(s);
}

/* A migration is a lossless offline copy, not a chance to reconstruct or clear
 * Bloom bits. Re-read both source slots to reject a stale caller snapshot. */
bool ct_replay_store_migrate(const ct_replay_store *src, ct_replay_store *dst)
{
    if (!src || !dst || src == dst || src->state != CT_STORE_READY ||
        dst->state != CT_STORE_EMPTY || src->io.context == dst->io.context) return false;
    if (src->revision > UINT64_MAX - 2) return fault(dst);
    for (unsigned slot = 0; slot < 2; ++slot) {
        unsigned char *p = dst->scratch;
        if (!src->io.read(src->io.context, slot, 0, p, sizeof(dst->scratch)) || !valid(p, slot))
            return fault(dst);
        uint64_t revision = get64(p + 8), session = get64(p + 16);
        if (slot == src->slot) {
            if (revision != src->revision || session != src->session ||
                memcmp(p + FILTER_OFFSET, src->filter, CT_REPLAY_BYTES)) return fault(dst);
        } else if (revision != src->revision - 1 || session > src->session ||
                   src->session - session > 1 || !superset(src->filter, p + FILTER_OFFSET))
            return fault(dst);
    }
    for (unsigned slot = 0; slot < 2; ++slot) {
        if (!dst->io.read(dst->io.context, slot, 0, dst->scratch, sizeof(dst->scratch)) ||
            !blank(dst->scratch)) return fault(dst);
    }
    /* Two complete copies form a valid pair. Each write syncs and reads back;
     * a single complete slot can never be selected by normal boot recovery. */
    for (uint64_t offset = 1; offset <= 2; ++offset) {
        uint64_t revision = src->revision + offset;
        if (!write_slot(dst, (unsigned)((revision - 1) % 2), revision, src->session, src->filter))
            return false;
    }
    dst->state = CT_STORE_READY;
    return true;
}

bool ct_replay_store_switch(ct_replay_store *src, ct_replay_store *dst, uint64_t id)
{
    if (!src || !dst || src == dst || !src->anchor_bound ||
        src->state != CT_STORE_READY || dst->state != CT_STORE_EMPTY || dst->anchor_bound ||
        !id || id == src->selected.backend_id || src->io.context == dst->io.context) return false;
    if (!ct_replay_store_check(src) || src->selected.epoch == UINT64_MAX ||
        !ct_replay_store_migrate(src, dst)) {
        fault(src); return fault(dst);
    }
    dst->anchor_bound = true; dst->anchor = src->anchor; dst->selected = src->selected;
    ct_replay_anchor_record next = {src->selected.epoch + 1, id, dst->revision, dst->session};
    /* Revoke the old in-memory owner even on ambiguous selection. Boot must
     * consult the independent anchor; it cannot infer selection from a copy. */
    fault(src);
    return advance_anchor(dst, next);
}
