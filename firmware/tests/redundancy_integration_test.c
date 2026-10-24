#include "cybertrack/protocol.h"
#include "fake_log.h"
#include "fake_anchor.h"
#include "fake_store.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%d: %s; reply=%s\n", __LINE__, #x, reply); exit(1); } } while (0)
#define WRAP(x) "{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\"," x "}}"
static const char initialize[] = WRAP("\"id\":\"init\",\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"recovery\",\"version\":\"1\"}}");
static const char stop[] = WRAP("\"id\":\"stop\",\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.stop\"}");
static const char status[] = WRAP("\"id\":\"status\",\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.get_status\"}");
static ct_test_store disks[3], base_disk;
static ct_replay_store stores[3];
static ct_test_anchor anchor, base_anchor;
static ct_test_log journal, base_log;
static ct_replay_log log_store;
static ct_replay_log_redundancy workspace;
static ct_protocol protocol;
static ct_controller control;
static ct_rpc_delivery delayed;
static unsigned char history[CT_REPLAY_BYTES];
static char reply[CT_RPC_REPLY_CAP];
static size_t rejections, action_cuts, open_cuts, transition_cuts, anchor_cuts, primary_cuts, damage_cases, cycles;
static const size_t edges[]={0,32812,32816};
static void off(void)
{
    CHECK(!control.output.water && !control.output.bubbles && !control.output.left_level &&
          !control.output.right_level && !control.ends_at_ms);
}
static void handle(const char *frame, uint64_t intent)
{
    ct_action_proof proof = {0};
    if (!protocol.storage_fault) CHECK(ct_protocol_issue_window(&protocol, 0, &proof));
    proof.intent = intent;
    ct_rpc_delivery delivery = {protocol.session, 0, control.enable_generation, proof};
    CHECK(ct_protocol_handle(&protocol, frame, strlen(frame), delivery, 0, reply, sizeof(reply)) == CT_RPC_RESPONSE);
}
static void action(unsigned rpc, uint64_t intent, const char *expected)
{
    char frame[256];
    snprintf(frame, sizeof(frame), WRAP("\"id\":%u,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.water\",\"arguments\":{\"duration_ms\":1}}"), rpc);
    handle(frame, intent);
    if (expected) CHECK(strstr(reply, expected)); else CHECK(!strstr(reply, "accepted"));
    if (expected && !strcmp(expected, "accepted")) CHECK(control.output.water);
    else { off(); ++rejections; }
}
static void attach(ct_replay_store *s, bool ready)
{
    ct_init(&control, (ct_limits){10,10,10,1}, 0); ct_protocol_init(&protocol, &control, 50);
    CHECK(ct_protocol_attach_logged_store(&protocol, s) == ready);
    CHECK(ct_boot_complete(&control) == CT_OK && ct_protocol_open(&protocol, 0));
    handle(initialize, 0); CHECK(protocol.initialized); off();
}

static void blank(unsigned i)
{
    ct_test_store_blank(&disks[i]);
    CHECK(ct_replay_store_load(&stores[i],ct_test_store_io(&disks[i]))==CT_STORE_EMPTY);
}
static void reboot(void)
{
    ct_test_anchor_power_cut(&anchor); ct_test_log_power_cut(&journal);
    CHECK(ct_replay_log_init_redundant(&log_store,ct_test_log_io(&journal),&workspace));
    for(unsigned i=0;i<3;++i) {
        ct_test_store_power_cut(&disks[i]);
        (void)ct_replay_store_load(&stores[i],ct_test_store_io(&disks[i]));
    }
}
static bool boot(unsigned i)
{
    reboot();
    bool ready=ct_replay_store_bind(&stores[i],ct_test_anchor_io(&anchor),i+1) &&
               ct_replay_store_attach_log(&stores[i],&log_store);
    attach(&stores[i],ready); return ready;
}
static bool enroll(void)
{
    return ct_replay_store_enroll_logged(&stores[0],&log_store,ct_test_anchor_io(&anchor),1);
}
static void baseline(void)
{
    memset(&anchor,0,sizeof(anchor)); ct_test_log_blank_redundant(&journal);
    for(unsigned i=0;i<3;++i) blank(i);
    CHECK(ct_replay_log_init_redundant(&log_store,ct_test_log_io(&journal),&workspace));
    CHECK(ct_replay_store_provision(&stores[0])); CHECK(enroll()); attach(&stores[0],true);
    CHECK(ct_local_enable(&control,0)==CT_OK); action(1,10,"accepted"); ct_stop(&control);
    CHECK(ct_local_enable(&control,0)==CT_OK); action(2,20,"accepted"); ct_stop(&control);
    ct_action_proof proof={0}; CHECK(ct_protocol_issue_window(&protocol,0,&proof)); proof.intent=90;
    delayed=(ct_rpc_delivery){protocol.session,0,control.enable_generation,proof};
    memcpy(history,stores[0].filter,sizeof(history)); ct_protocol_close(&protocol,0); off();
    base_disk=disks[0]; base_log=journal; base_anchor=anchor;
}
static void prepare(void)
{
    disks[0]=base_disk; journal=base_log; anchor=base_anchor; blank(1); blank(2); reboot();
    CHECK(ct_replay_store_bind(&stores[0],ct_test_anchor_io(&anchor),1));
    CHECK(ct_replay_store_attach_log(&stores[0],&log_store));
    memcpy(history,stores[0].filter,sizeof(history));
}
static ct_replay_recovery_result recover(unsigned source,unsigned target)
{
    return ct_replay_store_recover_log(&stores[source],&log_store,ct_test_anchor_io(&anchor),
                                      source+1,&stores[target],target+1);
}
static void retired(void)
{
    action(100,10,"-32002"); action(101,20,"-32002"); action(1,500,"-32002"); action(2,501,"-32002");
    char frame[256];
    snprintf(frame,sizeof(frame),WRAP("\"id\":%zu,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.water\",\"arguments\":{\"duration_ms\":1}}"),900000+rejections);
    CHECK(ct_protocol_handle(&protocol,frame,strlen(frame),delayed,0,reply,sizeof(reply))==CT_RPC_STALE_SESSION);
    off(); ++rejections;
    ct_rpc_delivery relabelled=delayed;
    relabelled.session=protocol.session; relabelled.enable_generation=control.enable_generation;
    CHECK(ct_protocol_handle(&protocol,frame,strlen(frame),relabelled,0,reply,sizeof(reply))==CT_RPC_RESPONSE);
    CHECK(strstr(reply,"freshness_unverified")); off(); ++rejections;
}

static uint64_t le64(const unsigned char *p)
{
    uint64_t v=0; for(unsigned i=0;i<8;++i) v|=(uint64_t)p[i]<<(8*i); return v;
}
static unsigned pair(void)
{
    for(unsigned i=0;i<4;++i) if(le64(journal.durable[i]+8)==anchor.durable.epoch &&
        le64(journal.durable[i]+16)==anchor.durable.backend_id) return i&~1u;
    CHECK(false); return 0;
}
static void damage(unsigned which)
{
    reboot(); journal.durable[pair()+which][40]^=128; ct_test_log_power_cut(&journal);
}
static void prove(unsigned selected,unsigned target,bool pending)
{
    blank(selected); reboot(); uint64_t session=anchor.durable.session;
    CHECK(recover(selected,target)==CT_RECOVERY_OK);
    CHECK(!memcmp(history,stores[target].filter,sizeof(history))); off();
    if(journal.unreadable_mask) {
        /* Recovery into the healthy pair works, but future rotation must not
         * authorize actions until local maintenance restores the failed slot. */
        CHECK(boot(target)); CHECK(protocol.storage_fault);
        CHECK(ct_local_enable(&control,0)==CT_OK); action(703,20,"-32005");
        ct_protocol_close(&protocol,0); journal.unreadable_mask=0;
    }
    CHECK(boot(target) && protocol.session>session);
    CHECK(!control.enable_generation && !protocol.accepted_sequence); action(700,700,NULL);
    CHECK(ct_local_enable(&control,0)==CT_OK); retired();
    if(pending) { action(330,30,"-32002"); action(3,333,"-32002"); }
    ct_protocol_close(&protocol,0); CHECK(!boot(selected));
    CHECK(ct_local_enable(&control,0)==CT_OK); action(702,20,"-32005");
    size_t calls=anchor.calls+journal.calls+disks[0].calls+disks[1].calls+disks[2].calls;
    handle(stop,0); CHECK(strstr(reply,"logical_outputs_cleared")); handle(status,0);
    CHECK(strstr(reply,"fault") && calls==anchor.calls+journal.calls+disks[0].calls+disks[1].calls+disks[2].calls);
    ct_protocol_close(&protocol,0); off();
}
static void inject(unsigned op,unsigned durable,size_t bytes)
{
    journal.fail_at=journal.calls+op; journal.persist_partial=durable!=0; journal.cut_bytes=bytes;
}
static void damaged_and_conflicting(void)
{
    for(unsigned slot=0;slot<4;++slot) {
        prepare(); journal.durable[slot][40]^=128; prove(0,1,false); ++damage_cases;
    }
    for(unsigned which=0;which<2;++which) {
        prepare(); journal.unreadable_mask=1u<<(pair()+which); prove(0,1,false); ++damage_cases;
        prepare(); CHECK(ct_replay_store_switch(&stores[0],&stores[1],2)); damage(which); prove(1,2,false); ++damage_cases;
    }
    prepare(); unsigned p=pair(); journal.durable[p][40]^=128; journal.durable[p+1][40]^=128;
    blank(0); reboot(); CHECK(recover(0,1)==CT_RECOVERY_HISTORY_UNAVAILABLE);
    CHECK(!boot(0)); CHECK(ct_local_enable(&control,0)==CT_OK); action(900,10,"-32005");
    handle(stop,0); CHECK(strstr(reply,"logical_outputs_cleared")); ct_protocol_close(&protocol,0);
}
static void interrupted_actions_and_open(void)
{
    for(unsigned mode=0;mode<2;++mode) for(unsigned op=5;op<=32;++op) {
        if(op>=17 && op<=20) continue; /* Read tolerance is covered separately. */
        for(unsigned durable=0;durable<2;++durable) for(size_t b=0;b<sizeof(edges)/sizeof(edges[0]);++b)
            for(unsigned lost=0;lost<2;++lost) {
                prepare(); attach(&stores[0],true); CHECK(ct_local_enable(&control,0)==CT_OK);
                if(mode) ct_protocol_close(&protocol,0);
                inject(op,durable,edges[b]);
                if(mode) { CHECK(ct_protocol_open(&protocol,0)); CHECK(protocol.storage_fault); ++open_cuts; }
                else { action(3,30,"-32005"); ++action_cuts; }
                off(); ct_protocol_close(&protocol,0); damage(lost); prove(0,1,false);
            }
    }
    for(unsigned mode=0;mode<2;++mode) for(unsigned op=1;op<=6;++op) for(unsigned committed=0;committed<2;++committed) {
        prepare(); attach(&stores[0],true); CHECK(ct_local_enable(&control,0)==CT_OK);
        uint64_t before=anchor.durable.revision;
        if(mode) ct_protocol_close(&protocol,0);
        anchor.fail_at=anchor.calls+op; anchor.commit_on_failure=committed!=0;
        if(mode) { CHECK(ct_protocol_open(&protocol,0)); CHECK(protocol.storage_fault); }
        else action(3,30,"-32005");
        bool pending=!mode && anchor.durable.revision>before;
        if(pending) memcpy(history,protocol.replay_filter,sizeof(history));
        off(); ct_protocol_close(&protocol,0); damage(op%2); prove(0,1,pending); ++anchor_cuts;
    }
    for(unsigned op=1;op<=6;++op) for(unsigned durable=0;durable<2;++durable)
        for(size_t b=0;b<sizeof(edges)/sizeof(edges[0]);++b) {
            prepare(); attach(&stores[0],true); CHECK(ct_local_enable(&control,0)==CT_OK);
            disks[0].fail_at=disks[0].calls+op; disks[0].persist_partial=durable!=0;
            disks[0].cut_bytes=edges[b]; action(3,30,"-32005");
            memcpy(history,protocol.replay_filter,sizeof(history)); ct_protocol_close(&protocol,0);
            damage(op%2); prove(0,1,true); ++primary_cuts;
        }
}
static void interrupted_transitions(void)
{
    for(unsigned mode=0;mode<2;++mode) for(unsigned op=5;op<=16;++op)
        for(unsigned durable=0;durable<2;++durable) for(size_t b=0;b<sizeof(edges)/sizeof(edges[0]);++b) {
            prepare(); if(mode) { blank(0); reboot(); }
            inject(op+(mode?4:0),durable,edges[b]);
            if(mode) CHECK(recover(0,1)==CT_RECOVERY_LOG_UNAVAILABLE);
            else CHECK(!ct_replay_store_switch(&stores[0],&stores[1],2));
            CHECK(anchor.durable.backend_id==1); damage(op%2); prove(0,2,false); ++transition_cuts;
        }
}
static void repeated_corruption(void)
{
    baseline(); unsigned selected=0;
    for(unsigned i=0;i<100;++i) {
        CHECK(boot(selected)); CHECK(ct_local_enable(&control,0)==CT_OK);
        memcpy(history,stores[selected].filter,sizeof(history));
        inject(5+(i%12)+(i%2?16:0),i%2,edges[i%3]);
        action(4000+i,5000+i,"-32005"); ct_protocol_close(&protocol,0);
        damage(i%2); blank(selected); unsigned target=(selected+1)%3; blank(target); reboot();
        CHECK(recover(selected,target)==CT_RECOVERY_OK);
        CHECK(!memcmp(history,stores[target].filter,sizeof(history)));
        /* Lose one replica and primary again before the repaired target opens. */
        damage((i+1)%2); blank(target); blank(selected); reboot();
        CHECK(recover(target,selected)==CT_RECOVERY_OK);
        CHECK(!memcmp(history,stores[selected].filter,sizeof(history)));
        CHECK(boot(selected)); CHECK(ct_local_enable(&control,0)==CT_OK); retired();
        if(i) action(3000+i,1000+i-1,"-32002");
        action(2000+i,1000+i,"accepted"); ct_stop(&control);
        ct_action_proof proof={0}; CHECK(ct_protocol_issue_window(&protocol,0,&proof)); proof.intent=10000+i;
        delayed=(ct_rpc_delivery){protocol.session,0,control.enable_generation,proof};
        ct_protocol_close(&protocol,0); ++cycles;
    }
}
int main(void)
{
    baseline(); damaged_and_conflicting(); interrupted_actions_and_open(); interrupted_transitions(); repeated_corruption();
    printf("PASS: 4 redundancy integration groups; damage_cases=%zu; action_rotation_cuts=%zu; open_rotation_cuts=%zu; transition_cuts=%zu; anchor_cuts=%zu; primary_cuts=%zu; repeated_double_recoveries=%zu; rejection_checks=%zu; unexpected_replays=0; lost_bits=0\n",
        damage_cases,action_cuts,open_cuts,transition_cuts,anchor_cuts,primary_cuts,cycles,rejections);
    return 0;
}
