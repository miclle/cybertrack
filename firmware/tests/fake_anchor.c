#include "fake_anchor.h"
static bool same(ct_replay_anchor_record a, ct_replay_anchor_record b)
{
    return a.epoch == b.epoch && a.backend_id == b.backend_id &&
           a.revision == b.revision && a.session == b.session;
}
static bool read_anchor(void *ctx, ct_replay_anchor_record *record)
{
    ct_test_anchor *a = ctx;
    if (++a->calls == a->fail_at) return false;
    *record = a->durable; return true;
}
static bool replace(void *ctx, const ct_replay_anchor_record *expected,
                    const ct_replay_anchor_record *next)
{
    ct_test_anchor *a = ctx;
    bool failed = ++a->calls == a->fail_at;
    if (!same(a->durable, *expected) || expected->epoch == UINT64_MAX ||
        next->epoch != expected->epoch + 1 || !next->backend_id ||
        next->revision < expected->revision || next->session < expected->session ||
        (next->revision == expected->revision && (next->backend_id != expected->backend_id || next->session != expected->session)) ||
        next->session >= next->revision) return false;
    if (!failed || a->commit_on_failure) { a->durable = *next; ++a->replacements; }
    return !failed;
}
ct_replay_anchor_io ct_test_anchor_io(ct_test_anchor *a)
{
    return (ct_replay_anchor_io){a, read_anchor, replace};
}
void ct_test_anchor_power_cut(ct_test_anchor *a)
{
    a->calls = a->fail_at = 0; a->commit_on_failure = false;
}
