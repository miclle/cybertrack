#include "cybertrack/protocol.h"
#include "cybertrack/runtime.h"
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
static ct_test_store disks[2];
static ct_replay_store stores[2];
static ct_test_anchor anchor;
static ct_test_log journal, saved_journal;
static ct_replay_log log_store;
static ct_protocol protocol;
static ct_controller control;
static char reply[CT_RPC_REPLY_CAP];
static size_t rejections, recovery_cuts, write_cuts, log_cuts, anchor_cuts, open_cuts, cycles, runtime_cases;
static size_t open_log_cuts, preparation_cycles, bridge_recovery_retries;
static unsigned char retained_history[CT_REPLAY_BYTES];
static uint64_t le64(const unsigned char *p)
{
    uint64_t v=0; for(unsigned i=0;i<8;++i) v|=(uint64_t)p[i]<<(8*i); return v;
}
static ct_replay_anchor_record recovery_from;
static bool retained_evidence(const ct_test_log *before)
{
    for (unsigned i = 0; i < 2; ++i) {
        const unsigned char *p = before->durable[i];
        if (le64(p+8) == recovery_from.epoch && le64(p+16) == recovery_from.backend_id &&
            le64(p+24) == recovery_from.revision && le64(p+32) == recovery_from.session)
            return !memcmp(p, journal.durable[i], CT_REPLAY_LOG_SLOT_BYTES);
    }
    return false;
}
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
static bool reload(unsigned i)
{
    ct_test_store_power_cut(&disks[i]); ct_test_anchor_power_cut(&anchor);
    ct_test_log_power_cut(&journal); CHECK(ct_replay_log_init(&log_store, ct_test_log_io(&journal)));
    (void)ct_replay_store_load(&stores[i], ct_test_store_io(&disks[i]));
    return ct_replay_store_bind(&stores[i], ct_test_anchor_io(&anchor), i + 1) &&
           ct_replay_store_attach_log(&stores[i], &log_store);
}
static bool boot(unsigned i)
{
    bool ready = reload(i); attach(&stores[i], ready); return ready;
}
static void enable(void) { CHECK(ct_local_enable(&control, 0) == CT_OK); }
static void blank(unsigned i)
{
    ct_test_store_blank(&disks[i]);
    CHECK(ct_replay_store_load(&stores[i], ct_test_store_io(&disks[i])) == CT_STORE_EMPTY);
}
static void prepare(void)
{
    memset(&anchor, 0, sizeof(anchor)); blank(0); blank(1); ct_test_log_blank(&journal);
    CHECK(ct_replay_store_provision(&stores[0]));
    CHECK(ct_replay_store_enroll(&stores[0], ct_test_anchor_io(&anchor), 1));
    CHECK(ct_replay_log_init(&log_store, ct_test_log_io(&journal)));
    CHECK(ct_replay_store_attach_log(&stores[0], &log_store));
    attach(&stores[0], true); enable(); action(1, 10, "accepted"); ct_stop(&control);
    enable(); action(2, 20, "accepted"); ct_stop(&control); enable();
}
static ct_replay_recovery_result recover(unsigned source)
{
    recovery_from = anchor.durable;
    return ct_replay_store_recover_log(&stores[source], &log_store, ct_test_anchor_io(&anchor),
                                      source + 1, &stores[1-source], 2-source);
}
static void retired(unsigned rpc)
{
    action(rpc, 10, "-32002"); action(rpc+1, 20, "-32002"); action(2, rpc+100, "-32002");
}
static void lose_primary(unsigned i)
{
    ct_protocol_close(&protocol, 0); off(); ct_test_store_blank(&disks[i]); CHECK(!reload(i));
}
static void missing_primary_and_gates(void)
{
    prepare(); lose_primary(0); uint64_t session = anchor.durable.session;
    saved_journal = journal; size_t reads = disks[0].calls;
    CHECK(recover(0) == CT_RECOVERY_OK); CHECK(reads == disks[0].calls);
    CHECK(retained_evidence(&saved_journal)); off();
    CHECK(boot(1) && protocol.session > session); action(90, 90, NULL);
    enable(); retired(3); action(6, 30, "accepted"); ct_stop(&control);
    CHECK(boot(1)); enable(); action(7, 30, "-32002");
    CHECK(!boot(0)); enable(); action(8, 20, "-32005");
    size_t calls = anchor.calls + journal.calls + disks[0].calls + disks[1].calls;
    handle(stop, 0); CHECK(strstr(reply, "logical_outputs_cleared")); handle(status, 0);
    CHECK(strstr(reply, "fault") && calls == anchor.calls+journal.calls+disks[0].calls+disks[1].calls);
    prepare(); ct_protocol_close(&protocol, 0); CHECK(reload(0)); stores[0].log = NULL;
    attach(&stores[0], false); enable(); action(4, 30, "-32005");
    CHECK(!ct_protocol_attach_logged_store(&protocol, &stores[0]));
}
static void finish_failure(bool pending_retired, bool primary_ready)
{
    CHECK(protocol.storage_fault); off(); ct_protocol_close(&protocol, 0);
    bool loaded=reload(0);
    if(loaded!=primary_ready) fprintf(stderr,"log=%zu write=%zu anchor=%zu expected=%d got=%d\n",log_cuts,write_cuts,anchor_cuts,primary_ready,loaded);
    CHECK(loaded == primary_ready);
    /* Recover even before data reservation, with the primary entirely absent.
     * The selected bridge retains old actions but not unselected new content. */
    ct_test_store_blank(&disks[0]); CHECK(!reload(0));
    CHECK(recover(0) == CT_RECOVERY_OK); CHECK(boot(1));
    enable(); retired(4);
    if (pending_retired) { action(7, 30, "-32002"); action(3, 300, "-32002"); }

}
static void interrupted_saves(void)
{
    const size_t log_edges[] = {0,1,4,8,16,24,32,40,32808,32812,32816};
    for (unsigned op=1; op<=16; ++op) for (unsigned durable=0; durable<2; ++durable)
        for (size_t b=0; b<sizeof(log_edges)/sizeof(log_edges[0]); ++b) {
            prepare(); journal.fail_at=journal.calls+op; journal.cut_bytes=log_edges[b];
            journal.persist_partial=durable != 0;
            action(3,30,"-32005"); finish_failure(false,true); ++log_cuts;
        }
    const size_t primary_edges[] = {0,1,4,24,32796,32800};
    for (unsigned op=1; op<=6; ++op) for (unsigned durable=0; durable<2; ++durable)
        for (size_t b=0; b<sizeof(primary_edges)/sizeof(primary_edges[0]); ++b) {
            prepare(); disks[0].fail_at=disks[0].calls+op; disks[0].cut_bytes=primary_edges[b];
            disks[0].persist_partial=durable != 0;
            action(3,30,"-32005");
            /* A full failed body write/sync can retain the old durable DONE
             * marker while replacing every CRC-covered byte. That is already
             * a complete snapshot; partial bodies still fail validation. */
            bool complete = op == 6 || (durable &&
                (((op == 2 && primary_edges[b] >= CT_REPLAY_SLOT_BYTES-4) ||
                  (op == 3 && primary_edges[b] == CT_REPLAY_SLOT_BYTES-4)) ||
                 (op == 5 && primary_edges[b] == CT_REPLAY_SLOT_BYTES) ||
                 (op == 4 && primary_edges[b] >= 4)));
            finish_failure(true,complete); ++write_cuts;
        }
    for (unsigned op=1; op<=6; ++op) for (unsigned commit=0; commit<2; ++commit) {
        prepare(); anchor.fail_at=anchor.calls+op; anchor.commit_on_failure=commit != 0;
        action(3,30,"-32005");
        bool reserved = op>=5 || (op==4 && commit);
        finish_failure(reserved,!reserved || op==6); ++anchor_cuts;
        prepare(); ct_protocol_close(&protocol,0);
        anchor.fail_at=anchor.calls+op; anchor.commit_on_failure=commit != 0;
        CHECK(ct_protocol_open(&protocol,0)); CHECK(protocol.storage_fault); off();
        ct_protocol_close(&protocol,0); CHECK(reload(0) == (!reserved || op==6));
        ct_test_store_blank(&disks[0]); CHECK(!reload(0));
        CHECK(recover(0)==CT_RECOVERY_OK); CHECK(boot(1));
        enable(); retired(4); ++open_cuts;
    }
}
static void interrupted_recovery(void)
{
    const size_t edges[] = {0,1,4,24,32796,32800};
    for (unsigned op=1; op<=14; ++op) for (unsigned durable=0; durable<2; ++durable)
        for (size_t b=0; b<sizeof(edges)/sizeof(edges[0]); ++b) {
            prepare(); lose_primary(0); saved_journal=journal;
            disks[1].fail_at=disks[1].calls+op; disks[1].cut_bytes=edges[b];
            disks[1].persist_partial=durable != 0;
            CHECK(recover(0)==CT_RECOVERY_DESTINATION_UNAVAILABLE);
            CHECK(retained_evidence(&saved_journal));
            CHECK(!boot(1)); enable(); action(4,20,"-32005"); ct_protocol_close(&protocol,0);
            CHECK(!reload(0)); blank(1); CHECK(recover(0)==CT_RECOVERY_OK);
            CHECK(boot(1)); enable(); retired(4); ++recovery_cuts;
        }
    for (unsigned op=1; op<=4; ++op) for (unsigned commit=0; commit<2; ++commit) {
        prepare(); lose_primary(0); anchor.fail_at=anchor.calls+op; anchor.commit_on_failure=commit != 0;
        CHECK(recover(0)!=CT_RECOVERY_OK);
        if (anchor.durable.backend_id==1) {
            CHECK(!boot(1)); CHECK(!reload(0)); blank(1); CHECK(recover(0)==CT_RECOVERY_OK);
        }
        CHECK(boot(1)); enable(); retired(4); ++recovery_cuts;
    }
}
static void repeated_recovery(void)
{
    prepare(); unsigned selected=0; uint64_t session=anchor.durable.session;
    for (unsigned i=0; i<100; ++i) {
        /* Fake blank replacements model externally supplied media, never a
         * firmware erase-on-error policy. Original RPC IDs and intents persist. */
        lose_primary(selected); blank(1-selected); CHECK(recover(selected)==CT_RECOVERY_OK);
        CHECK(!boot(selected)); enable(); action(4000+i,20,"-32005");
        selected=1-selected; CHECK(boot(selected)); CHECK(protocol.session>session); session=protocol.session;
        enable(); retired(10000+2*i); action(2000+i,1000+i,"accepted"); ct_stop(&control);
        CHECK(boot(selected)); enable(); action(3000+i,1000+i,"-32002"); ++cycles;
    }
}
static void interrupted_open_logs(void)
{
    const size_t edges[] = {0,1,4,8,16,24,32,40,32808,32812,32816};
    for (unsigned op = 1; op <= 16; ++op) for (unsigned durable = 0; durable < 2; ++durable)
        for (size_t b = 0; b < sizeof(edges)/sizeof(edges[0]); ++b) {
            prepare(); ct_protocol_close(&protocol, 0);
            uint64_t session = anchor.durable.session;
            memcpy(retained_history, stores[0].filter, sizeof(retained_history));
            journal.fail_at = journal.calls + op; journal.cut_bytes = edges[b];
            journal.persist_partial = durable != 0;
            CHECK(ct_protocol_open(&protocol, 0)); CHECK(protocol.storage_fault); off();
            CHECK(anchor.durable.session == session);
            lose_primary(0); CHECK(recover(0) == CT_RECOVERY_OK);
            CHECK(!memcmp(stores[1].filter, retained_history, sizeof(retained_history)));
            CHECK(boot(1)); CHECK(protocol.session > session); enable(); retired(4);
            ++open_log_cuts;
        }
}
static void repeated_preparation_recovery(void)
{
    prepare(); unsigned selected = 0;
    for (unsigned i = 0; i < 100; ++i) {
        memcpy(retained_history, stores[selected].filter, sizeof(retained_history));
        ct_replay_anchor_record before = anchor.durable;
        ct_action_proof proof = {0}; CHECK(ct_protocol_issue_window(&protocol, 0, &proof));
        proof.intent = 10000 + i;
        ct_rpc_delivery old = {protocol.session, 0, control.enable_generation, proof};
        char frame[256];
        snprintf(frame, sizeof(frame), WRAP("\"id\":%u,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.water\",\"arguments\":{\"duration_ms\":1}}"), 30000+i);
        journal.fail_at = journal.calls + 9 + i % 8; /* After bridge selection. */
        journal.cut_bytes = i % 3 == 0 ? 0 : CT_REPLAY_LOG_SLOT_BYTES;
        journal.persist_partial = (i % 2) != 0;
        CHECK(ct_protocol_handle(&protocol, frame, strlen(frame), old, 0, reply, sizeof(reply)) == CT_RPC_RESPONSE);
        CHECK(strstr(reply, "-32005")); off(); ++rejections;
        CHECK(anchor.durable.epoch == before.epoch + 1 && anchor.durable.revision == before.revision);
        CHECK(anchor.durable.session == before.session);
        lose_primary(selected); blank(1-selected); saved_journal = journal;
        if (i % 4 == 0) {
            disks[1-selected].fail_at = disks[1-selected].calls + 1 + i % 14;
            disks[1-selected].cut_bytes = CT_REPLAY_SLOT_BYTES;
            disks[1-selected].persist_partial = true;
            CHECK(recover(selected) == CT_RECOVERY_DESTINATION_UNAVAILABLE);
            CHECK(retained_evidence(&saved_journal));
            CHECK(!reload(selected)); blank(1-selected); ++bridge_recovery_retries;
        }
        CHECK(recover(selected) == CT_RECOVERY_OK);
        CHECK(!memcmp(stores[1-selected].filter, retained_history, sizeof(retained_history)));
        CHECK(retained_evidence(&saved_journal));
        CHECK(!boot(selected)); enable(); action(50000+i, 20, "-32005");
        selected = 1-selected; CHECK(boot(selected)); CHECK(protocol.session > before.session);
        CHECK(!control.enable_generation && !protocol.accepted_sequence); off();
        CHECK(ct_protocol_handle(&protocol, frame, strlen(frame), old, 0, reply, sizeof(reply)) == CT_RPC_STALE_SESSION);
        off(); ++rejections;
        enable(); retired(60000+2*i);
        if (i) action(70000+i, 20000+i-1, "-32002");
        /* Relabelling the transport session cannot renew the producer proof. */
        old.session = protocol.session; old.enable_generation = control.enable_generation;
        CHECK(ct_protocol_handle(&protocol, frame, strlen(frame), old, 0, reply, sizeof(reply)) == CT_RPC_RESPONSE);
        CHECK(strstr(reply, "freshness_unverified")); off(); ++rejections;
        action(80000+i, 10000+i, "-32002");
        action(40000+i, 20000+i, "accepted"); ct_stop(&control); enable();
        ++preparation_cycles;
    }
}

static ct_runtime runtime;
static ct_runtime_response response;
static ct_replay_io raw_log;
static struct { uint64_t now; ct_local_inputs inputs; ct_output output; unsigned writes, delay; bool stop, fail_output; } board;
static bool board_off(void *ctx) { (void)ctx; board.output=(ct_output){0}; return true; }
static bool board_ok(void *ctx) { (void)ctx; return true; }
static bool board_clock(void *ctx,uint64_t *now) { (void)ctx; *now=board.now; return true; }
static bool board_inputs(void *ctx,ct_local_inputs *out) { (void)ctx; *out=board.inputs; return true; }
static bool board_output(void *ctx,const ct_output *out)
{
    (void)ctx; CHECK(anchor.durable.revision==stores[0].revision && anchor.durable.backend_id==1);
    CHECK(anchor.durable.session==protocol.session);
    const unsigned char *p = NULL;
    for (unsigned i = 0; i < 2; ++i)
        if (le64(journal.durable[i]+8) == anchor.durable.epoch) p = journal.durable[i];
    CHECK(p);
    CHECK(le64(p+8)==anchor.durable.epoch && le64(p+16)==1);
    CHECK(le64(p+24)==anchor.durable.revision && le64(p+32)==protocol.session);
    CHECK(!memcmp(p+40,protocol.replay_filter,CT_REPLAY_BYTES));
    CHECK(!memcmp(stores[0].filter,protocol.replay_filter,CT_REPLAY_BYTES));
    CHECK(!memcmp(disks[0].durable,disks[0].pending,sizeof(disks[0].durable)));
    CHECK(!memcmp(journal.durable,journal.pending,sizeof(journal.durable)));
    ++board.writes; board.output=*out; return !board.fail_output;
}
static bool timed_sync(void *ctx)
{
    board.now+=board.delay; if(board.stop) board.inputs.stop=true;
    return raw_log.sync(ctx);
}
static bool step(ct_event_kind kind,const char *frame)
{
    ct_runtime_event event={0}; event.kind=kind; event.frame=frame;
    if(frame) event.length=strlen(frame);
    ct_action_proof origin={0};
    if(kind==CT_EVENT_MESSAGE && strcmp(frame,initialize)) {
        CHECK(ct_protocol_issue_window(&protocol,board.now,&origin)); origin.intent=90;
    }
    event.delivery=(ct_rpc_delivery){protocol.session,board.now,runtime.control.enable_generation,origin};
    return ct_runtime_step(&runtime,&event,&response);
}
static void runtime_ordering(void)
{
    for(unsigned mode=0;mode<6;++mode) {
        prepare(); ct_protocol_close(&protocol,0); memset(&board,0,sizeof(board));
        raw_log=ct_test_log_io(&journal); log_store.io.sync=timed_sync;
        ct_board_io io={NULL,board_off,board_ok,board_clock,board_inputs,board_output,board_ok};
        CHECK(ct_runtime_init(&runtime,&protocol,io,(ct_limits){100,100,100,1},mode==5?5:50,20));
        CHECK(ct_protocol_attach_logged_store(&protocol,&stores[0]));
        CHECK(step(CT_EVENT_CONNECT,NULL)); CHECK(step(CT_EVENT_MESSAGE,initialize));
        board.inputs.enable_button=true; CHECK(step(CT_EVENT_IDLE,NULL));
        board.inputs.enable_button=false; CHECK(step(CT_EVENT_IDLE,NULL));
        if(mode==0) journal.fail_at=journal.calls+3;
        if(mode==1) board.delay=11;
        if(mode==2) board.stop=true;
        if(mode==3) board.fail_output=true;
        if(mode==5) board.delay=3;
        const char frame[]=WRAP("\"id\":9,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.water\",\"arguments\":{\"duration_ms\":100}}");
        bool ok=step(CT_EVENT_MESSAGE,frame);
        if(ok!=(mode==0 || mode==2 || mode==4)) fprintf(stderr,"runtime mode=%u ok=%d writes=%u faults=%u response=%s\n",mode,ok,board.writes,(unsigned)runtime.faults,response.reply);
        CHECK(ok==(mode==0 || mode==2 || mode==4));
        CHECK(board.writes==(mode==3 || mode==4?1u:0u));
        if(mode==5) CHECK(runtime.faults & CT_RUNTIME_FRESHNESS);
        if(mode!=4) CHECK(!board.output.water);
        if(!ok) CHECK(!response.reply[0]);
        CHECK(boot(0)); enable(); retired(100);
        if(mode!=0) action(110,90,"-32002"); ++runtime_cases;
    }
}
int main(void)
{
    missing_primary_and_gates(); interrupted_saves(); interrupted_recovery(); repeated_recovery();
    interrupted_open_logs(); repeated_preparation_recovery(); runtime_ordering();
    printf("PASS: 7 log integration groups; log_cuts=%zu; primary_cuts=%zu; action_anchor_cuts=%zu; open_anchor_cuts=%zu; recovery_cuts=%zu; repeated_recoveries=%zu; runtime_cases=%zu; open_log_cuts=%zu; preparation_recoveries=%zu; bridge_recovery_retries=%zu; rejection_checks=%zu; unexpected_replays=0\n",
           log_cuts,write_cuts,anchor_cuts,open_cuts,recovery_cuts,cycles,runtime_cases,open_log_cuts,preparation_cycles,bridge_recovery_retries,rejections);
    return 0;
}
