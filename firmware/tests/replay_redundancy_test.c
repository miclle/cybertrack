#include "cybertrack/replay_log.h"
#include "../src/replay_log_internal.h"
#include "fake_store.h"
#include "fake_log.h"
#include "fake_anchor.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"%d: %s\n",__LINE__,#x); exit(1); } } while (0)
static ct_test_store disks[3], base_disk;
static ct_test_log journal, base_log;
static ct_test_anchor anchor, base_anchor;
static ct_replay_store stores[3];
static ct_replay_log log_store;
static ct_replay_log_redundancy workspace;
static unsigned char history[CT_REPLAY_BYTES], candidate[CT_REPLAY_BYTES], readback[CT_REPLAY_BYTES];
static size_t corruptions, rotations, read_faults, repairs, enrollments, transitions, anchor_cuts, cycles;
static const size_t edges[]={0,1,4,8,16,24,32,40,32808,32812,32816};
static uint64_t le64(const unsigned char *p)
{
    uint64_t v=0; for(unsigned i=0;i<8;++i) v|=(uint64_t)p[i]<<(8*i); return v;
}
static void crc(unsigned char *p)
{
    uint32_t v=UINT32_MAX;
    for(size_t i=0;i<32808;++i) { v^=p[i]; for(unsigned b=0;b<8;++b) v=(v>>1)^((v&1u)?UINT32_C(0xedb88320):0); }
    v=~v; for(unsigned b=0;b<4;++b) p[32808+b]=(unsigned char)(v>>(8*b));
}
static unsigned pair(void)
{
    for(unsigned i=0;i<4;++i) if(le64(journal.durable[i]+8)==anchor.durable.epoch &&
        le64(journal.durable[i]+16)==anchor.durable.backend_id) return i&~1u;
    CHECK(false); return 0;
}
static void blank(unsigned i)
{
    ct_test_store_blank(&disks[i]); CHECK(ct_replay_store_load(&stores[i],ct_test_store_io(&disks[i]))==CT_STORE_EMPTY);
}
static void reboot(void)
{
    ct_test_log_power_cut(&journal); ct_test_anchor_power_cut(&anchor);
    CHECK(ct_replay_log_init_redundant(&log_store,ct_test_log_io(&journal),&workspace));
    for(unsigned i=0;i<3;++i) { ct_test_store_power_cut(&disks[i]); (void)ct_replay_store_load(&stores[i],ct_test_store_io(&disks[i])); }
}
static void start(void)
{
    memset(&anchor,0,sizeof(anchor)); memset(history,0,sizeof(history));
    for(size_t i=0;i<sizeof(history);i+=31) history[i]=(unsigned char)(i|1);
    for(unsigned i=0;i<3;++i) blank(i);
    ct_test_log_blank_redundant(&journal); reboot();
    CHECK(ct_replay_store_provision(&stores[0]));
    CHECK(ct_replay_store_save(&stores[0],history,1));
}
static void enroll(void) { CHECK(ct_replay_store_enroll_logged(&stores[0],&log_store,ct_test_anchor_io(&anchor),1)); }
static void baseline(void)
{
    start(); enroll(); history[2]=4; CHECK(ct_replay_store_save(&stores[0],history,2));
    base_disk=disks[0]; base_log=journal; base_anchor=anchor;
    memcpy(candidate,history,sizeof(history)); candidate[1]=2;
}
static void prepare(void)
{
    disks[0]=base_disk; journal=base_log; anchor=base_anchor; blank(1); blank(2); reboot();
    CHECK(ct_replay_store_bind(&stores[0],ct_test_anchor_io(&anchor),1));
    CHECK(ct_replay_store_attach_log(&stores[0],&log_store));
}
static void inject(unsigned op,unsigned durable,size_t bytes)
{
    journal.fail_at=journal.calls+op; journal.persist_partial=durable!=0; journal.cut_bytes=bytes;
}
static ct_replay_recovery_result recover(unsigned src,unsigned dst)
{
    return ct_replay_store_recover_log(&stores[src],&log_store,ct_test_anchor_io(&anchor),src+1,&stores[dst],dst+1);
}
static void complete(unsigned src,unsigned dst,const unsigned char *expected)
{
    CHECK(recover(src,dst)==CT_RECOVERY_OK);
    CHECK(!memcmp(stores[dst].filter,expected,CT_REPLAY_BYTES));
    unsigned p=pair(); CHECK(!memcmp(journal.durable[p],journal.durable[p+1],CT_REPLAY_LOG_SLOT_BYTES));
    CHECK(stores[dst].log==&log_store);
}
static void lose_one_and_recover(unsigned which,const unsigned char *expected)
{
    reboot(); unsigned slot=pair()+which;
    journal.durable[slot][40]^=128; blank(0); reboot(); complete(0,1,expected);
}
static void single_slot_damage(void)
{
    const size_t bytes[]={0,4,8,16,24,32,40,12345,32808,32812,32815};
    for(unsigned slot=0;slot<4;++slot) for(size_t i=0;i<sizeof(bytes)/sizeof(bytes[0]);++i)
        for(unsigned bit=0;bit<8;++bit) {
            prepare(); journal.durable[slot][bytes[i]]^=(unsigned char)(1u<<bit);
            blank(0); reboot(); complete(0,1,history); ++corruptions;
        }
    for(unsigned slot=0;slot<4;++slot) {
        prepare(); journal.unreadable_mask=1u<<slot;
        CHECK(ct_replay_log_read(&log_store,anchor.durable,readback));
        CHECK(!memcmp(readback,history,sizeof(history))); ++read_faults;
        if(slot<2) { blank(0); reboot(); complete(0,1,history); }
        else {
            blank(0); reboot(); CHECK(recover(0,1)==CT_RECOVERY_LOG_UNAVAILABLE);
            CHECK(anchor.durable.backend_id==1); journal.unreadable_mask=0; reboot(); blank(1); complete(0,1,history);
        }
    }
}
static void interrupted_rotation(void)
{
    for(unsigned op=1;op<=32;++op) {
        bool read=op<=4 || (op>=17 && op<=20);
        unsigned boundaries=read?1:(unsigned)(sizeof(edges)/sizeof(edges[0]));
        for(unsigned durable=0;durable<(read?1u:2u);++durable) for(unsigned b=0;b<boundaries;++b)
            for(unsigned lost=0;lost<2;++lost) {
                prepare(); inject(op,durable,edges[b]);
                CHECK(ct_replay_store_save(&stores[0],candidate,2)==read);
                CHECK(read || stores[0].state==CT_STORE_FAULT);
                lose_one_and_recover(lost,read?candidate:history);
                if(read) ++read_faults; else ++rotations;
            }
    }
    for(unsigned op=1;op<=6;++op) for(unsigned committed=0;committed<2;++committed) {
        prepare(); anchor.fail_at=anchor.calls+op; anchor.commit_on_failure=committed!=0;
        CHECK(!ct_replay_store_save(&stores[0],candidate,2));
        bool selected=op>=5 || (op==4 && committed);
        lose_one_and_recover(op%2,selected?candidate:history); ++anchor_cuts;
    }
}
static void interrupted_repair(void)
{
    for(unsigned lost=0;lost<2;++lost) for(unsigned op=5;op<=10;++op)
        for(unsigned durable=0;durable<2;++durable) for(size_t b=0;b<sizeof(edges)/sizeof(edges[0]);++b) {
            prepare(); journal.durable[lost][40]^=128; reboot();
            CHECK(ct_replay_store_bind(&stores[0],ct_test_anchor_io(&anchor),1));
            inject(op,durable,edges[b]); CHECK(!ct_replay_store_attach_log(&stores[0],&log_store));
            CHECK(stores[0].state==CT_STORE_FAULT); blank(0); reboot(); complete(0,1,history); ++repairs;
        }
}
static void interrupted_selection(void)
{
    /* First registration never selects an incomplete pair. Explicit local
     * retries keep the original primary, including ambiguous durable writes. */
    for(unsigned op=5;op<=16;++op) for(unsigned durable=0;durable<2;++durable)
        for(size_t b=0;b<sizeof(edges)/sizeof(edges[0]);++b) {
            start(); inject(op,durable,edges[b]);
            CHECK(!ct_replay_store_enroll_logged(&stores[0],&log_store,ct_test_anchor_io(&anchor),1));
            CHECK(!anchor.durable.epoch); reboot(); enroll();
            lose_one_and_recover(op%2,history); ++enrollments;
        }
    for(unsigned op=1;op<=4;++op) for(unsigned committed=0;committed<2;++committed) {
        start(); anchor.fail_at=anchor.calls+op; anchor.commit_on_failure=committed!=0;
        CHECK(!ct_replay_store_enroll_logged(&stores[0],&log_store,ct_test_anchor_io(&anchor),1));
        reboot(); if(!anchor.durable.epoch) enroll();
        lose_one_and_recover(op%2,history); ++anchor_cuts;
    }
    baseline();
    for(unsigned mode=0;mode<2;++mode) for(unsigned op=5;op<=16;++op)
        for(unsigned durable=0;durable<2;++durable) for(size_t b=0;b<sizeof(edges)/sizeof(edges[0]);++b) {
            prepare(); if(mode) { blank(0); reboot(); }
            inject(op+(mode?4:0),durable,edges[b]);
            if(mode) CHECK(recover(0,1)==CT_RECOVERY_LOG_UNAVAILABLE);
            else CHECK(!ct_replay_store_switch(&stores[0],&stores[1],2));
            CHECK(anchor.durable.backend_id==1); reboot();
            journal.durable[pair()+op%2][40]^=128; blank(0); reboot(); complete(0,2,history); ++transitions;
        }
    for(unsigned mode=0;mode<2;++mode) for(unsigned op=1;op<=(mode?4u:3u);++op)
        for(unsigned committed=0;committed<2;++committed) {
            prepare(); if(mode) { blank(0); reboot(); }
            anchor.fail_at=anchor.calls+op; anchor.commit_on_failure=committed!=0;
            if(mode) CHECK(recover(0,1)!=CT_RECOVERY_OK);
            else CHECK(!ct_replay_store_switch(&stores[0],&stores[1],2));
            unsigned selected=(unsigned)anchor.durable.backend_id-1; reboot();
            journal.durable[pair()+op%2][40]^=128; blank(selected); reboot(); complete(selected,2,history); ++anchor_cuts;
        }
}
static void conflicts_and_limits(void)
{
    prepare(); unsigned p=pair(); journal.durable[p][40]^=128; crc(journal.durable[p]);
    blank(0); reboot(); CHECK(recover(0,1)==CT_RECOVERY_HISTORY_UNAVAILABLE);
    prepare(); p=pair(); journal.durable[p][40]^=128; journal.durable[p+1][40]^=128;
    blank(0); reboot(); CHECK(recover(0,1)==CT_RECOVERY_HISTORY_UNAVAILABLE); /* Older full pair is not current. */
    prepare(); p=pair(); journal.unreadable_mask=3u<<p;
    blank(0); reboot(); CHECK(recover(0,1)==CT_RECOVERY_HISTORY_UNAVAILABLE);
    prepare(); p=pair(); memcpy(journal.durable[2-p],journal.durable[p],CT_REPLAY_LOG_SLOT_BYTES);
    blank(0); reboot(); CHECK(recover(0,1)==CT_RECOVERY_HISTORY_UNAVAILABLE); /* Same key across both pairs is invalid. */
    prepare(); CHECK(ct_replay_store_save(&stores[0],candidate,2)); journal=base_log;
    blank(0); reboot(); CHECK(recover(0,1)==CT_RECOVERY_HISTORY_UNAVAILABLE);
    CHECK(!ct_replay_log_init_redundant(&log_store,ct_test_log_io(&journal),NULL) && !log_store.ready);
}
static void repeated_damage(void)
{
    prepare(); unsigned selected=0;
    for(unsigned i=0;i<100;++i) {
        unsigned dest=1-selected; journal.durable[pair()+i%2][40]^=128;
        blank(selected); blank(dest); reboot(); complete(selected,dest,history);
        selected=dest; ++cycles;
    }
}
int main(void)
{
    baseline(); single_slot_damage(); interrupted_rotation(); interrupted_repair();
    interrupted_selection(); conflicts_and_limits(); repeated_damage();
    printf("PASS: 6 redundancy groups; corruptions=%zu; rotation_cuts_with_damage=%zu; tolerated_read_faults=%zu; repair_cuts=%zu; enrollment_cuts=%zu; transition_cuts_with_damage=%zu; anchor_cuts_with_damage=%zu; repeated_recoveries=%zu; log_bytes=%zu; workspace_bytes=%zu; lost_bits=0\n",
        corruptions,rotations,read_faults,repairs,enrollments,transitions,anchor_cuts,cycles,sizeof(log_store),sizeof(workspace));
    return 0;
}
