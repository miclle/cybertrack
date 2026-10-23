#include "cybertrack/link.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(EXIT_FAILURE); } } while (0)
#define WRAP(x) "{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\"," x "}}"
static const char initialize[] = WRAP("\"id\":\"初始化\",\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"link-test\",\"version\":\"1\"}}");
static const char move[] = WRAP("\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.move\",\"arguments\":{\"direction\":\"forward\",\"speed_level\":2,\"duration_ms\":100}}");
static const char stop[] = WRAP("\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.stop\"}");
static const char ping[] = WRAP("\"id\":3,\"method\":\"ping\"");
static const char notification[] = WRAP("\"method\":\"notifications/initialized\"");
static ct_runtime runtime;
static ct_protocol protocol;
static ct_link link;
static ct_link_tx sent;
static struct {
    uint64_t now;
    ct_local_inputs inputs;
    ct_output applied;
    unsigned writes, offs;
    uint32_t write_delay;
    bool fail_off;
} board;
static const ct_link_limits budgets = {30, 30, 15, 12, 5};
static size_t split_cases;

static bool force_off(void *ctx)
{
    CHECK(ctx == &board); ++board.offs;
    if (board.fail_off) return false;
    board.applied = (ct_output){0}; return true;
}
static bool self_test(void *ctx) { CHECK(ctx == &board); return true; }
static bool clock_ms(void *ctx, uint64_t *now) { CHECK(ctx == &board); *now = board.now; return true; }
static bool inputs(void *ctx, ct_local_inputs *out) { CHECK(ctx == &board); *out = board.inputs; return true; }
static bool outputs(void *ctx, const ct_output *out)
{
    CHECK(ctx == &board); board.applied = *out; ++board.writes; board.now += board.write_delay; return true;
}
static bool kick(void *ctx) { CHECK(ctx == &board); return true; }
static bool service(void) { return ct_link_service(&link, board.now); }
static void off(void)
{
    CHECK(board.applied.left_level == 0 && board.applied.right_level == 0);
    CHECK(!board.applied.water && !board.applied.bubbles);
    CHECK(runtime.control.output.left_level == 0 && runtime.off_acknowledged);
}
static void reset_at(uint64_t now)
{
    memset(&board, 0, sizeof(board)); board.now = now;
    ct_board_io io = {&board, force_off, self_test, clock_ms, inputs, outputs, kick};
    CHECK(ct_runtime_init(&runtime, &protocol, io, (ct_limits){1000, 200, 300, 3}, 40, 20));
    CHECK(ct_link_init(&link, &runtime, budgets));
}
static void reset(void) { reset_at(0); }
static bool chunk(ct_ws_opcode op, bool fin, size_t offset, size_t total, const char *data, size_t len, bool fresh)
{
    return ct_link_receive(&link, link.attempt, (ct_ws_chunk){op, fin, offset, total, len, data}, fresh, board.now);
}
static bool complete(const char *frame, bool fresh)
{
    return chunk(CT_WS_TEXT, true, 0, strlen(frame), frame, strlen(frame), fresh);
}
static void ack(void)
{
    CHECK(ct_link_take_tx(&link, &sent, board.now));
    CHECK(!ct_link_take_tx(&link, &sent, board.now));
    CHECK(ct_link_sent(&link, sent.attempt, sent.id, true, sent.length, board.now));
}
static void exchange(const char *frame)
{
    CHECK(complete(frame, true)); CHECK(service()); ack();
}
static void connect_ready(void)
{
    uint64_t attempt = ct_link_begin(&link, board.now); CHECK(attempt != 0);
    CHECK(ct_link_connected(&link, attempt, board.now));
    CHECK(ct_link_ready(&link, attempt, board.now));
    CHECK(protocol.session == 0); CHECK(service());
    CHECK(link.state == CT_LINK_ONLINE && protocol.session != 0);
}
static void online(void) { reset(); connect_ready(); }
static void armed(void)
{
    online(); exchange(initialize);
    board.inputs.enable_button = true; CHECK(service());
    board.inputs.enable_button = false; CHECK(service());
    CHECK(runtime.control.state == CT_READY);
}
static void advance_to(uint64_t now)
{
    while (board.now < now) {
        uint64_t delta = now - board.now;
        board.now += delta > 10 ? 10 : delta;
        CHECK(service());
    }
}

static void configuration_and_handshake_gate(void)
{
    reset();
    CHECK(!ct_link_init(NULL, &runtime, budgets));
    ct_link_limits invalid = budgets; invalid.send_ms = 0;
    CHECK(!ct_link_init(&link, &runtime, invalid));
    CHECK(!service() && ct_link_begin(&link, 0) == 0);
    CHECK(ct_link_init(&link, &runtime, budgets));
    CHECK(ct_link_begin(&link, 0) == 1);
    CHECK(!ct_link_ready(&link, 1, 0));
    CHECK(!complete(move, true)); off();
    CHECK(ct_link_connected(&link, 1, 0));
    CHECK(!complete(move, true)); CHECK(!protocol.initialized);
    CHECK(ct_link_ready(&link, 1, 0));
    CHECK(!ct_link_ready(&link, 1, 0));
    CHECK(!complete(move, true)); CHECK(service());
    CHECK(!ct_link_connected(&link, 1, 0));
    exchange(initialize); CHECK(strstr(sent.frame, "protocolVersion")); off();
}

static void every_split_and_utf8(void)
{
    size_t length = strlen(initialize);
    for (size_t split = 1; split < length; ++split) {
        online();
        CHECK(chunk(CT_WS_TEXT, true, 0, length, initialize, split, false));
        CHECK(service()); CHECK(protocol.cache_count == 0 && !link.tx_pending);
        CHECK(chunk(CT_WS_TEXT, true, split, length, initialize + split, length - split, true));
        CHECK(service()); ack();
        CHECK(protocol.initialized && strstr(sent.frame, "初始化"));
        ++split_cases;
        online();
        CHECK(chunk(CT_WS_TEXT, false, 0, split, initialize, split, false));
        CHECK(chunk(CT_WS_PING, true, 0, 1, "p", 1, false));
        CHECK(chunk(CT_WS_CONT, true, 0, length - split, initialize + split, length - split, true));
        CHECK(service()); ack(); CHECK(protocol.initialized); ++split_cases;
    }
    online();
    for (size_t i = 0; i < length; ++i)
        CHECK(chunk(CT_WS_TEXT, true, i, length, initialize + i, 1, false));
    CHECK(service()); ack(); CHECK(protocol.initialized);
    online();
    CHECK(chunk(CT_WS_TEXT,false,0,10,initialize,3,false));
    CHECK(chunk(CT_WS_TEXT,false,3,10,initialize+3,7,false));
    CHECK(chunk(CT_WS_PING,true,0,2,"p",1,false));
    CHECK(chunk(CT_WS_PING,true,1,2,"p",1,false));
    CHECK(chunk(CT_WS_CONT,true,0,length-10,initialize+10,4,false));
    CHECK(chunk(CT_WS_CONT,true,4,length-10,initialize+14,length-14,false));
    CHECK(service()); ack(); CHECK(protocol.initialized);
}

static void boundary_frames_and_notifications(void)
{
    char frame[CT_RPC_FRAME_MAX + 1];
    online();
    memcpy(frame, ping, strlen(ping));
    memset(frame + strlen(ping), ' ', CT_RPC_FRAME_MAX - strlen(ping));
    frame[CT_RPC_FRAME_MAX] = '\0';
    CHECK(complete(frame, false)); CHECK(service()); ack(); CHECK(strstr(sent.frame, "result"));
    CHECK(chunk(CT_WS_TEXT, true, 0, 0, NULL, 0, false));
    CHECK(service()); ack(); CHECK(strstr(sent.frame, "-32700"));
    CHECK(complete(notification, false)); CHECK(service());
    CHECK(!link.tx_pending); off();
    char nul[] = {'{',0,'}'};
    CHECK(chunk(CT_WS_TEXT, true, 0, sizeof(nul), nul, sizeof(nul), false));
    CHECK(service()); ack(); CHECK(strstr(sent.frame, "-32700"));
    CHECK(chunk(CT_WS_TEXT, false, 0, 0, NULL, 0, false));
    CHECK(chunk(CT_WS_CONT, true, 0, strlen(ping), ping, strlen(ping), false));
    CHECK(service()); ack();
}

static void invalid_chunks(void)
{
    const ct_ws_chunk invalid[] = {
        {CT_WS_CONT,true,0,1,1,"x"}, {CT_WS_TEXT,true,1,2,1,"x"},
        {CT_WS_TEXT,true,0,1,2,"xx"}, {CT_WS_TEXT,true,0,1,1,NULL},
        {CT_WS_TEXT,true,0,1,0,""}, {CT_WS_TEXT,true,SIZE_MAX,1,1,"x"},
        {CT_WS_PING,false,0,0,0,NULL}, {CT_WS_BINARY,true,0,0,0,NULL},
        {(ct_ws_opcode)15,true,0,0,0,NULL}, {CT_WS_TEXT,true,0,SIZE_MAX,0,NULL},
        {CT_WS_PONG,true,0,126,0,NULL}
    };
    for (size_t i = 0; i < sizeof(invalid)/sizeof(invalid[0]); ++i) {
        armed(); exchange(move);
        CHECK(!ct_link_receive(&link, link.attempt, invalid[i], true, board.now));
        CHECK(link.close_required); CHECK(service()); off(); CHECK(protocol.session == 0);
    }
    const ct_ws_chunk changed[] = {
        {CT_WS_TEXT,true,0,4,1,"x"}, {CT_WS_TEXT,true,3,4,1,"x"},
        {CT_WS_TEXT,true,2,5,1,"x"}, {CT_WS_TEXT,false,2,4,1,"x"},
        {CT_WS_CONT,true,2,4,1,"x"}, {CT_WS_PING,true,0,0,0,NULL}
    };
    for (size_t i = 0; i < sizeof(changed)/sizeof(changed[0]); ++i) {
        online(); CHECK(chunk(CT_WS_TEXT,true,0,4,"ab",2,false));
        CHECK(!ct_link_receive(&link, link.attempt, changed[i], false, board.now));
        CHECK(service()); off();
    }
    online(); CHECK(chunk(CT_WS_TEXT,false,0,1,"a",1,false));
    CHECK(!chunk(CT_WS_TEXT,true,0,1,"b",1,false)); CHECK(service()); off();
    char full[CT_RPC_FRAME_MAX]; memset(full, ' ', sizeof(full));
    online(); CHECK(chunk(CT_WS_TEXT,false,0,sizeof(full),full,sizeof(full),false));
    CHECK(!chunk(CT_WS_CONT,true,0,1,"x",1,false));
    CHECK(link.error == CT_LINK_OVERSIZE); CHECK(service()); off();
}

static void fragment_deadlines(void)
{
    armed(); exchange(move);
    CHECK(chunk(CT_WS_TEXT,false,0,1,"{",1,true));
    advance_to(14);
    CHECK(chunk(CT_WS_PING,true,0,0,NULL,0,false)); /* Must not refresh text deadline. */
    board.now = 15;
    CHECK(!chunk(CT_WS_CONT,true,0,1,"}",1,true));
    CHECK(link.error == CT_LINK_FRAGMENT_TIMEOUT); CHECK(service()); off();
    online(); CHECK(chunk(CT_WS_PONG,true,0,2,"p",1,false));
    advance_to(15); CHECK(link.error == CT_LINK_FRAGMENT_TIMEOUT); off();
    online(); CHECK(chunk(CT_WS_TEXT,true,0,3,"{",1,false));
    advance_to(15); CHECK(link.error == CT_LINK_FRAGMENT_TIMEOUT); off();
    online(); CHECK(chunk(CT_WS_TEXT,false,0,1,"{",1,false));
    board.now = 10; CHECK(chunk(CT_WS_CONT,false,0,1," ",1,false)); CHECK(service());
    advance_to(15); CHECK(link.error == CT_LINK_FRAGMENT_TIMEOUT); off();
}

static void connect_and_handshake_deadlines(void)
{
    reset(); CHECK(ct_link_begin(&link,0)); advance_to(29);
    board.now = 30; CHECK(!ct_link_connected(&link,1,30));
    CHECK(link.error == CT_LINK_CONNECT_TIMEOUT); CHECK(service()); off();
    reset(); CHECK(ct_link_begin(&link,0)); CHECK(ct_link_connected(&link,1,0));
    advance_to(29); CHECK(ct_link_ready(&link,1,29));
    board.now = 30; CHECK(service());
    CHECK(link.error == CT_LINK_HANDSHAKE_TIMEOUT && protocol.session == 0); off();
}

static void ingress_metadata_not_refreshed(void)
{
    armed();
    size_t half = strlen(move)/2;
    CHECK(chunk(CT_WS_TEXT,false,0,half,move,half,true));
    board.inputs.stop = true; CHECK(service()); board.inputs.stop = false; CHECK(service());
    board.inputs.enable_button = true; CHECK(service()); board.inputs.enable_button = false; CHECK(service());
    CHECK(chunk(CT_WS_CONT,true,0,strlen(move)-half,move+half,strlen(move)-half,true));
    CHECK(service()); ack(); CHECK(strstr(sent.frame,"stale_local_enable")); off();
    armed(); CHECK(chunk(CT_WS_TEXT,false,0,half,move,half,false));
    board.now = 5;
    CHECK(chunk(CT_WS_CONT,true,0,strlen(move)-half,move+half,strlen(move)-half,true));
    CHECK(link.inbox.items[link.inbox.head].delivery.received_at_ms == 0);
    CHECK(service()); ack(); CHECK(strstr(sent.frame,"freshness_unverified")); off();
}

static void reconnect_and_stale_events(void)
{
    armed(); exchange(move);
    uint64_t old_attempt = link.attempt, old_session = protocol.session;
    ct_link_tx old_tx = sent;
    CHECK(chunk(CT_WS_TEXT,false,0,1,"{",1,true));
    CHECK(complete(ping,true) == false); /* Interleaved text closes, discards half message. */
    CHECK(service()); off();
    board.now = 5; CHECK(service());
    CHECK(ct_link_begin(&link,5) == 0); /* Abort not acknowledged. */
    ct_link_closed(&link,old_attempt,5);
    connect_ready(); CHECK(link.attempt > old_attempt && protocol.session > old_session);
    CHECK(!ct_link_receive(&link,old_attempt,(ct_ws_chunk){CT_WS_TEXT,true,0,1,1,"x"},true,0));
    CHECK(!ct_link_connected(&link,old_attempt,0)); CHECK(!ct_link_ready(&link,old_attempt,0));
    CHECK(!ct_link_sent(&link,old_attempt,old_tx.id,false,0,0));
    ct_link_closed(&link,old_attempt,0);
    CHECK(link.state == CT_LINK_ONLINE && link.last_ms == 5);
    CHECK(!ct_link_connected(&link,link.attempt,0)); /* Duplicate callback cannot roll back clock. */
    CHECK(!ct_link_ready(&link,link.attempt,0));
    CHECK(link.state == CT_LINK_ONLINE && link.last_ms == 5);
    exchange(initialize); exchange(move); CHECK(strstr(sent.frame,"-32002")); off();
    CHECK(!chunk(CT_WS_CONT,true,0,1,"}",1,true)); CHECK(service()); off();
}

static void disconnect_discards_queue_and_response(void)
{
    armed(); CHECK(complete(move,true)); CHECK(service()); CHECK(ct_link_take_tx(&link,&sent,board.now));
    CHECK(complete(ping,true)); CHECK(link.inbox.count == 1);
    board.inputs.enable_button = true; CHECK(service()); /* Held across reconnect. */
    uint64_t old = link.attempt;
    ct_link_closed(&link,old,0);
    CHECK(!link.tx_pending && link.inbox.count == 0 && !link.message_open);
    CHECK(ct_link_begin(&link,0) == 0); CHECK(service()); off();
    CHECK(!ct_link_receive(&link,old,(ct_ws_chunk){CT_WS_TEXT,true,0,1,1,"x"},true,0));
    CHECK(ct_link_begin(&link,4) == 0); board.now = 5; connect_ready(); exchange(initialize);
    CHECK(runtime.control.state != CT_READY); off();
    CHECK(!ct_link_sent(&link,old,sent.id,true,sent.length,0));
}

static void send_failures_and_timeouts(void)
{
    for (unsigned mode = 0; mode < 4; ++mode) {
        armed(); CHECK(complete(move,true)); CHECK(service());
        CHECK(board.applied.left_level == 2);
        if (mode < 2) {
            CHECK(ct_link_take_tx(&link,&sent,board.now));
            CHECK(!ct_link_sent(&link,sent.attempt,sent.id,mode != 0,mode ? sent.length-1 : 0,0));
            CHECK(link.error == CT_LINK_SEND_ERROR); CHECK(service());
        } else {
            if (mode == 2) CHECK(ct_link_take_tx(&link,&sent,board.now));
            advance_to(12); CHECK(link.error == CT_LINK_SEND_TIMEOUT);
            CHECK(!ct_link_sent(&link,link.attempt,link.tx_generation,true,sent.length,12));
        }
        off(); CHECK(protocol.session == 0 && !link.tx_pending && protocol.cache_count == 0);
        uint64_t failed = link.attempt;
        ct_link_closed(&link, failed, board.now);
        advance_to(board.now + budgets.retry_ms);
        connect_ready(); exchange(initialize);
        board.inputs.enable_button = true; CHECK(service());
        board.inputs.enable_button = false; CHECK(service());
        CHECK(runtime.control.state == CT_READY);
        /* Even freshly tagged replay after a lost reply and manual re-enable
         * cannot execute the previously accepted command. */
        exchange(move); CHECK(strstr(sent.frame, "-32002")); off();
        CHECK(protocol.sequence == 0);
        exchange(WRAP("\"id\":4,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.water\",\"arguments\":{\"duration_ms\":10}}"));
        CHECK(strstr(sent.frame, "accepted") && board.applied.water);
    }
    armed(); CHECK(complete(move,true)); CHECK(service()); CHECK(ct_link_take_tx(&link,&sent,board.now));
    board.now = 12; CHECK(!ct_link_sent(&link,sent.attempt,sent.id,true,sent.length,12));
    CHECK(service()); off(); CHECK(link.error == CT_LINK_SEND_TIMEOUT);
    armed(); CHECK(complete(move,true)); CHECK(service());
    board.now = 12; CHECK(!ct_link_take_tx(&link,&sent,board.now));
    CHECK(link.error == CT_LINK_SEND_TIMEOUT); CHECK(service()); off();
    for (unsigned mode = 0; mode < 2; ++mode) {
        armed(); CHECK(complete(move,true)); CHECK(service());
        if (mode) CHECK(ct_link_take_tx(&link,&sent,board.now));
        CHECK(!ct_link_sent(&link,link.attempt,link.tx.id,true,link.tx.length + mode,0));
        CHECK(link.error == CT_LINK_SEND_ERROR); CHECK(service()); off();
    }
}

static void backpressure_and_local_stop(void)
{
    armed(); CHECK(complete(move,true)); CHECK(service()); CHECK(ct_link_take_tx(&link,&sent,board.now));
    for (unsigned i = 0; i < CT_INBOX_SLOTS; ++i) CHECK(complete(ping,true));
    board.inputs.stop = true; CHECK(service()); off();
    CHECK(link.inbox.count == CT_INBOX_SLOTS && link.tx_pending);
    CHECK(!complete(stop,true)); CHECK(link.error == CT_LINK_QUEUE_ERROR);
    CHECK(service()); CHECK(protocol.session == 0); off();
    online(); CHECK(complete(ping,false)); CHECK(service()); ack();
    ct_link_tx old = sent;
    CHECK(complete(initialize,false)); CHECK(service()); CHECK(ct_link_take_tx(&link,&sent,board.now));
    CHECK(!ct_link_sent(&link,link.attempt,old.id,false,0,UINT64_MAX));
    CHECK(link.state == CT_LINK_ONLINE && link.last_ms == 0);
    CHECK(ct_link_sent(&link,sent.attempt,sent.id,true,sent.length,0));
}

static void runtime_delay_and_shutdown_failure(void)
{
    armed(); CHECK(complete(move,true));
    CHECK(chunk(CT_WS_TEXT,false,0,1,"{",1,true));
    board.write_delay = 15;
    CHECK(service()); CHECK(link.error == CT_LINK_FRAGMENT_TIMEOUT);
    CHECK(!link.tx_pending && protocol.session == 0); off();
    armed(); CHECK(complete(move,true)); CHECK(service()); CHECK(ct_link_take_tx(&link,&sent,board.now));
    board.fail_off = true;
    CHECK(!ct_link_sent(&link,sent.attempt,sent.id,false,0,0));
    CHECK(!service()); CHECK(link.state == CT_LINK_HALTED);
    CHECK(runtime.faults & CT_RUNTIME_OFF_FAILED); CHECK(!runtime.off_acknowledged);
    CHECK(board.applied.left_level == 2 && !link.tx_pending);
    ct_link_closed(&link,link.attempt,0); CHECK(ct_link_begin(&link,10) == 0);
}

static void clock_and_counter_boundaries(void)
{
    armed(); exchange(move); board.now = 1; CHECK(service());
    CHECK(!ct_link_receive(&link,link.attempt,(ct_ws_chunk){CT_WS_PING,true,0,0,0,NULL},false,0));
    CHECK(!service()); CHECK(link.state == CT_LINK_HALTED); off();
    reset_at(UINT64_MAX - 5); CHECK(ct_link_begin(&link,board.now));
    board.now = UINT64_MAX; CHECK(service()); CHECK(link.state == CT_LINK_CONNECTING);
    CHECK(!ct_link_connected(&link,link.attempt,0)); CHECK(!service()); off();
    reset(); link.attempt = UINT64_MAX; CHECK(ct_link_begin(&link,0) == 0);
    CHECK(link.error == CT_LINK_EXHAUSTED); CHECK(!service()); off();
    armed(); link.tx_generation = UINT64_MAX;
    CHECK(complete(move,true)); CHECK(!service());
    CHECK(link.error == CT_LINK_EXHAUSTED && protocol.session == 0); off();
}

int main(void)
{
    configuration_and_handshake_gate();
    every_split_and_utf8();
    boundary_frames_and_notifications();
    invalid_chunks();
    fragment_deadlines();
    connect_and_handshake_deadlines();
    ingress_metadata_not_refreshed();
    reconnect_and_stale_events();
    disconnect_discards_queue_and_response();
    send_failures_and_timeouts();
    backpressure_and_local_stop();
    runtime_delay_and_shutdown_failure();
    clock_and_counter_boundaries();
    printf("PASS: 13 link scenario groups; %zu exhaustive split cases; link_bytes=%zu; tx_bytes=%zu (fake transport/board only)\n",split_cases,sizeof(link),sizeof(sent));
    return EXIT_SUCCESS;
}
