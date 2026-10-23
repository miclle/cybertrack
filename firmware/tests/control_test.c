#include "cybertrack/control.h"

#include <stdio.h>
#include <stdlib.h>

/* Unlike assert(), these checks remain active in Release builds. */
#define CHECK(expr) do { \
    if (!(expr)) { \
        fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #expr); \
        exit(EXIT_FAILURE); \
    } \
} while (0)

static const ct_limits synthetic_limits = {1000, 200, 300, 3};

static void off(const ct_controller *c)
{
    CHECK(c->output.left_level == 0);
    CHECK(c->output.right_level == 0);
    CHECK(!c->output.water && !c->output.bubbles);
    CHECK(c->ends_at_ms == 0);
}

static ct_controller ready(void)
{
    ct_controller c;
    ct_init(&c, synthetic_limits, 0);
    CHECK(ct_boot_complete(&c) == CT_OK);
    CHECK(ct_set_session(&c, 1, 0) == CT_OK);
    CHECK(ct_local_enable(&c, 0) == CT_OK);
    return c;
}

static ct_request request(uint64_t sequence)
{
    return (ct_request){
        .session = 1, .sequence = sequence, .expires_at_ms = 10000,
        .action = CT_MOVE, .direction = CT_FORWARD,
        .speed_level = 2, .duration_ms = 100
    };
}

static void boot_and_reset(void)
{
    ct_controller c;
    ct_request r = request(1);
    ct_init(&c, synthetic_limits, 0);
    off(&c);
    CHECK(c.state == CT_BOOT);
    CHECK(ct_set_session(&c, 1, 0) == CT_OK);
    CHECK(ct_local_enable(&c, 0) == CT_NOT_READY);
    CHECK(ct_submit(&c, &r, 0) == CT_NOT_READY);
    CHECK(ct_boot_complete(&c) == CT_OK);
    CHECK(c.state == CT_DISARMED);
    r.sequence++;
    CHECK(ct_submit(&c, &r, 0) == CT_NOT_READY);
    CHECK(ct_local_enable(&c, 0) == CT_OK);
    CHECK(ct_submit(&c, &r, 0) == CT_REPLAY);
    r.sequence++;
    CHECK(ct_submit(&c, &r, 0) == CT_OK);
    ct_init(&c, synthetic_limits, 0);
    CHECK(c.state == CT_BOOT && c.session == 0);
    off(&c);
    ct_set_stop(&c, true);
    ct_set_stop(&c, false);
    CHECK(ct_local_enable(&c, 0) == CT_NOT_READY);
    CHECK(ct_boot_complete(&c) == CT_OK);
    CHECK(c.state == CT_FAULT);
}

static void timeout_and_exclusion(void)
{
    ct_controller c = ready();
    ct_request r = request(1);
    CHECK(ct_submit(&c, &r, 10) == CT_OK);
    CHECK(c.output.left_level == 2 && c.output.right_level == 2);
    CHECK(ct_tick(&c, 109) == CT_OK && c.state == CT_ACTIVE);
    r.sequence++;
    r.action = CT_WATER;
    CHECK(ct_submit(&c, &r, 109) == CT_BUSY);
    CHECK(!c.output.water && c.ends_at_ms == 110);
    CHECK(ct_tick(&c, 110) == CT_OK && c.state == CT_READY);
    off(&c);
    CHECK(ct_submit(&c, &r, 110) == CT_REPLAY);
    r.sequence++;
    CHECK(ct_submit(&c, &r, 110) == CT_OK);
    CHECK(c.output.water && !c.output.bubbles && c.output.left_level == 0);
    CHECK(ct_tick(&c, 210) == CT_OK);
    off(&c);
    r.sequence++;
    r.action = CT_BUBBLES;
    CHECK(ct_submit(&c, &r, 210) == CT_OK);
    CHECK(c.output.bubbles && !c.output.water && c.output.right_level == 0);
    CHECK(ct_tick(&c, 1000) == CT_OK);
    off(&c);
}

static void stop_and_fault_recovery(void)
{
    ct_controller c = ready();
    ct_request r = request(1);
    CHECK(ct_submit(&c, &r, 0) == CT_OK);
    ct_set_stop(&c, true);
    CHECK(c.state == CT_FAULT && c.fault == CT_STOPPED);
    off(&c);
    CHECK(ct_local_enable(&c, 1) == CT_NOT_READY);
    ct_set_stop(&c, false);
    CHECK(c.state == CT_FAULT);
    r.sequence++;
    CHECK(ct_submit(&c, &r, 1) == CT_NOT_READY);
    CHECK(ct_local_enable(&c, 1) == CT_OK);
    r.sequence++;
    CHECK(ct_submit(&c, &r, 1) == CT_OK);
    ct_set_fault(&c, true);
    CHECK(c.fault == CT_EXTERNAL_FAULT);
    off(&c);
    CHECK(ct_local_enable(&c, 2) == CT_NOT_READY);
    ct_set_fault(&c, false);
    CHECK(c.state == CT_FAULT);
    CHECK(ct_local_enable(&c, 2) == CT_OK);
    ct_stop(&c);
    ct_stop(&c);
    CHECK(c.state == CT_FAULT);
    off(&c);
}

static void sessions_and_replay(void)
{
    ct_controller c = ready();
    ct_request r = request(1);
    CHECK(ct_submit(&c, &r, 0) == CT_OK);
    CHECK(ct_submit(&c, &r, 1) == CT_REPLAY);
    CHECK(c.ends_at_ms == 100);
    CHECK(ct_set_session(&c, 0, 2) == CT_OK);
    CHECK(c.state == CT_FAULT && c.fault == CT_SESSION_LOST);
    off(&c);
    CHECK(ct_local_enable(&c, 2) == CT_NOT_READY);
    CHECK(ct_set_session(&c, 2, 2) == CT_OK);
    CHECK(c.state == CT_FAULT);
    CHECK(ct_local_enable(&c, 2) == CT_OK);
    CHECK(ct_submit(&c, &r, 2) == CT_SESSION_MISMATCH);
    r.session = 2;
    CHECK(ct_submit(&c, &r, 2) == CT_OK);
    CHECK(ct_set_session(&c, 3, 3) == CT_OK);
    CHECK(c.state == CT_FAULT);
    off(&c);
    CHECK(ct_local_enable(&c, 3) == CT_OK);
    CHECK(ct_set_session(&c, 4, 3) == CT_OK);
    CHECK(c.state == CT_DISARMED);
    off(&c);
}

static void bad_requests(void)
{
    ct_controller c = ready();
    ct_request r = request(0);
    CHECK(ct_submit(&c, NULL, 0) == CT_INVALID);
    CHECK(ct_submit(&c, &r, 0) == CT_REPLAY);
    r.sequence = 1;
    r.expires_at_ms = 5;
    CHECK(ct_submit(&c, &r, 5) == CT_EXPIRED);
    r = request(2);
    r.duration_ms = 0;
    CHECK(ct_submit(&c, &r, 5) == CT_INVALID);
    r.sequence++;
    r.duration_ms = 1001;
    CHECK(ct_submit(&c, &r, 5) == CT_INVALID);
    r = request(4);
    r.speed_level = 0;
    CHECK(ct_submit(&c, &r, 5) == CT_INVALID);
    r.sequence++;
    r.speed_level = 4;
    CHECK(ct_submit(&c, &r, 5) == CT_INVALID);
    r = request(6);
    r.direction = (ct_direction)99;
    CHECK(ct_submit(&c, &r, 5) == CT_INVALID);
    r = request(7);
    r.action = (ct_action)99;
    CHECK(ct_submit(&c, &r, 5) == CT_INVALID);
    r = request(8);
    r.action = CT_WATER;
    r.duration_ms = 201;
    CHECK(ct_submit(&c, &r, 5) == CT_INVALID);
    r.sequence++;
    r.action = CT_BUBBLES;
    r.duration_ms = 301;
    CHECK(ct_submit(&c, &r, 5) == CT_INVALID);
    CHECK(c.state == CT_READY);
    off(&c);
}

static void no_profile(void)
{
    ct_controller c;
    ct_init(&c, (ct_limits){0}, 0);
    CHECK(ct_boot_complete(&c) == CT_OK);
    CHECK(ct_set_session(&c, 1, 0) == CT_OK);
    CHECK(ct_local_enable(&c, 0) == CT_OK);
    for (int action = CT_MOVE; action <= CT_BUBBLES; action++) {
        ct_request r = request((uint64_t)action);
        r.action = (ct_action)action;
        CHECK(ct_submit(&c, &r, 0) == CT_UNAVAILABLE);
        off(&c);
    }
}

static void clock_and_overflow(void)
{
    ct_controller c = ready();
    ct_request r = request(1);
    CHECK(ct_submit(&c, &r, 10) == CT_OK);
    CHECK(ct_tick(&c, 9) == CT_CLOCK_ERROR);
    CHECK(c.state == CT_FAULT && c.fault == CT_CLOCK_FAULT);
    off(&c);
    CHECK(ct_local_enable(&c, 9) == CT_CLOCK_ERROR);
    CHECK(ct_local_enable(&c, 10) == CT_OK);
    r.sequence++;
    r.expires_at_ms = UINT64_MAX;
    CHECK(ct_submit(&c, &r, UINT64_MAX - 50) == CT_INVALID);
    off(&c);
}

static void directions_and_boundaries(void)
{
    const int16_t left[] = {3, -3, -3, 3};
    const int16_t right[] = {3, -3, 3, -3};
    for (int direction = CT_FORWARD; direction <= CT_RIGHT; direction++) {
        ct_controller c = ready();
        ct_request r = request(1);
        r.direction = (ct_direction)direction;
        r.speed_level = 3;
        r.duration_ms = 1000;
        CHECK(ct_submit(&c, &r, 0) == CT_OK);
        CHECK(c.output.left_level == left[direction]);
        CHECK(c.output.right_level == right[direction]);
        CHECK(ct_tick(&c, 1000) == CT_OK);
        off(&c);
    }
}

int main(void)
{
    boot_and_reset();
    timeout_and_exclusion();
    stop_and_fault_recovery();
    sessions_and_replay();
    bad_requests();
    no_profile();
    clock_and_overflow();
    directions_and_boundaries();
    puts("PASS: 8 control scenario groups (host only; no hardware outputs)");
    return EXIT_SUCCESS;
}
