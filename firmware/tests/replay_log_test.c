#include "cybertrack/replay_log.h"
#include "fake_log.h"
#include "fake_store.h"
#include "fake_anchor.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%d: %s\n", __LINE__, #x); exit(1); } } while (0)
static ct_test_store disk, target_disk, before;
static ct_test_log journal, old_journal;
static ct_replay_store source, target;
static ct_replay_log log_store;
static ct_test_anchor anchor;
static unsigned char bits[CT_REPLAY_BYTES];
static size_t log_cuts, primary_cuts, anchor_cuts, recovery_cuts, corruptions;
static uint64_t le64(const unsigned char *p)
{
    uint64_t n = 0; for (unsigned i = 0; i < 8; ++i) n |= (uint64_t)p[i] << (8*i);
    return n;
}
static unsigned selected_slot(void)
{
    for (unsigned i = 0; i < 2; ++i) {
        const unsigned char *p = journal.durable[i];
        if (le64(p+8) == anchor.durable.epoch && le64(p+16) == anchor.durable.backend_id &&
            le64(p+24) == anchor.durable.revision && le64(p+32) == anchor.durable.session) return i;
    }
    CHECK(false); return 2;
}
static void blank_target(void)
{
    ct_test_store_blank(&target_disk);
    CHECK(ct_replay_store_load(&target, ct_test_store_io(&target_disk)) == CT_STORE_EMPTY);
}
static bool reload(void)
{
    ct_test_store_power_cut(&disk); ct_test_log_power_cut(&journal); ct_test_anchor_power_cut(&anchor);
    CHECK(ct_replay_log_init(&log_store, ct_test_log_io(&journal)));
    (void)ct_replay_store_load(&source, ct_test_store_io(&disk));
    return ct_replay_store_bind(&source, ct_test_anchor_io(&anchor), 1);
}
static void prepare(void)
{
    memset(&anchor, 0, sizeof(anchor)); memset(bits, 0, sizeof(bits));
    ct_test_store_blank(&disk); ct_test_log_blank(&journal);
    CHECK(ct_replay_store_load(&source, ct_test_store_io(&disk)) == CT_STORE_EMPTY);
    CHECK(ct_replay_store_provision(&source));
    CHECK(ct_replay_store_enroll(&source, ct_test_anchor_io(&anchor), 1));
    CHECK(ct_replay_log_init(&log_store, ct_test_log_io(&journal)));
    CHECK(ct_replay_store_attach_log(&source, &log_store));
    bits[0] = 1; CHECK(ct_replay_store_save(&source, bits, 1));
    before = disk; blank_target();
}
static ct_replay_recovery_result recover(void)
{
    return ct_replay_store_recover_log(&source, &log_store, ct_test_anchor_io(&anchor), 1, &target, 2);
}
static void exact_and_independent(void)
{
    prepare(); uint64_t rev = source.revision, epoch = anchor.durable.epoch;
    size_t writes = journal.calls; CHECK(ct_replay_store_save(&source, bits, 1));
    CHECK(writes == journal.calls && epoch == anchor.durable.epoch);
    bits[1] = 2; disk.fail_at = disk.calls + 1; /* Reservation + log durable, primary erase fails. */
    CHECK(!ct_replay_store_save(&source, bits, 1));
    CHECK(anchor.durable.revision == rev + 1 && anchor.durable.epoch == epoch + 2);
    CHECK(!reload()); before = disk;
    size_t calls = disk.calls; old_journal = journal;
    CHECK(recover() == CT_RECOVERY_OK && disk.calls == calls);
    CHECK(!memcmp(target.filter, bits, sizeof(bits)));
    CHECK(!memcmp(disk.durable, before.durable, sizeof(disk.durable)));
    CHECK(!memcmp(journal.durable, old_journal.durable, sizeof(journal.durable)));
    CHECK(!source.log && target.anchor_bound && !target.log);
    CHECK(!reload()); blank_target(); CHECK(recover() == CT_RECOVERY_WRONG_BACKEND);
}
static void interrupted_log(void)
{
    const size_t boundary[] = {0,1,4,8,16,24,32,40,32808,32812,32816};
    /* Both bridge and candidate: two selection reads and six write/readback
     * operations each. Losing the primary cannot turn a candidate into proof. */
    for (unsigned op = 1; op <= 16; ++op) for (unsigned durable = 0; durable < 2; ++durable)
        for (size_t b = 0; b < sizeof(boundary)/sizeof(boundary[0]); ++b) {
            prepare(); old_journal = journal; uint64_t rev = source.revision;
            unsigned retained = selected_slot(); size_t calls = disk.calls;
            journal.fail_at = journal.calls + op; journal.cut_bytes = boundary[b]; journal.persist_partial = durable != 0;
            bits[1] = 2; CHECK(!ct_replay_store_save(&source, bits, 1));
            CHECK(!log_store.ready && source.state == CT_STORE_FAULT && calls == disk.calls);
            CHECK(anchor.durable.revision == rev);
            if (op <= 8) CHECK(!memcmp(journal.durable[retained], old_journal.durable[retained], CT_REPLAY_LOG_SLOT_BYTES));
            CHECK(reload()); CHECK(source.filter[0] == 1 && source.filter[1] == 0);
            CHECK(!memcmp(disk.durable, before.durable, sizeof(disk.durable)));
            ct_test_store_blank(&disk); CHECK(!reload()); old_journal = journal;
            CHECK(recover() == CT_RECOVERY_OK); /* Exact old/bridge record, never the new candidate. */
            bits[1] = 0; CHECK(!memcmp(target.filter, bits, sizeof(bits)));
            CHECK(!memcmp(journal.durable, old_journal.durable, sizeof(journal.durable))); ++log_cuts;
        }
}
static void interrupted_primary_and_anchor(void)
{
    const size_t boundary[] = {0,1,4,24,32796,32800};
    for (unsigned op = 1; op <= 6; ++op) for (unsigned durable = 0; durable < 2; ++durable)
        for (size_t b = 0; b < sizeof(boundary)/sizeof(boundary[0]); ++b) {
            prepare(); bits[1] = 2; disk.fail_at = disk.calls + op;
            disk.cut_bytes = boundary[b]; disk.persist_partial = durable != 0;
            CHECK(!ct_replay_store_save(&source, bits, 1)); (void)reload();
            CHECK(recover() == CT_RECOVERY_OK); CHECK(!memcmp(target.filter, bits, sizeof(bits))); ++primary_cuts;
        }
    for (unsigned op = 1; op <= 6; ++op) for (unsigned commit = 0; commit < 2; ++commit) {
        prepare(); bits[1] = 2; anchor.fail_at = anchor.calls + op; anchor.commit_on_failure = commit != 0;
        CHECK(!ct_replay_store_save(&source, bits, 1)); bool primary_ok = reload();
        bool new_record = op >= 5 || (op == 4 && commit);
        CHECK(primary_ok == (!new_record || op == 6));
        ct_test_store_blank(&disk); CHECK(!reload());
        CHECK(recover() == CT_RECOVERY_OK);
        if (!new_record) bits[1] = 0;
        CHECK(!memcmp(target.filter, bits, sizeof(bits)));
        ++anchor_cuts;
    }
}
static void failed_candidate_cannot_be_relabelled(void)
{
    prepare(); bits[1] = 2; anchor.fail_at = anchor.calls + 4; /* Candidate durable, anchor unchanged. */
    CHECK(!ct_replay_store_save(&source, bits, 1)); old_journal = journal;
    uint64_t old_epoch = anchor.durable.epoch;
    CHECK(reload()); CHECK(ct_replay_store_attach_log(&source, &log_store));
    bits[1] = 0; bits[2] = 4; CHECK(ct_replay_store_save(&source, bits, 1));
    CHECK(anchor.durable.epoch == old_epoch + 2);
    journal = old_journal; ct_test_store_blank(&disk); CHECK(!reload());
    CHECK(recover() == CT_RECOVERY_HISTORY_UNAVAILABLE);
}
static void interrupted_recovery(void)
{
    const size_t boundary[] = {0,1,4,24,32796,32800};
    for (unsigned op = 1; op <= 14; ++op) for (unsigned durable = 0; durable < 2; ++durable)
        for (size_t b = 0; b < sizeof(boundary)/sizeof(boundary[0]); ++b) {
            prepare(); ct_test_store_blank(&disk); CHECK(!reload()); old_journal = journal;
            target_disk.fail_at = target_disk.calls + op; target_disk.cut_bytes = boundary[b];
            target_disk.persist_partial = durable != 0;
            CHECK(recover() == CT_RECOVERY_DESTINATION_UNAVAILABLE);
            CHECK(!memcmp(journal.durable, old_journal.durable, sizeof(journal.durable)));
            (void)reload(); blank_target(); CHECK(recover() == CT_RECOVERY_OK);
            CHECK(!memcmp(target.filter, bits, sizeof(bits))); ++recovery_cuts;
        }
}
static void bad_evidence_and_configuration(void)
{
    const size_t locations[] = {0,4,8,16,24,32,40,32807,32808,32812,32815};
    for (size_t i = 0; i < sizeof(locations)/sizeof(locations[0]); ++i) for (unsigned b = 0; b < 8; ++b) {
        prepare(); unsigned slot = selected_slot();
        journal.durable[slot][locations[i]] ^= (unsigned char)(1u << b);
        (void)reload(); CHECK(recover() == CT_RECOVERY_HISTORY_UNAVAILABLE); ++corruptions;
    }
    prepare(); journal.fail_at = journal.calls + 1; CHECK(recover() == CT_RECOVERY_HISTORY_UNAVAILABLE);
    prepare(); CHECK(!ct_replay_log_init(NULL, ct_test_log_io(&journal)));
    CHECK(!ct_replay_log_init(&log_store, (ct_replay_io){0}));
    bits[1] = 2; CHECK(!ct_replay_store_save(&source, bits, 1)); /* Never silent unlogged fallback. */
    prepare(); CHECK(!ct_replay_store_attach_log(&source, &log_store));
    prepare(); CHECK(reload());
    log_store.io.context = source.io.context; CHECK(!ct_replay_store_attach_log(&source, &log_store));
    prepare(); anchor.durable.epoch = UINT64_MAX - 1; source.selected = anchor.durable;
    size_t calls = journal.calls; bits[1] = 2;
    CHECK(!ct_replay_store_save(&source, bits, 1) && calls == journal.calls);
}
static void repeated_preparation_and_relocation(void)
{
    prepare();
    /* Old CTLG v1 placement remains readable; slot position is not evidence. */
    memcpy(log_store.scratch, journal.durable[0], CT_REPLAY_LOG_SLOT_BYTES);
    memcpy(journal.durable[0], journal.durable[1], CT_REPLAY_LOG_SLOT_BYTES);
    memcpy(journal.durable[1], log_store.scratch, CT_REPLAY_LOG_SLOT_BYTES);
    ct_test_store_blank(&disk); CHECK(!reload()); CHECK(recover() == CT_RECOVERY_OK);
    CHECK(!memcmp(target.filter, bits, sizeof(bits)));
    prepare();
    for (unsigned i = 0; i < 100; ++i) {
        CHECK(reload()); CHECK(ct_replay_store_attach_log(&source, &log_store));
        uint64_t epoch = anchor.durable.epoch;
        journal.fail_at = journal.calls + 12; journal.persist_partial = true;
        journal.cut_bytes = CT_REPLAY_LOG_SLOT_BYTES;
        bits[1] = (unsigned char)(1u << (i % 8));
        CHECK(!ct_replay_store_save(&source, bits, 1));
        CHECK(anchor.durable.epoch == epoch + 1);
    }
    ct_test_store_blank(&disk); CHECK(!reload()); CHECK(recover() == CT_RECOVERY_OK);
    bits[1] = 0; CHECK(!memcmp(target.filter, bits, sizeof(bits)));
}
static void ambiguous_and_unselected_evidence(void)
{
    prepare(); unsigned slot = selected_slot();
    memcpy(journal.durable[1-slot], journal.durable[slot], CT_REPLAY_LOG_SLOT_BYTES);
    CHECK(reload()); CHECK(recover() == CT_RECOVERY_HISTORY_UNAVAILABLE);
    CHECK(reload()); CHECK(ct_replay_store_attach_log(&source, &log_store));
    uint64_t epoch = anchor.durable.epoch; size_t calls = disk.calls;
    bits[1] = 2; CHECK(!ct_replay_store_save(&source, bits, 1));
    CHECK(epoch == anchor.durable.epoch && calls == disk.calls);
    prepare(); unsigned current = selected_slot();
    /* A complete bridge before CAS is NOT current history for another epoch. */
    anchor.fail_at = anchor.calls + 2;
    bits[1] = 2; CHECK(!ct_replay_store_save(&source, bits, 1));
    memset(journal.durable[current], 0xff, CT_REPLAY_LOG_SLOT_BYTES);
    ct_test_store_blank(&disk); CHECK(!reload()); CHECK(recover() == CT_RECOVERY_HISTORY_UNAVAILABLE);
    for (unsigned op = 1; op <= 2; ++op) {
        prepare(); journal.fail_at = journal.calls + op;
        CHECK(recover() == CT_RECOVERY_HISTORY_UNAVAILABLE);
    }
}
int main(void)
{
    exact_and_independent(); interrupted_log(); interrupted_primary_and_anchor();
    failed_candidate_cannot_be_relabelled(); interrupted_recovery(); bad_evidence_and_configuration();
    repeated_preparation_and_relocation(); ambiguous_and_unselected_evidence();
    printf("PASS: 8 log groups; log_cuts=%zu; primary_cuts=%zu; anchor_cuts=%zu; recovery_cuts=%zu; corruptions=%zu; repeated_preparations=100; store_bytes=%zu; log_bytes=%zu; lost_bits=0\n",
           log_cuts, primary_cuts, anchor_cuts, recovery_cuts, corruptions, sizeof(source), sizeof(log_store));
    return 0;
}
