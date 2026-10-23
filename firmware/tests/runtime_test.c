#include "cybertrack/runtime.h"
#include "cybertrack/inputs.h"
#include "cybertrack/inbox.h"
#include "fault_allocator.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(expr) do { \
    if (!(expr)) { \
        fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #expr); \
        exit(EXIT_FAILURE); \
    } \
} while (0)

typedef struct {
    uint64_t now;
    ct_local_inputs inputs;
    ct_output applied;
    bool fail_off, fail_self_test, fail_clock, fail_input, fail_write, fail_watchdog;
    bool stop_during_write;
    uint32_t write_delay, off_delay, watchdog_delay;
    unsigned off_calls, write_calls, watchdog_calls;
    char trace[1024];
    size_t trace_length;
} fake_board;

static ct_runtime runtime;
static ct_protocol protocol;
static ct_runtime_response response;
static fake_board board;
static ct_input_filter input_filter;
static bool use_filter;
static ct_inbox inbox;
static ct_inbox_item item;
static ct_test_heap parser_heap;
static const ct_limits limits = {1000, 200, 300, 3};

static void trace(char ch)
{
    CHECK(board.trace_length + 1 < sizeof(board.trace));
    board.trace[board.trace_length++] = ch;
    board.trace[board.trace_length] = '\0';
}

static bool fake_off(void *context)
{
    CHECK(context == &board);
    trace('O');
    ++board.off_calls;
    board.now += board.off_delay;
    if (board.fail_off) return false;
    board.applied = (ct_output){0};
    return true;
}

static bool fake_self_test(void *context)
{
    CHECK(context == &board);
    trace('S');
    return !board.fail_self_test;
}

static bool fake_clock(void *context, uint64_t *now)
{
    CHECK(context == &board);
    trace('T');
    *now = board.now;
    return !board.fail_clock;
}

static bool fake_inputs(void *context, ct_local_inputs *inputs)
{
    CHECK(context == &board);
    trace('I');
    if (use_filter) {
        return !board.fail_input && ct_inputs_observe(&input_filter, board.inputs, board.now) &&
               ct_inputs_read(&input_filter, inputs);
    }
    *inputs = board.inputs;
    return !board.fail_input;
}

static bool fake_write(void *context, const ct_output *output)
{
    CHECK(context == &board);
    trace('W');
    ++board.write_calls;
    board.applied = *output; /* Simulate partial hardware change even on error. */
    board.now += board.write_delay;
    if (board.stop_during_write) board.inputs.stop = true;
    return !board.fail_write;
}

static bool fake_watchdog(void *context)
{
    CHECK(context == &board);
    trace('K');
    ++board.watchdog_calls;
    board.now += board.watchdog_delay;
    return !board.fail_watchdog;
}

static ct_board_io io(void)
{
    return (ct_board_io){&board, fake_off, fake_self_test, fake_clock,
                         fake_inputs, fake_write, fake_watchdog};
}

static bool step(ct_event_kind kind)
{
    ct_runtime_event event = {.kind = kind};
    return ct_runtime_step(&runtime, &event, &response);
}

static bool message_with(const char *frame, ct_rpc_delivery delivery)
{
    ct_runtime_event event = {
        .kind = CT_EVENT_MESSAGE, .frame = frame, .length = strlen(frame), .delivery = delivery
    };
    return ct_runtime_step(&runtime, &event, &response);
}

static ct_rpc_delivery metadata(void)
{
    return (ct_rpc_delivery){protocol.session, board.now, runtime.control.enable_generation, true};
}

static bool message(const char *frame)
{
    return message_with(frame, metadata());
}

static const char initialize[] = "{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\",\"id\":\"init\",\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"test\",\"version\":\"1\"}}}}";
static const char move[] = "{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.move\",\"arguments\":{\"direction\":\"forward\",\"speed_level\":2,\"duration_ms\":5}}}}";
static const char stop[] = "{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.stop\"}}}";

static void off(void)
{
    CHECK(board.applied.left_level == 0 && board.applied.right_level == 0);
    CHECK(!board.applied.water && !board.applied.bubbles);
    CHECK(runtime.control.output.left_level == 0 && !runtime.control.output.water);
    CHECK(runtime.off_acknowledged);
}

static void reset(void)
{
    memset(&board, 0, sizeof(board));
    use_filter = false;
}

static void start_with_allocator(bool inject)
{
    reset();
    if (inject) ct_test_heap_reset(&parser_heap, 0, false);
    CHECK(ct_runtime_init(&runtime, &protocol, io(), limits, 50, 20));
    if (inject) CHECK(ct_protocol_set_allocator(&protocol, ct_test_allocator(&parser_heap)));
    CHECK(step(CT_EVENT_CONNECT));
    CHECK(message(initialize));
    board.inputs.enable_button = true;
    CHECK(step(CT_EVENT_IDLE));
    CHECK(runtime.control.state == CT_READY);
    board.inputs.enable_button = false;
    CHECK(step(CT_EVENT_IDLE));
}

static void start(void) { start_with_allocator(false); }

static void startup_and_missing_configuration(void)
{
    reset();
    board.applied.left_level = 2; /* Simulate preexisting peripheral state. */
    CHECK(ct_runtime_init(&runtime, &protocol, io(), (ct_limits){0}, 0, 20));
    CHECK(board.trace[0] == 'O' && board.trace[1] == 'S');
    CHECK(runtime.control.state == CT_DISARMED);
    CHECK(board.write_calls == 0);
    off();
    CHECK(step(CT_EVENT_CONNECT));
    CHECK(message(initialize));
    board.inputs.enable_button = true;
    CHECK(step(CT_EVENT_IDLE));
    CHECK(message(move));
    CHECK(strstr(response.reply, "freshness_unverified"));
    off();
    reset();
    ct_board_io incomplete = io();
    incomplete.write_outputs = NULL;
    CHECK(!ct_runtime_init(&runtime, &protocol, incomplete, limits, 50, 20));
    CHECK(runtime.faults & CT_RUNTIME_CONFIG);
    CHECK(board.watchdog_calls == 0 && board.trace[0] == 'O');
    reset();
    CHECK(!ct_runtime_init(&runtime, &protocol, io(), limits, 50, 0));
    CHECK(runtime.faults & CT_RUNTIME_CONFIG);
    off();
}

static void startup_failures(void)
{
    reset();
    board.fail_self_test = true;
    CHECK(!ct_runtime_init(&runtime, &protocol, io(), limits, 50, 20));
    CHECK(runtime.faults & CT_RUNTIME_SELF_TEST);
    CHECK(board.write_calls == 0 && board.watchdog_calls == 0);
    off();
    reset();
    board.fail_off = true;
    CHECK(!ct_runtime_init(&runtime, &protocol, io(), limits, 50, 20));
    CHECK(runtime.faults & CT_RUNTIME_OFF_FAILED);
    CHECK(!runtime.off_acknowledged && !strchr(board.trace, 'S'));
    reset();
    board.fail_clock = true;
    CHECK(!ct_runtime_init(&runtime, &protocol, io(), limits, 50, 20));
    CHECK(runtime.faults & CT_RUNTIME_CLOCK);
    CHECK(board.watchdog_calls == 0);
    off();
}

static void held_enable_and_stop_priority(void)
{
    reset();
    board.inputs.enable_button = true;
    CHECK(ct_runtime_init(&runtime, &protocol, io(), limits, 50, 20));
    CHECK(step(CT_EVENT_CONNECT));
    CHECK(step(CT_EVENT_IDLE));
    CHECK(runtime.control.state == CT_DISARMED);
    board.inputs.enable_button = false;
    CHECK(step(CT_EVENT_IDLE));
    board.inputs.enable_button = true;
    CHECK(step(CT_EVENT_IDLE));
    CHECK(runtime.control.state == CT_READY);
    board.inputs.stop = true;
    CHECK(step(CT_EVENT_IDLE));
    CHECK(runtime.control.state == CT_FAULT);
    board.inputs.stop = false;
    CHECK(step(CT_EVENT_IDLE));
    CHECK(runtime.control.state == CT_FAULT); /* Held enable is not a new event. */
    board.inputs.enable_button = false;
    CHECK(step(CT_EVENT_IDLE));
    board.inputs.enable_button = true;
    CHECK(step(CT_EVENT_IDLE));
    CHECK(runtime.control.state == CT_READY);
    off();

    start();
    board.inputs.stop = true;
    CHECK(message(move));
    CHECK(strstr(response.reply, "not_ready"));
    CHECK(board.write_calls == 0);
    off();
}

static void idle_deadline_and_remote_stop(void)
{
    start();
    CHECK(message(move));
    CHECK(board.applied.left_level == 2);
    CHECK(strstr(response.reply, "accepted"));
    board.now = 5;
    CHECK(ct_runtime_step(&runtime, NULL, NULL));
    off();
    CHECK(runtime.control.state == CT_READY);
    start();
    CHECK(message(move));
    CHECK(message(stop));
    CHECK(runtime.control.state == CT_FAULT);
    CHECK(strstr(response.reply, "logical_outputs_cleared"));
    off();
}

static void connection_and_enable_generations(void)
{
    start();
    ct_rpc_delivery old = metadata();
    CHECK(message(move));
    CHECK(step(CT_EVENT_DISCONNECT));
    off();
    CHECK(step(CT_EVENT_CONNECT));
    CHECK(message_with(move, old));
    CHECK(response.result == CT_RPC_STALE_SESSION);
    off();
    CHECK(message(initialize));
    old = metadata();
    board.inputs.enable_button = true;
    CHECK(step(CT_EVENT_IDLE));
    CHECK(message_with(move, old));
    CHECK(strstr(response.reply, "stale_local_enable"));
    off();
}

static void input_and_clock_failures(void)
{
    start();
    CHECK(message(move));
    unsigned kicks = board.watchdog_calls;
    board.fail_input = true;
    CHECK(!step(CT_EVENT_IDLE));
    CHECK(runtime.faults & CT_RUNTIME_INPUT);
    CHECK(board.watchdog_calls == kicks && protocol.session == 0);
    off();
    board.fail_input = false;
    board.inputs.enable_button = true;
    CHECK(!step(CT_EVENT_CONNECT));
    CHECK(board.watchdog_calls == kicks);
    off();
    start();
    board.now = 10;
    CHECK(step(CT_EVENT_IDLE));
    board.now = 9;
    CHECK(!step(CT_EVENT_IDLE));
    CHECK(runtime.faults & CT_RUNTIME_CLOCK);
    off();
    start();
    CHECK(message(move));
    board.fail_clock = true;
    CHECK(!step(CT_EVENT_IDLE));
    CHECK(runtime.faults & CT_RUNTIME_CLOCK);
    off();
}

static void missed_schedule_and_slow_write(void)
{
    start();
    CHECK(message(move));
    unsigned kicks = board.watchdog_calls;
    board.now = 21;
    CHECK(!step(CT_EVENT_IDLE));
    CHECK(runtime.faults & CT_RUNTIME_SCHEDULING);
    CHECK(board.watchdog_calls == kicks);
    off();
    start();
    board.write_delay = 21;
    kicks = board.watchdog_calls;
    CHECK(!message(move));
    CHECK(runtime.faults & CT_RUNTIME_SCHEDULING);
    CHECK(board.watchdog_calls == kicks && response.reply[0] == '\0');
    off();
}

static void output_and_off_failures(void)
{
    start();
    board.fail_write = true;
    unsigned kicks = board.watchdog_calls;
    CHECK(!message(move));
    CHECK(runtime.faults & CT_RUNTIME_OUTPUT);
    CHECK(response.reply[0] == '\0' && protocol.cache_count == 0 && protocol.session == 0);
    CHECK(board.watchdog_calls == kicks);
    off();
    start();
    CHECK(message(move));
    board.fail_off = true;
    CHECK(!message(stop));
    CHECK(runtime.faults & CT_RUNTIME_OFF_FAILED);
    CHECK(!runtime.off_acknowledged && response.reply[0] == '\0');
    /* Failure is reported, never falsely claimed to have physically shut down. */
    CHECK(board.applied.left_level == 2);
}

static void safety_or_deadline_during_write(void)
{
    start();
    board.stop_during_write = true;
    CHECK(message(move));
    CHECK(runtime.control.state == CT_FAULT);
    off();
    start();
    board.write_delay = 5;
    CHECK(message(move));
    CHECK(runtime.control.state == CT_READY);
    off();
    start();
    board.inputs.fault = true;
    CHECK(message(move));
    CHECK(runtime.control.state == CT_FAULT && board.write_calls == 0);
    off();
}

static void watchdog_failure_and_slow_callback(void)
{
    start();
    CHECK(message(move));
    board.fail_watchdog = true;
    CHECK(!step(CT_EVENT_IDLE));
    CHECK(runtime.faults & CT_RUNTIME_WATCHDOG);
    off();
    unsigned kicks = board.watchdog_calls;
    board.fail_watchdog = false;
    CHECK(!step(CT_EVENT_IDLE));
    CHECK(board.watchdog_calls == kicks);
    start();
    board.watchdog_delay = 5;
    CHECK(message(move));
    off(); /* Deadline crossing during watchdog callback cannot leave output on. */
    start();
    board.watchdog_delay = 21;
    CHECK(!message(move));
    CHECK(runtime.faults & CT_RUNTIME_SCHEDULING);
    off();
}

static void malformed_event_and_stop_before_parsing(void)
{
    start();
    CHECK(message(move));
    board.inputs.stop = true;
    unsigned writes = board.write_calls;
    CHECK(message("{invalid"));
    CHECK(strstr(response.reply, "Parse error"));
    CHECK(board.write_calls == writes);
    off();
    start();
    CHECK(message(move));
    ct_runtime_event event = {.kind = CT_EVENT_MESSAGE, .frame = move, .length = strlen(move)};
    CHECK(!ct_runtime_step(&runtime, &event, NULL));
    CHECK(runtime.faults & CT_RUNTIME_CONFIG);
    off();
}

static bool drain(void)
{
    ct_event_kind kind = ct_inbox_take(&inbox, &item);
    ct_runtime_event event = {kind, item.frame, item.length, item.delivery};
    return ct_runtime_step(&runtime, &event, &response);
}

static void queued_overflow_and_disconnect(void)
{
    start();
    ct_inbox_init(&inbox);
    CHECK(ct_inbox_bind(&inbox, protocol.session));
    CHECK(message(move));
    for (unsigned i = 0; i < CT_INBOX_SLOTS; ++i)
        CHECK(ct_inbox_push(&inbox, move, strlen(move), metadata()) == CT_INBOX_OK);
    CHECK(ct_inbox_push(&inbox, stop, strlen(stop), metadata()) == CT_INBOX_OVERFLOW);
    CHECK(drain());
    CHECK(protocol.session == 0 && runtime.control.state == CT_FAULT);
    CHECK(inbox.count == 0 && response.result == CT_RPC_NO_RESPONSE);
    off();
    uint64_t old_session = inbox.last_session;
    CHECK(step(CT_EVENT_CONNECT));
    CHECK(ct_inbox_bind(&inbox, protocol.session));
    CHECK(message(initialize));
    CHECK(runtime.control.state != CT_READY);
    ct_inbox_disconnect(&inbox, old_session);
    CHECK(drain()); CHECK(protocol.session == inbox.session);
    CHECK(ct_inbox_push(&inbox, move, strlen(move), metadata()) == CT_INBOX_OK);
    ct_inbox_disconnect(&inbox, protocol.session);
    CHECK(drain()); CHECK(protocol.session == 0);
    off();
}

static void queued_age_and_enable_are_not_refreshed(void)
{
    start();
    ct_inbox_init(&inbox);
    CHECK(ct_inbox_bind(&inbox, protocol.session));
    CHECK(ct_inbox_push(&inbox, move, strlen(move), metadata()) == CT_INBOX_OK);
    for (unsigned i = 1; i <= 3; ++i) {
        board.now = i * 20;
        CHECK(step(CT_EVENT_IDLE));
    }
    CHECK(drain());
    CHECK(strstr(response.reply, "expired"));
    CHECK(board.write_calls == 0);
    off();
    start();
    ct_inbox_init(&inbox);
    CHECK(ct_inbox_bind(&inbox, protocol.session));
    CHECK(ct_inbox_push(&inbox, move, strlen(move), metadata()) == CT_INBOX_OK);
    board.inputs.stop = true;
    CHECK(step(CT_EVENT_IDLE));
    board.inputs.stop = false;
    CHECK(step(CT_EVENT_IDLE));
    board.inputs.enable_button = true;
    CHECK(step(CT_EVENT_IDLE));
    CHECK(drain());
    CHECK(strstr(response.reply, "stale_local_enable"));
    CHECK(board.write_calls == 0);
    off();
}

static void filtered_short_stop_and_held_enable(void)
{
    reset();
    CHECK(ct_inputs_init(&input_filter, 3, 2, board.inputs, board.now));
    use_filter = true;
    CHECK(ct_runtime_init(&runtime, &protocol, io(), limits, 50, 20));
    CHECK(step(CT_EVENT_CONNECT));
    CHECK(message(initialize));
    board.now = 2; CHECK(step(CT_EVENT_IDLE));
    board.now = 3; board.inputs.enable_button = true; CHECK(step(CT_EVENT_IDLE));
    board.now = 5; CHECK(step(CT_EVENT_IDLE));
    CHECK(runtime.control.state == CT_READY);
    CHECK(message(move));
    CHECK(board.applied.left_level == 2);
    /* A captured pulse entirely between runtime cycles must survive. */
    CHECK(ct_inputs_observe(&input_filter, (ct_local_inputs){true, false, true}, 6));
    CHECK(ct_inputs_observe(&input_filter, (ct_local_inputs){false, false, true}, 7));
    board.now = 7; CHECK(step(CT_EVENT_IDLE));
    CHECK(runtime.control.state == CT_FAULT);
    off();
    board.now = 10; CHECK(step(CT_EVENT_IDLE));
    board.now = 12; CHECK(step(CT_EVENT_IDLE));
    CHECK(runtime.control.state == CT_FAULT); /* Still holding enable. */
    board.now = 13; board.inputs.enable_button = false; CHECK(step(CT_EVENT_IDLE));
    board.now = 15; CHECK(step(CT_EVENT_IDLE));
    board.now = 16; board.inputs.enable_button = true; CHECK(step(CT_EVENT_IDLE));
    board.now = 18; CHECK(step(CT_EVENT_IDLE));
    CHECK(runtime.control.state == CT_READY);
    off();
    /* Filter failure is propagated through the real runtime INPUT fault path. */
    CHECK(!ct_inputs_observe(&input_filter, board.inputs, 17));
    CHECK(!step(CT_EVENT_IDLE));
    CHECK(runtime.faults & CT_RUNTIME_INPUT);
    off();
}

static void parser_memory_failure_shuts_down_output(void)
{
    for (unsigned cached = 0; cached < 2; ++cached) {
        start_with_allocator(true);
        ct_test_heap_reset(&parser_heap, 0, false);
        CHECK(message(move));
        CHECK(board.applied.left_level == 2);
        size_t first_parse_calls = parser_heap.calls;
        unsigned writes = board.write_calls;
        ct_test_heap_reset(&parser_heap, cached ? first_parse_calls + 1 : 1, true);
        CHECK(message(move));
        CHECK(strstr(response.reply, cached ? "Cache allocation failed" : "JSON allocation failed"));
        CHECK(strstr(response.reply, "-32603") && runtime.control.state == CT_FAULT);
        CHECK(board.write_calls == writes && protocol.session != 0);
        ct_test_heap_empty(&parser_heap);
        off();
        ct_test_heap_reset(&parser_heap, 0, false);
        CHECK(message(move)); /* Cached accepted reply is not a new output. */
        CHECK(strstr(response.reply, "accepted") && board.write_calls == writes);
        CHECK(runtime.control.state == CT_FAULT);
        off();
    }
    start_with_allocator(true);
    CHECK(message(move));
    board.inputs.stop = true;
    ct_test_heap_reset(&parser_heap, 1, true);
    CHECK(message(stop)); /* Local stop remains effective under persistent OOM. */
    ct_test_heap_empty(&parser_heap);
    off();
}

static void parser_memory_and_shutdown_failure(void)
{
    start_with_allocator(true);
    CHECK(message(move));
    unsigned kicks = board.watchdog_calls;
    board.fail_off = true;
    ct_test_heap_reset(&parser_heap, 1, true);
    CHECK(!message(stop));
    CHECK(runtime.faults & CT_RUNTIME_OFF_FAILED);
    CHECK(response.reply[0] == '\0' && response.result == CT_RPC_NO_RESPONSE);
    CHECK(protocol.session == 0 && protocol.cache_count == 0);
    CHECK(board.watchdog_calls == kicks && board.applied.left_level == 2);
    CHECK(!runtime.off_acknowledged);
    ct_test_heap_empty(&parser_heap);
    board.fail_off = false;
    CHECK(!step(CT_EVENT_IDLE));
    CHECK(board.watchdog_calls == kicks);
    off();
}

int main(void)
{
    startup_and_missing_configuration();
    startup_failures();
    held_enable_and_stop_priority();
    idle_deadline_and_remote_stop();
    connection_and_enable_generations();
    input_and_clock_failures();
    missed_schedule_and_slow_write();
    output_and_off_failures();
    safety_or_deadline_during_write();
    watchdog_failure_and_slow_callback();
    malformed_event_and_stop_before_parsing();
    queued_overflow_and_disconnect();
    queued_age_and_enable_are_not_refreshed();
    filtered_short_stop_and_held_enable();
    parser_memory_failure_shuts_down_output();
    parser_memory_and_shutdown_failure();
    puts("PASS: 16 runtime scenario groups (fake board only)");
    return EXIT_SUCCESS;
}
