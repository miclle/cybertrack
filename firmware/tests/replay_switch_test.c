#include "fake_anchor.h"
#include "fake_store.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%d: %s\n", __LINE__, #x); exit(1); } } while (0)
static ct_test_store disks[2], old_disk, candidate;
static ct_replay_store stores[2], stale;
static ct_test_anchor anchor;
static unsigned char bits[CT_REPLAY_BYTES];
static size_t copy_cuts, save_cuts, anchor_cuts, rollback_checks;
static void load(unsigned i)
{
    ct_test_store_power_cut(&disks[i]);
    (void)ct_replay_store_load(&stores[i], ct_test_store_io(&disks[i]));
}
static void prepare(void)
{
    memset(&anchor, 0, sizeof(anchor)); memset(bits, 0, sizeof(bits));
    for (unsigned i = 0; i < 2; ++i) { ct_test_store_blank(&disks[i]); load(i); }
    CHECK(ct_replay_store_provision(&stores[0]));
    CHECK(ct_replay_store_enroll(&stores[0], ct_test_anchor_io(&anchor), 10));
    bits[0] = 1; CHECK(ct_replay_store_save(&stores[0], bits, 1));
    old_disk = disks[0]; stale = stores[0];
}
static void selection_and_rollback(void)
{
    prepare();
    CHECK(ct_replay_store_switch(&stores[0], &stores[1], 20));
    CHECK(stores[0].state == CT_STORE_FAULT && anchor.durable.backend_id == 20);
    CHECK(!ct_replay_store_save(&stale, bits, 1)); ++rollback_checks;
    CHECK(!memcmp(disks[0].durable, old_disk.durable, sizeof(old_disk.durable)));
    load(0); CHECK(!ct_replay_store_bind(&stores[0], ct_test_anchor_io(&anchor), 10)); ++rollback_checks;
    load(0); CHECK(!ct_replay_store_bind(&stores[0], ct_test_anchor_io(&anchor), 20)); ++rollback_checks;
    CHECK(ct_replay_store_check(&stores[1]));
    old_disk = disks[1]; bits[1] = 2;
    CHECK(ct_replay_store_save(&stores[1], bits, 1));
    disks[1] = old_disk; load(1);
    CHECK(!ct_replay_store_bind(&stores[1], ct_test_anchor_io(&anchor), 20)); ++rollback_checks;
    /* A different or erased backend cannot be enrolled against a used anchor. */
    ct_test_store_blank(&disks[1]); load(1); CHECK(ct_replay_store_provision(&stores[1]));
    CHECK(!ct_replay_store_enroll(&stores[1], ct_test_anchor_io(&anchor), 20)); ++rollback_checks;
}
static void interrupted_copy(void)
{
    const size_t boundaries[] = {0, 1, 4, 24, 32796, 32800};
    for (unsigned op = 1; op <= 14; ++op) for (unsigned durable = 0; durable < 2; ++durable)
        for (size_t b = 0; b < sizeof(boundaries)/sizeof(boundaries[0]); ++b) {
            prepare(); disks[1].fail_at = disks[1].calls + op;
            disks[1].cut_bytes = boundaries[b]; disks[1].persist_partial = durable != 0;
            CHECK(!ct_replay_store_switch(&stores[0], &stores[1], 20));
            CHECK(stores[0].state == CT_STORE_FAULT && stores[1].state == CT_STORE_FAULT);
            CHECK(anchor.durable.backend_id == 10);
            CHECK(!memcmp(disks[0].durable, old_disk.durable, sizeof(old_disk.durable)));
            load(0); load(1); ct_test_anchor_power_cut(&anchor);
            CHECK(ct_replay_store_bind(&stores[0], ct_test_anchor_io(&anchor), 10));
            CHECK(!memcmp(stores[0].filter, bits, sizeof(bits)));
            CHECK(!ct_replay_store_bind(&stores[1], ct_test_anchor_io(&anchor), 20));
            ++copy_cuts;
        }
}
static void interrupted_selection(void)
{
    /* check / compare-and-replace / readback, including durable success with
     * false returned and failure to observe an already committed selection. */
    for (unsigned op = 1; op <= 3; ++op) for (unsigned commit = 0; commit < 2; ++commit) {
        prepare(); anchor.fail_at = anchor.calls + op; anchor.commit_on_failure = commit != 0;
        CHECK(!ct_replay_store_switch(&stores[0], &stores[1], 20));
        CHECK(stores[0].state == CT_STORE_FAULT && stores[1].state == CT_STORE_FAULT);
        load(0); load(1); ct_test_anchor_power_cut(&anchor);
        unsigned selected = anchor.durable.backend_id == 10 ? 0 : 1;
        CHECK(ct_replay_store_bind(&stores[selected], ct_test_anchor_io(&anchor), selected ? 20 : 10));
        CHECK(!memcmp(stores[selected].filter, bits, sizeof(bits)));
        CHECK(!ct_replay_store_bind(&stores[1-selected], ct_test_anchor_io(&anchor), selected ? 10 : 20));
        ++anchor_cuts;
    }
}
static void interrupted_save(void)
{
    const size_t boundaries[] = {0, 1, 4, 24, 32796, 32800};
    for (unsigned op = 1; op <= 6; ++op) for (unsigned durable = 0; durable < 2; ++durable)
        for (size_t b = 0; b < sizeof(boundaries)/sizeof(boundaries[0]); ++b) {
            prepare(); bits[1] = 2; disks[0].fail_at = disks[0].calls + op;
            disks[0].cut_bytes = boundaries[b]; disks[0].persist_partial = durable != 0;
            CHECK(!ct_replay_store_save(&stores[0], bits, 1));
            load(0); ct_test_anchor_power_cut(&anchor);
            if (ct_replay_store_bind(&stores[0], ct_test_anchor_io(&anchor), 10))
                CHECK(stores[0].filter[0] == 1 && stores[0].filter[1] == 2);
            ++save_cuts;
        }
    for (unsigned op = 1; op <= 4; ++op) for (unsigned commit = 0; commit < 2; ++commit) {
        prepare(); bits[1] = 2; anchor.fail_at = anchor.calls + op; anchor.commit_on_failure = commit != 0;
        CHECK(!ct_replay_store_save(&stores[0], bits, 1));
        load(0); ct_test_anchor_power_cut(&anchor);
        bool bound = ct_replay_store_bind(&stores[0], ct_test_anchor_io(&anchor), 10);
        CHECK(bound == (op == 1 || (op == 2 && !commit) || op == 4));
        if (bound) CHECK(stores[0].filter[0] == 1 && stores[0].filter[1] == (op == 4 ? 2 : 0));
        ++anchor_cuts;
    }
}
/* Regress the same-version fork: a durable candidate with a failed return
 * followed by restoring the previous image must NOT allow another write at
 * that candidate's version. A version-only post-write anchor permits this. */
static void candidate_version_cannot_be_reused(void)
{
    prepare(); bits[1] = 2; disks[0].fail_at = disks[0].calls + 6;
    CHECK(!ct_replay_store_save(&stores[0], bits, 1)); candidate = disks[0];
    disks[0] = old_disk; load(0);
    CHECK(!ct_replay_store_bind(&stores[0], ct_test_anchor_io(&anchor), 10));
    bits[1] = 4; CHECK(!ct_replay_store_save(&stores[0], bits, 1)); ++rollback_checks;
    disks[0] = candidate; load(0);
    CHECK(ct_replay_store_bind(&stores[0], ct_test_anchor_io(&anchor), 10));
    CHECK(stores[0].filter[1] == 2);
}
static void invalid_and_enrollment(void)
{
    prepare(); size_t calls = disks[0].calls, target_calls = disks[1].calls;
    CHECK(!ct_replay_store_switch(NULL, &stores[1], 20));
    CHECK(!ct_replay_store_switch(&stores[0], NULL, 20));
    CHECK(!ct_replay_store_switch(&stores[0], &stores[0], 20));
    CHECK(!ct_replay_store_switch(&stores[0], &stores[1], 0));
    CHECK(!ct_replay_store_switch(&stores[0], &stores[1], 10));
    CHECK(calls == disks[0].calls && target_calls == disks[1].calls);
    /* No-op still consults anchor, but never writes either medium. */
    calls = anchor.replacements;
    CHECK(ct_replay_store_save(&stores[0], bits, 1)); CHECK(calls == anchor.replacements);
    anchor.fail_at = anchor.calls + 1;
    CHECK(!ct_replay_store_save(&stores[0], bits, 1));
    prepare(); anchor.durable.epoch = UINT64_MAX; stores[0].selected = anchor.durable;
    CHECK(!ct_replay_store_switch(&stores[0], &stores[1], 20));
    CHECK(disks[1].calls == 2);
    prepare(); anchor.durable.epoch = UINT64_MAX; stores[0].selected = anchor.durable;
    calls = disks[0].calls; bits[1] = 2;
    CHECK(!ct_replay_store_save(&stores[0], bits, 1) && calls == disks[0].calls);
    /* All four enrollment anchor callback positions, both ambiguous outcomes. */
    for (unsigned op = 1; op <= 4; ++op) for (unsigned commit = 0; commit < 2; ++commit) {
        prepare(); memset(&anchor, 0, sizeof(anchor)); load(0);
        anchor.fail_at = op; anchor.commit_on_failure = commit != 0;
        CHECK(!ct_replay_store_enroll(&stores[0], ct_test_anchor_io(&anchor), 10));
        ct_test_anchor_power_cut(&anchor); load(0);
        CHECK(ct_replay_store_bind(&stores[0], ct_test_anchor_io(&anchor), 10) == (anchor.durable.epoch != 0));
        ++anchor_cuts;
    }
    prepare(); load(0); ct_replay_anchor_io missing = {0};
    CHECK(!ct_replay_store_bind(&stores[0], missing, 10));
    prepare(); load(0); CHECK(!ct_replay_store_bind(&stores[0], ct_test_anchor_io(&anchor), 0));
    prepare(); memset(&anchor.durable, 0, sizeof(anchor.durable)); load(0);
    CHECK(!ct_replay_store_bind(&stores[0], ct_test_anchor_io(&anchor), 10));
}
int main(void)
{
    selection_and_rollback(); interrupted_copy(); interrupted_selection(); interrupted_save(); candidate_version_cannot_be_reused(); invalid_and_enrollment();
    printf("PASS: 6 switch groups; copy_cuts=%zu; save_cuts=%zu; anchor_cuts=%zu; rollback_checks=%zu; store_bytes=%zu\n",
           copy_cuts, save_cuts, anchor_cuts, rollback_checks, sizeof(ct_replay_store));
    return 0;
}
