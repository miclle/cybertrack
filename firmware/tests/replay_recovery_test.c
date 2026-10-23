#include "fake_anchor.h"
#include "fake_store.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%d: %s\n", __LINE__, #x); exit(1); } } while (0)
static ct_test_store disks[2], source_image, older_image;
static ct_replay_store stores[2];
static ct_test_anchor anchor;
static unsigned char history[CT_REPLAY_BYTES];
static size_t target_cuts, anchor_cuts, source_cuts, rejected_histories;
static void load(unsigned i)
{
    ct_test_store_power_cut(&disks[i]);
    (void)ct_replay_store_load(&stores[i], ct_test_store_io(&disks[i]));
}
static void blank_target(void)
{
    ct_test_store_blank(&disks[1]); load(1); CHECK(stores[1].state == CT_STORE_EMPTY);
}
static void prepare(bool damage)
{
    memset(&anchor, 0, sizeof(anchor)); memset(history, 0, sizeof(history));
    ct_test_store_blank(&disks[0]); load(0); CHECK(ct_replay_store_provision(&stores[0]));
    CHECK(ct_replay_store_enroll(&stores[0], ct_test_anchor_io(&anchor), 10));
    history[0] = 1; CHECK(ct_replay_store_save(&stores[0], history, 1)); older_image = disks[0];
    history[1] = 2; CHECK(ct_replay_store_save(&stores[0], history, 1));
    if (damage) memset(disks[0].durable[1 - stores[0].slot], 0xff, CT_REPLAY_SLOT_BYTES);
    load(0); CHECK(stores[0].state == (damage ? CT_STORE_FAULT : CT_STORE_READY));
    source_image = disks[0]; blank_target();
}
static ct_replay_recovery_result recover(void)
{
    return ct_replay_store_recover(&stores[0], ct_test_anchor_io(&anchor), 10, &stores[1], 20);
}
static void source_unchanged(void)
{
    CHECK(!memcmp(disks[0].durable, source_image.durable, sizeof(disks[0].durable)));
    CHECK(!memcmp(disks[0].pending, source_image.pending, sizeof(disks[0].pending)));
}
static void exact_snapshot(void)
{
    for (unsigned damage = 0; damage < 2; ++damage) {
        prepare(damage != 0); uint64_t revision = anchor.durable.revision;
        /* A failed load's RAM is never evidence: recovery must re-read bytes. */
        memset(stores[0].filter, 0x80, sizeof(stores[0].filter));
        stores[0].revision = stores[0].session = UINT64_MAX;
        CHECK(recover() == CT_RECOVERY_OK); source_unchanged();
        CHECK(stores[0].state == CT_STORE_FAULT && stores[1].state == CT_STORE_READY);
        CHECK(stores[1].revision == revision + 2 && stores[1].session == 1);
        CHECK(!memcmp(stores[1].filter, history, sizeof(history)));
        load(1); CHECK(ct_replay_store_bind(&stores[1], ct_test_anchor_io(&anchor), 20));
        load(0); CHECK(!ct_replay_store_bind(&stores[0], ct_test_anchor_io(&anchor), 10));
    }
}
static void interrupted_target(void)
{
    const size_t boundaries[] = {0,1,4,24,32796,32800};
    for (unsigned op = 1; op <= 14; ++op) for (unsigned durable = 0; durable < 2; ++durable)
        for (size_t b = 0; b < sizeof(boundaries)/sizeof(boundaries[0]); ++b) {
            prepare(true); disks[1].fail_at = disks[1].calls + op;
            disks[1].cut_bytes = boundaries[b]; disks[1].persist_partial = durable != 0;
            CHECK(recover() == CT_RECOVERY_DESTINATION_UNAVAILABLE); source_unchanged();
            CHECK(stores[0].state == CT_STORE_FAULT && stores[1].state == CT_STORE_FAULT);
            CHECK(anchor.durable.backend_id == 10);
            load(1); CHECK(!ct_replay_store_bind(&stores[1], ct_test_anchor_io(&anchor), 20));
            /* Repeated maintenance needs a fresh independent blank replacement.
             * Fake reset below is not a production erase/repair API. */
            load(0); blank_target(); CHECK(recover() == CT_RECOVERY_OK);
            CHECK(!memcmp(stores[1].filter, history, sizeof(history))); ++target_cuts;
        }
}
static void interrupted_anchor_and_source(void)
{
    for (unsigned op = 1; op <= 4; ++op) for (unsigned commit = 0; commit < 2; ++commit) {
        prepare(true); anchor.fail_at = anchor.calls + op; anchor.commit_on_failure = commit != 0;
        CHECK(recover() == (op <= 2 ? CT_RECOVERY_ANCHOR_UNAVAILABLE : CT_RECOVERY_SELECTION_UNCERTAIN));
        source_unchanged(); ct_test_anchor_power_cut(&anchor); load(0); load(1);
        if (anchor.durable.backend_id == 20) {
            CHECK(ct_replay_store_bind(&stores[1], ct_test_anchor_io(&anchor), 20));
            CHECK(!memcmp(stores[1].filter, history, sizeof(history)));
            blank_target(); CHECK(recover() == CT_RECOVERY_WRONG_BACKEND);
        } else {
            CHECK(!ct_replay_store_bind(&stores[1], ct_test_anchor_io(&anchor), 20));
            blank_target(); CHECK(recover() == CT_RECOVERY_OK);
        }
        ++anchor_cuts;
    }
    for (unsigned op = 1; op <= 2; ++op) {
        prepare(true); disks[0].fail_at = disks[0].calls + op; size_t calls = disks[1].calls;
        CHECK(recover() == CT_RECOVERY_HISTORY_UNAVAILABLE); CHECK(calls == disks[1].calls);
        source_unchanged(); ++source_cuts;
    }
}
static void fix_crc(unsigned char *p)
{
    uint32_t crc = UINT32_MAX;
    for (size_t i = 0; i < CT_REPLAY_BYTES + 24; ++i) {
        crc ^= p[i]; for (unsigned b = 0; b < 8; ++b) crc = (crc >> 1) ^ ((crc & 1) ? UINT32_C(0xedb88320) : 0);
    }
    crc = ~crc;
    for (unsigned b = 0; b < 4; ++b) p[CT_REPLAY_BYTES + 24 + b] = (unsigned char)(crc >> (8*b));
}
static void unavailable_and_contradictory_history(void)
{
    for (unsigned mode = 0; mode < 7; ++mode) {
        prepare(false);
        ct_replay_recovery_result expected = CT_RECOVERY_HISTORY_UNAVAILABLE;
        if (mode == 0) disks[0] = older_image; /* Old, valid pair; anchor is one ahead. */
        if (mode == 1) memset(disks[0].durable[stores[0].slot], 0xff, CT_REPLAY_SLOT_BYTES);
        if (mode == 2) disks[0].durable[stores[0].slot][24] ^= 1;
        if (mode == 3) { /* Real interrupted reservation; no matching snapshot exists. */
            CHECK(ct_replay_store_bind(&stores[0], ct_test_anchor_io(&anchor), 10));
            history[2] = 4; anchor.fail_at = anchor.calls + 3;
            CHECK(!ct_replay_store_save(&stores[0], history, 1)); ct_test_anchor_power_cut(&anchor);
        }
        if (mode == 4) { /* Contradictory future image; never discard its extra bits. */
            anchor.durable.revision -= 1; expected = CT_RECOVERY_HISTORY_CONFLICT;
        }
        if (mode == 5) {
            unsigned char *p = disks[0].durable[1 - stores[0].slot]; p[26] |= 0x80; fix_crc(p);
            expected = CT_RECOVERY_HISTORY_CONFLICT;
        }
        if (mode == 6) { /* Exact version but different session, even with valid CRC. */
            unsigned char *p = disks[0].durable[stores[0].slot]; p[16] = 0; fix_crc(p);
        }
        load(0); source_image = disks[0]; size_t calls = disks[1].calls;
        CHECK(recover() == expected && calls == disks[1].calls); source_unchanged();
        CHECK(anchor.durable.backend_id == 10); ++rejected_histories;
    }
}
static void invalid_and_stale_inputs(void)
{
    prepare(true); ct_replay_anchor_io io = ct_test_anchor_io(&anchor);
    CHECK(ct_replay_store_recover(NULL, io, 10, &stores[1], 20) == CT_RECOVERY_BAD_ARGUMENT);
    CHECK(ct_replay_store_recover(&stores[0], io, 10, NULL, 20) == CT_RECOVERY_BAD_ARGUMENT);
    CHECK(ct_replay_store_recover(&stores[0], io, 10, &stores[0], 20) == CT_RECOVERY_BAD_ARGUMENT);
    CHECK(ct_replay_store_recover(&stores[0], io, 10, &stores[1], 10) == CT_RECOVERY_BAD_ARGUMENT);
    CHECK(ct_replay_store_recover(&stores[0], io, 0, &stores[1], 20) == CT_RECOVERY_BAD_ARGUMENT);
    CHECK(ct_replay_store_recover(&stores[0], (ct_replay_anchor_io){0}, 10, &stores[1], 20) == CT_RECOVERY_BAD_ARGUMENT);
    CHECK(ct_replay_store_recover(&stores[0], io, 99, &stores[1], 20) == CT_RECOVERY_WRONG_BACKEND);
    prepare(true); stores[1].io.context = stores[0].io.context;
    CHECK(recover() == CT_RECOVERY_BAD_ARGUMENT);
    prepare(true); CHECK(ct_replay_store_provision(&stores[1])); CHECK(recover() == CT_RECOVERY_BAD_ARGUMENT);
    prepare(true); disks[1].pending[0][0] = 0;
    CHECK(recover() == CT_RECOVERY_DESTINATION_UNAVAILABLE && disks[1].pending[0][0] == 0);
    prepare(true); anchor.durable = (ct_replay_anchor_record){0}; CHECK(recover() == CT_RECOVERY_ANCHOR_UNAVAILABLE);
    prepare(true); anchor.durable.epoch = UINT64_MAX; CHECK(recover() == CT_RECOVERY_EXHAUSTED);
    prepare(true); anchor.durable.revision = UINT64_MAX - 1; CHECK(recover() == CT_RECOVERY_EXHAUSTED);
}
int main(void)
{
    exact_snapshot(); interrupted_target(); interrupted_anchor_and_source();
    unavailable_and_contradictory_history(); invalid_and_stale_inputs();
    printf("PASS: 5 recovery groups; target_cuts=%zu; anchor_cuts=%zu; source_cuts=%zu; rejected_histories=%zu; history_bits_lost=0; source_mutations=0\n",
           target_cuts, anchor_cuts, source_cuts, rejected_histories);
    return 0;
}
