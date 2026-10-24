#include "fake_log.h"
#include "fake_anchor.h"
#include "fake_store.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%d: %s\n", __LINE__, #x); exit(1); } } while (0)
static ct_test_store disks[3], original;
static ct_replay_store stores[3];
static ct_test_log journal;
static ct_replay_log log_store;
static ct_test_anchor anchor;
static unsigned char bits[CT_REPLAY_BYTES];
static size_t enrollment_cuts, attach_cuts, switch_cuts, recovery_cuts, anchor_cuts, cycles;
static const size_t edges[] = {0,1,4,8,16,24,32,40,32808,32812,32816};
static void load(unsigned i)
{
    ct_test_store_power_cut(&disks[i]);
    (void)ct_replay_store_load(&stores[i], ct_test_store_io(&disks[i]));
}
static void blank(unsigned i) { ct_test_store_blank(&disks[i]); load(i); }
static void reboot(void)
{
    ct_test_anchor_power_cut(&anchor); ct_test_log_power_cut(&journal);
    CHECK(ct_replay_log_init(&log_store, ct_test_log_io(&journal)));
}
static void prepare(bool enrolled)
{
    memset(&anchor, 0, sizeof(anchor)); memset(bits, 0, sizeof(bits));
    for (unsigned i=0; i<3; ++i) blank(i);
    ct_test_log_blank(&journal); reboot();
    CHECK(ct_replay_store_provision(&stores[0]));
    for (size_t i=0; i<sizeof(bits); i+=31) bits[i]=(unsigned char)(i|1);
    CHECK(ct_replay_store_save(&stores[0], bits, 1)); original=disks[0];
    if (enrolled) CHECK(ct_replay_store_enroll_logged(&stores[0], &log_store, ct_test_anchor_io(&anchor), 1));
}
static bool enroll(void) { return ct_replay_store_enroll_logged(&stores[0], &log_store, ct_test_anchor_io(&anchor), 1); }
static ct_replay_recovery_result recover(unsigned source, unsigned dest)
{
    return ct_replay_store_recover_log(&stores[source], &log_store, ct_test_anchor_io(&anchor), source+1, &stores[dest], dest+1);
}
static void missing(unsigned i) { blank(i); reboot(); }
static void complete(unsigned source, unsigned dest)
{
    CHECK(recover(source,dest)==CT_RECOVERY_OK);
    CHECK(!memcmp(stores[dest].filter,bits,sizeof(bits)));
    CHECK(stores[dest].log==&log_store && anchor.durable.backend_id==dest+1);
}
static void cut_log(unsigned op, unsigned durable, size_t bytes)
{
    journal.fail_at=journal.calls+op; journal.persist_partial=durable!=0; journal.cut_bytes=bytes;
}
static void initial_selection(void)
{
    prepare(false); CHECK(enroll());
    CHECK(!memcmp(disks[0].durable,original.durable,sizeof(original.durable)));
    missing(0); complete(0,1); /* No first save/bridge/attach after enrollment. */
    for (unsigned op=1; op<=8; ++op) for (unsigned durable=0; durable<2; ++durable)
        for (size_t b=0; b<sizeof(edges)/sizeof(edges[0]); ++b) {
            prepare(false); cut_log(op,durable,edges[b]); CHECK(!enroll());
            CHECK(!anchor.durable.epoch && stores[0].state==CT_STORE_FAULT);
            CHECK(!memcmp(disks[0].durable,original.durable,sizeof(original.durable)));
            load(0); reboot(); CHECK(enroll()); missing(0); complete(0,1); ++enrollment_cuts;
        }
    for (unsigned op=1; op<=4; ++op) for (unsigned commit=0; commit<2; ++commit) {
        prepare(false); anchor.fail_at=anchor.calls+op; anchor.commit_on_failure=commit!=0;
        CHECK(!enroll()); bool selected=op>=3 || (op==2 && commit);
        CHECK((anchor.durable.epoch!=0)==selected);
        missing(0);
        if (selected) complete(0,1);
        else CHECK(recover(0,1)==CT_RECOVERY_ANCHOR_UNAVAILABLE);
        ++anchor_cuts;
    }
}
static void legacy_attachment(void)
{
    for (unsigned op=1; op<=8; ++op) for (unsigned durable=0; durable<2; ++durable)
        for (size_t b=0; b<sizeof(edges)/sizeof(edges[0]); ++b) {
            prepare(false); CHECK(ct_replay_store_enroll(&stores[0],ct_test_anchor_io(&anchor),1));
            cut_log(op,durable,edges[b]); CHECK(!ct_replay_store_attach_log(&stores[0],&log_store));
            CHECK(stores[0].state==CT_STORE_FAULT && !stores[0].log);
            bool persisted=op==8 || (durable && ((op==6 && edges[b]>=4) || (op==7 && edges[b]==CT_REPLAY_LOG_SLOT_BYTES)));
            missing(0);
            if (persisted) complete(0,1);
            else CHECK(recover(0,1)==CT_RECOVERY_HISTORY_UNAVAILABLE);
            ++attach_cuts;
        }
    prepare(false); CHECK(ct_replay_store_enroll(&stores[0],ct_test_anchor_io(&anchor),1));
    CHECK(ct_replay_store_attach_log(&stores[0],&log_store)); missing(0); complete(0,1);
    /* Existing exact evidence is reused without making duplicate records. */
    prepare(true); load(0); CHECK(ct_replay_store_bind(&stores[0],ct_test_anchor_io(&anchor),1));
    size_t calls=journal.calls; CHECK(ct_replay_store_attach_log(&stores[0],&log_store));
    CHECK(journal.calls==calls+2); missing(0); complete(0,1);
}
static void switching(void)
{
    prepare(true); CHECK(ct_replay_store_switch(&stores[0],&stores[1],2));
    CHECK(stores[1].log==&log_store); missing(1); complete(1,2);
    for (unsigned op=1; op<=8; ++op) for (unsigned durable=0; durable<2; ++durable)
        for (size_t b=0; b<sizeof(edges)/sizeof(edges[0]); ++b) {
            prepare(true); cut_log(op,durable,edges[b]);
            CHECK(!ct_replay_store_switch(&stores[0],&stores[1],2));
            CHECK(anchor.durable.backend_id==1 && stores[1].state==CT_STORE_FAULT);
            CHECK(!memcmp(disks[0].durable,original.durable,sizeof(original.durable)));
            missing(0); complete(0,2); ++switch_cuts;
        }
    for (unsigned op=1; op<=3; ++op) for (unsigned commit=0; commit<2; ++commit) {
        prepare(true); anchor.fail_at=anchor.calls+op; anchor.commit_on_failure=commit!=0;
        CHECK(!ct_replay_store_switch(&stores[0],&stores[1],2));
        unsigned selected=(unsigned)anchor.durable.backend_id-1;
        missing(selected); complete(selected,2); ++anchor_cuts;
    }
}
static void recovering(void)
{
    for (unsigned op=1; op<=10; ++op) for (unsigned durable=0; durable<2; ++durable)
        for (size_t b=0; b<sizeof(edges)/sizeof(edges[0]); ++b) {
            prepare(true); missing(0); cut_log(op,durable,edges[b]);
            CHECK(recover(0,1)==(op<=2 ? CT_RECOVERY_HISTORY_UNAVAILABLE : CT_RECOVERY_LOG_UNAVAILABLE));
            CHECK(anchor.durable.backend_id==1 && stores[1].state==CT_STORE_FAULT);
            reboot(); complete(0,2); ++recovery_cuts;
        }
    for (unsigned op=1; op<=4; ++op) for (unsigned commit=0; commit<2; ++commit) {
        prepare(true); missing(0); anchor.fail_at=anchor.calls+op; anchor.commit_on_failure=commit!=0;
        CHECK(recover(0,1)!=CT_RECOVERY_OK);
        unsigned selected=(unsigned)anchor.durable.backend_id-1;
        missing(selected); complete(selected,2); ++anchor_cuts;
    }
    prepare(true); unsigned selected=0;
    for (unsigned i=0; i<100; ++i) {
        missing(selected); unsigned dest=1-selected; blank(dest); complete(selected,dest);
        selected=dest; ++cycles; /* No session open or intervening bridge write. */
    }
}
static void configuration_and_conflicts(void)
{
    prepare(false); CHECK(!ct_replay_store_enroll_logged(&stores[0],NULL,ct_test_anchor_io(&anchor),1));
    log_store.io.context=stores[0].io.context; CHECK(!enroll()); CHECK(!anchor.durable.epoch);
    prepare(true); load(0); CHECK(!enroll()); /* Used anchor cannot be re-enrolled. */
    prepare(true); load(0); CHECK(ct_replay_store_bind(&stores[0],ct_test_anchor_io(&anchor),1));
    stores[0].filter[1]^=1; CHECK(!ct_replay_store_attach_log(&stores[0],&log_store));
    prepare(false); anchor.fail_at=anchor.calls+2; CHECK(!enroll());
    load(0); reboot(); stores[0].filter[1]^=1; CHECK(!enroll()); CHECK(!anchor.durable.epoch);
    prepare(true); log_store.io.context=stores[1].io.context;
    CHECK(!ct_replay_store_switch(&stores[0],&stores[1],2)); CHECK(anchor.durable.backend_id==1);
}
int main(void)
{
    initial_selection(); legacy_attachment(); switching(); recovering(); configuration_and_conflicts();
    printf("PASS: 5 selection groups; enrollment_log_cuts=%zu; attach_log_cuts=%zu; switch_log_cuts=%zu; recovery_log_cuts=%zu; anchor_cuts=%zu; immediate_recoveries=%zu; lost_bits=0\n",
           enrollment_cuts,attach_cuts,switch_cuts,recovery_cuts,anchor_cuts,cycles);
    return 0;
}
