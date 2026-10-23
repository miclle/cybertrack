#include "fake_store.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(EXIT_FAILURE); } } while (0)
static ct_test_store disk, baseline;
static ct_replay_store store, recovered;
static unsigned char filter[CT_REPLAY_BYTES];
static size_t cuts, corruptions;

static void provision(void)
{
    ct_test_store_blank(&disk);
    CHECK(ct_replay_store_load(&store, ct_test_store_io(&disk)) == CT_STORE_EMPTY);
    CHECK(!ct_replay_store_save(&store, filter, 0));
    CHECK(ct_replay_store_provision(&store));
    CHECK(store.revision == 2 && store.session == 0 && store.state == CT_STORE_READY);
    CHECK(!ct_replay_store_provision(&store));
}
static void roundtrip_and_contract(void)
{
    CHECK(ct_replay_store_load(NULL, ct_test_store_io(&disk)) == CT_STORE_FAULT);
    CHECK(ct_replay_store_load(&store, (ct_replay_io){0}) == CT_STORE_FAULT);
    CHECK(!ct_replay_store_provision(NULL) && !ct_replay_store_save(NULL, filter, 0));
    provision(); memset(filter, 0, sizeof(filter)); filter[5] = 1;
    CHECK(ct_replay_store_save(&store, filter, 1));
    CHECK(store.revision == 3 && store.slot == 0);
    size_t calls = disk.calls;
    CHECK(ct_replay_store_save(&store, filter, 1) && disk.calls == calls);
    ct_test_store_power_cut(&disk);
    CHECK(ct_replay_store_load(&recovered, ct_test_store_io(&disk)) == CT_STORE_READY);
    CHECK(recovered.session == 1 && recovered.revision == 3 && recovered.filter[5] == 1);
    CHECK(!memcmp(recovered.filter, filter, sizeof(filter)));
    baseline = disk;
    filter[5] = 0;
    CHECK(!ct_replay_store_save(&store, filter, 1) && store.state == CT_STORE_FAULT);
    filter[5] = 1;
    CHECK(!ct_replay_store_save(&store, filter, 1));
    CHECK(ct_replay_store_load(&store, ct_test_store_io(&disk)) == CT_STORE_READY);
    CHECK(!ct_replay_store_save(&store, filter, 0));
    CHECK(ct_replay_store_load(&store, ct_test_store_io(&disk)) == CT_STORE_READY);
    CHECK(!ct_replay_store_save(&store, filter, 3));
    CHECK(ct_replay_store_load(&store, ct_test_store_io(&disk)) == CT_STORE_READY);
    store.revision = UINT64_MAX; filter[9] = 2;
    CHECK(!ct_replay_store_save(&store, filter, 1));
}
static void torn_save(void)
{
    const size_t boundaries[] = {0,1,3,4,7,8,15,16,23,24,25,4095,4096,16384,32767,32768,32791,32792,32795,32796,32799,32800};
    for (size_t operation = 1; operation <= 6; ++operation) {
        for (unsigned durable = 0; durable < 2; ++durable) {
            for (size_t i = 0; i < sizeof(boundaries)/sizeof(boundaries[0]); ++i) {
                disk = baseline;
                CHECK(ct_replay_store_load(&store, ct_test_store_io(&disk)) == CT_STORE_READY);
                memcpy(filter, store.filter, sizeof(filter)); filter[9] = 2;
                disk.fail_at = disk.calls + operation;
                disk.cut_bytes = boundaries[i]; disk.persist_partial = durable != 0;
                CHECK(!ct_replay_store_save(&store, filter, 2) && store.state == CT_STORE_FAULT);
                CHECK(!ct_replay_store_save(&store, filter, 2));
                ct_test_store_power_cut(&disk);
                ct_store_state state = ct_replay_store_load(&recovered, ct_test_store_io(&disk));
                CHECK(state != CT_STORE_EMPTY);
                if (state == CT_STORE_READY) {
                    CHECK(recovered.filter[5] == 1); /* Prior durable intent never lost. */
                    CHECK(recovered.session == 1 || recovered.session == 2);
                    if (recovered.session == 2) CHECK(recovered.filter[9] == 2);
                }
                ++cuts;
            }
        }
    }
    disk = baseline; CHECK(ct_replay_store_load(&store, ct_test_store_io(&disk)) == CT_STORE_READY);
    CHECK(ct_replay_store_save(&store, filter, 2));
    ct_test_store_power_cut(&disk);
    CHECK(ct_replay_store_load(&recovered, ct_test_store_io(&disk)) == CT_STORE_READY);
    CHECK(recovered.filter[5] == 1 && recovered.filter[9] == 2 && recovered.session == 2);
}
static void damaged_media_and_load(void)
{
    const size_t offsets[] = {0,4,7,8,15,16,23,24,29,4096,16384,32791,32792,32795,32796,32799};
    for (unsigned slot = 0; slot < 2; ++slot) {
        for (size_t i = 0; i < sizeof(offsets)/sizeof(offsets[0]); ++i) {
            for (unsigned bit = 0; bit < 8; ++bit) {
                disk = baseline; disk.durable[slot][offsets[i]] ^= (unsigned char)(1u << bit);
                ct_test_store_power_cut(&disk);
                CHECK(ct_replay_store_load(&store, ct_test_store_io(&disk)) == CT_STORE_FAULT);
                CHECK(!ct_replay_store_provision(&store)); ++corruptions;
            }
        }
        disk = baseline; memset(disk.durable[slot], 0xff, CT_REPLAY_SLOT_BYTES);
        ct_test_store_power_cut(&disk);
        CHECK(ct_replay_store_load(&store, ct_test_store_io(&disk)) == CT_STORE_FAULT);
        disk = baseline; disk.fail_at = disk.calls + slot + 1;
        CHECK(ct_replay_store_load(&store, ct_test_store_io(&disk)) == CT_STORE_FAULT);
    }
    /* CRC-valid but discontinuous revisions must not select an older history. */
    disk = baseline; CHECK(ct_replay_store_load(&store, ct_test_store_io(&disk)) == CT_STORE_READY);
    store.revision += 2; memcpy(filter, store.filter, sizeof(filter)); filter[12] = 1;
    CHECK(ct_replay_store_save(&store, filter, store.session));
    CHECK(ct_replay_store_load(&recovered, ct_test_store_io(&disk)) == CT_STORE_FAULT);
}
static void interrupted_provision(void)
{
    for (size_t operation = 1; operation <= 14; ++operation) {
        ct_test_store_blank(&disk);
        CHECK(ct_replay_store_load(&store, ct_test_store_io(&disk)) == CT_STORE_EMPTY);
        disk.fail_at = disk.calls + operation; disk.cut_bytes = 17; disk.persist_partial = true;
        CHECK(!ct_replay_store_provision(&store));
        ct_test_store_power_cut(&disk);
        ct_store_state state = ct_replay_store_load(&recovered, ct_test_store_io(&disk));
        if (state == CT_STORE_READY) CHECK(recovered.session == 0 && recovered.revision == 2);
        ++cuts;
    }
    ct_test_store_blank(&disk);
    CHECK(ct_replay_store_load(&store, ct_test_store_io(&disk)) == CT_STORE_EMPTY);
    disk.pending[0][0] = 0; /* Media changed between load and local provisioning. */
    CHECK(!ct_replay_store_provision(&store));
}
int main(void)
{
    roundtrip_and_contract(); torn_save(); damaged_media_and_load(); interrupted_provision();
    printf("PASS: 4 store groups; cut_cases=%zu; bit_corruptions=%zu; slot_bytes=%u; store_bytes=%zu\n", cuts, corruptions, CT_REPLAY_SLOT_BYTES, sizeof(store));
    return EXIT_SUCCESS;
}
