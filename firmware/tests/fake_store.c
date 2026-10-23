#include "fake_store.h"
#include <stdlib.h>
#include <string.h>

static bool fail(ct_test_store *s) { return ++s->calls == s->fail_at; }
static size_t cut(ct_test_store *s, size_t length) { return s->cut_bytes < length ? s->cut_bytes : length; }
static void bounds(unsigned slot, size_t offset, size_t size)
{
    if (slot >= 2 || offset > CT_REPLAY_SLOT_BYTES || size > CT_REPLAY_SLOT_BYTES - offset) abort();
}
static bool read_bytes(void *ctx, unsigned slot, size_t offset, void *data, size_t size)
{
    ct_test_store *s = ctx; bounds(slot, offset, size);
    bool failed = fail(s);
    memcpy(data, s->pending[slot] + offset, failed ? cut(s, size) : size);
    return !failed;
}
static bool erase(void *ctx, unsigned slot)
{
    ct_test_store *s = ctx; bounds(slot, 0, CT_REPLAY_SLOT_BYTES);
    bool failed = fail(s);
    size_t n = failed ? cut(s, CT_REPLAY_SLOT_BYTES) : CT_REPLAY_SLOT_BYTES;
    memset(s->pending[slot], 0xff, n);
    if (failed && s->persist_partial) memcpy(s->durable[slot], s->pending[slot], n);
    return !failed;
}
static bool write_bytes(void *ctx, unsigned slot, size_t offset, const void *data, size_t size)
{
    ct_test_store *s = ctx; bounds(slot, offset, size);
    bool failed = fail(s);
    size_t n = failed ? cut(s, size) : size;
    memcpy(s->pending[slot] + offset, data, n);
    if (failed && s->persist_partial) memcpy(s->durable[slot], s->pending[slot], offset + n);
    return !failed;
}
static bool sync_bytes(void *ctx)
{
    ct_test_store *s = ctx;
    bool failed = fail(s);
    size_t n = failed ? cut(s, CT_REPLAY_SLOT_BYTES) : CT_REPLAY_SLOT_BYTES;
    if (!failed || s->persist_partial)
        for (unsigned i = 0; i < 2; ++i) memcpy(s->durable[i], s->pending[i], n);
    return !failed;
}
void ct_test_store_blank(ct_test_store *s)
{
    memset(s, 0, sizeof(*s)); memset(s->durable, 0xff, sizeof(s->durable));
    memcpy(s->pending, s->durable, sizeof(s->pending));
}
void ct_test_store_power_cut(ct_test_store *s)
{
    memcpy(s->pending, s->durable, sizeof(s->pending));
    s->calls = s->fail_at = s->cut_bytes = 0; s->persist_partial = false;
}
ct_replay_io ct_test_store_io(ct_test_store *s)
{
    return (ct_replay_io){s, read_bytes, erase, write_bytes, sync_bytes};
}
