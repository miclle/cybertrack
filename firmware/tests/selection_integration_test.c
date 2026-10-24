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
static ct_test_store disks[3];
static ct_replay_store stores[3];
static ct_test_anchor anchor;
static ct_test_log journal;
static ct_replay_log log_store;
static ct_protocol protocol;
static ct_controller control;
static ct_rpc_delivery delayed;
static unsigned char history[CT_REPLAY_BYTES];
static char reply[CT_RPC_REPLY_CAP];
static size_t rejections, enroll_cuts, switch_cuts, recovery_cuts, primary_cuts, anchor_cuts, cycles;
static const size_t edges[] = {0,1,4,8,16,24,32,40,32808,32812,32816};
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
    CHECK(ct_replay_log_init(&log_store,ct_test_log_io(&journal)));
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
static void prepare(bool enrolled)
{
    memset(&anchor,0,sizeof(anchor)); ct_test_log_blank(&journal);
    for(unsigned i=0;i<3;++i) blank(i);
    CHECK(ct_replay_log_init(&log_store,ct_test_log_io(&journal)));
    CHECK(ct_replay_store_provision(&stores[0]));
    if(enrolled) { CHECK(enroll()); attach(&stores[0],true); }
    else {
        /* Explicit locally attested legacy import. This does not establish
         * rollback resistance for the time BEFORE first enrollment. */
        ct_init(&control,(ct_limits){10,10,10,1},0); ct_protocol_init(&protocol,&control,50);
        CHECK(ct_protocol_attach_store(&protocol,&stores[0]));
        CHECK(ct_boot_complete(&control)==CT_OK && ct_protocol_open(&protocol,0));
        handle(initialize,0); CHECK(protocol.initialized);
    }
    CHECK(ct_local_enable(&control,0)==CT_OK); action(1,10,"accepted"); ct_stop(&control);
    CHECK(ct_local_enable(&control,0)==CT_OK); action(2,20,"accepted"); ct_stop(&control);
    ct_action_proof proof={0}; CHECK(ct_protocol_issue_window(&protocol,0,&proof)); proof.intent=30;
    delayed=(ct_rpc_delivery){protocol.session,0,control.enable_generation,proof};
    memcpy(history,stores[0].filter,sizeof(history)); ct_protocol_close(&protocol,0); off();
    if(!enrolled) reboot();
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
static void prove(unsigned selected,unsigned target)
{
    /* Remove the selected primary before ANY attach/open/save on that target. */
    blank(selected); reboot();
    uint64_t prior_session=anchor.durable.session;
    CHECK(recover(selected,target)==CT_RECOVERY_OK);
    CHECK(!memcmp(history,stores[target].filter,sizeof(history))); off();
    CHECK(boot(target) && protocol.session>prior_session);
    CHECK(!control.enable_generation && !protocol.accepted_sequence); action(700,700,NULL);
    CHECK(ct_local_enable(&control,0)==CT_OK); retired();
    ct_protocol_close(&protocol,0); CHECK(!boot(selected));
    CHECK(ct_local_enable(&control,0)==CT_OK); action(702,20,"-32005");
    size_t calls=anchor.calls+journal.calls+disks[0].calls+disks[1].calls+disks[2].calls;
    handle(stop,0); CHECK(strstr(reply,"logical_outputs_cleared")); handle(status,0);
    CHECK(strstr(reply,"fault") && calls==anchor.calls+journal.calls+disks[0].calls+disks[1].calls+disks[2].calls);
    ct_protocol_close(&protocol,0); off();
}
static void inject_log(unsigned op,unsigned durable,size_t bytes)
{
    journal.fail_at=journal.calls+op; journal.persist_partial=durable!=0; journal.cut_bytes=bytes;
}
static void first_enrollment(void)
{
    prepare(false); CHECK(enroll()); prove(0,1);
    for(unsigned op=1;op<=8;++op) for(unsigned durable=0;durable<2;++durable)
        for(size_t b=0;b<sizeof(edges)/sizeof(edges[0]);++b) {
            prepare(false); inject_log(op,durable,edges[b]); CHECK(!enroll());
            CHECK(!anchor.durable.epoch); attach(&stores[0],false);
            CHECK(ct_local_enable(&control,0)==CT_OK); action(800,20,"-32005");
            ct_protocol_close(&protocol,0); reboot();
            CHECK(enroll()); prove(0,1); ++enroll_cuts;
        }
    for(unsigned op=1;op<=4;++op) for(unsigned committed=0;committed<2;++committed) {
        prepare(false); anchor.fail_at=anchor.calls+op; anchor.commit_on_failure=committed!=0;
        CHECK(!enroll()); reboot(); if(!anchor.durable.epoch) CHECK(enroll());
        prove(0,1); ++anchor_cuts;
    }
}
static void switching(void)
{
    prepare(true); CHECK(ct_replay_store_switch(&stores[0],&stores[1],2)); prove(1,2);
    for(unsigned op=1;op<=8;++op) for(unsigned durable=0;durable<2;++durable)
        for(size_t b=0;b<sizeof(edges)/sizeof(edges[0]);++b) {
            prepare(true); inject_log(op,durable,edges[b]);
            CHECK(!ct_replay_store_switch(&stores[0],&stores[1],2));
            CHECK(anchor.durable.backend_id==1); prove(0,2); ++switch_cuts;
        }
    const size_t primary_edges[]={0,1,4,24,32796,32800};
    for(unsigned op=1;op<=14;++op) for(unsigned durable=0;durable<2;++durable)
        for(size_t b=0;b<sizeof(primary_edges)/sizeof(primary_edges[0]);++b) {
            prepare(true); disks[1].fail_at=disks[1].calls+op;
            disks[1].persist_partial=durable!=0; disks[1].cut_bytes=primary_edges[b];
            CHECK(!ct_replay_store_switch(&stores[0],&stores[1],2));
            CHECK(anchor.durable.backend_id==1); prove(0,2); ++primary_cuts;
        }
    for(unsigned op=1;op<=3;++op) for(unsigned committed=0;committed<2;++committed) {
        prepare(true); anchor.fail_at=anchor.calls+op; anchor.commit_on_failure=committed!=0;
        CHECK(!ct_replay_store_switch(&stores[0],&stores[1],2));
        prove((unsigned)anchor.durable.backend_id-1,2); ++anchor_cuts;
    }
}
static void recovery_selection(void)
{
    for(unsigned op=1;op<=10;++op) for(unsigned durable=0;durable<2;++durable)
        for(size_t b=0;b<sizeof(edges)/sizeof(edges[0]);++b) {
            prepare(true); blank(0); reboot(); inject_log(op,durable,edges[b]);
            CHECK(recover(0,1)!=CT_RECOVERY_OK);
            CHECK(anchor.durable.backend_id==1); prove(0,2); ++recovery_cuts;
        }
    for(unsigned op=1;op<=4;++op) for(unsigned committed=0;committed<2;++committed) {
        prepare(true); blank(0); reboot(); anchor.fail_at=anchor.calls+op;
        anchor.commit_on_failure=committed!=0; CHECK(recover(0,1)!=CT_RECOVERY_OK);
        prove((unsigned)anchor.durable.backend_id-1,2); ++anchor_cuts;
    }
}
static void repeated_selection(void)
{
    prepare(true); unsigned selected=0;
    for(unsigned i=0;i<100;++i) {
        unsigned target=(selected+1)%3, spare=(selected+2)%3;
        reboot(); CHECK(ct_replay_store_bind(&stores[selected],ct_test_anchor_io(&anchor),selected+1));
        CHECK(ct_replay_store_attach_log(&stores[selected],&log_store)); blank(target); blank(spare);
        CHECK(ct_replay_store_switch(&stores[selected],&stores[target],target+1));
        /* No intervening bridge or session between two consecutive selections. */
        blank(target); reboot(); CHECK(recover(target,spare)==CT_RECOVERY_OK);
        blank(spare); reboot(); blank(selected); CHECK(recover(spare,selected)==CT_RECOVERY_OK);
        CHECK(!memcmp(history,stores[selected].filter,sizeof(history)));
        CHECK(boot(selected)); CHECK(ct_local_enable(&control,0)==CT_OK); retired();
        if(i) action(3000+i,1000+i-1,"-32002");
        action(2000+i,1000+i,"accepted"); ct_stop(&control);
        memcpy(history,stores[selected].filter,sizeof(history));
        /* Produce a distinct delayed intent BEFORE the next transition. A
         * previously rejected intent is already retired, even with a new ID. */
        ct_action_proof proof={0}; CHECK(ct_protocol_issue_window(&protocol,0,&proof));
        proof.intent=10000+i;
        delayed=(ct_rpc_delivery){protocol.session,0,control.enable_generation,proof};
        ct_protocol_close(&protocol,0); ++cycles;
    }
}
int main(void)
{
    first_enrollment(); switching(); recovery_selection(); repeated_selection();
    printf("PASS: 4 selection integration groups; enrollment_log_cuts=%zu; switch_log_cuts=%zu; recovery_log_cuts=%zu; target_primary_cuts=%zu; anchor_cuts=%zu; repeated_selections=%zu; rejection_checks=%zu; unexpected_replays=0; lost_bits=0\n",
           enroll_cuts,switch_cuts,recovery_cuts,primary_cuts,anchor_cuts,cycles,rejections);
    return 0;
}
