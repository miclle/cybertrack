#include "cybertrack/inputs.h"

#include <stdio.h>
#include <stdlib.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(EXIT_FAILURE); } } while (0)
static ct_input_filter filter;
static ct_local_inputs output;

static void observe(bool stop, bool fault, bool enable, uint64_t now)
{
    CHECK(ct_inputs_observe(&filter, (ct_local_inputs){stop, fault, enable}, now));
}

static void read_inputs(void) { CHECK(ct_inputs_read(&filter, &output)); }
static void init(ct_local_inputs initial, uint64_t now)
{
    CHECK(ct_inputs_init(&filter, 3, 5, initial, now));
}

static void startup_and_enable_bounce(void)
{
    init((ct_local_inputs){.enable_button = true}, 0);
    observe(false, false, true, 100);
    read_inputs(); CHECK(!output.enable_button);
    observe(false, false, false, 101);
    observe(false, false, true, 104); /* A brief release cannot arm. */
    observe(false, false, true, 110);
    read_inputs(); CHECK(!output.enable_button);
    observe(false, false, false, 111);
    observe(false, false, false, 116);
    observe(false, false, true, 117);
    observe(false, false, false, 120); /* Contact bounce resets press timer. */
    observe(false, false, true, 121);
    observe(false, false, true, 125);
    read_inputs(); CHECK(!output.enable_button);
    observe(false, false, true, 126);
    read_inputs(); CHECK(output.enable_button);
    observe(false, false, false, 127);
    observe(false, false, true, 129);
    read_inputs(); CHECK(output.enable_button); /* No extra rising edge. */
    observe(false, false, false, 130);
    observe(false, false, false, 135);
    read_inputs(); CHECK(!output.enable_button);
}

static void immediate_assert_and_release_bounce(void)
{
    init((ct_local_inputs){0}, 0);
    observe(true, true, true, 1);
    read_inputs(); CHECK(output.stop && output.fault && !output.enable_button);
    read_inputs(); CHECK(output.stop && output.fault);
    observe(false, false, true, 2);
    observe(false, false, true, 4);
    read_inputs(); CHECK(output.stop && output.fault);
    observe(true, false, true, 4);
    observe(false, false, true, 5);
    read_inputs(); CHECK(output.stop && !output.fault);
    observe(false, false, true, 7);
    read_inputs(); CHECK(output.stop);
    observe(false, false, true, 8);
    read_inputs(); CHECK(!output.stop && !output.enable_button);
}

static void pulses_survive_until_read(void)
{
    init((ct_local_inputs){0}, 0);
    observe(true, false, false, 1);
    observe(false, true, false, 2);
    observe(false, false, false, 3);
    observe(false, false, false, 100);
    read_inputs(); CHECK(output.stop && output.fault && !output.enable_button);
    read_inputs(); CHECK(!output.stop && !output.fault);
    observe(false, false, false, 105);
    observe(false, false, true, 106);
    observe(false, false, true, 111);
    read_inputs(); CHECK(output.enable_button);
}

static void safety_requires_new_stable_release(void)
{
    init((ct_local_inputs){0}, 0);
    observe(false, false, false, 5);
    observe(false, false, true, 6);
    observe(false, false, true, 11);
    read_inputs(); CHECK(output.enable_button);
    observe(false, true, true, 12);
    read_inputs(); CHECK(output.fault && !output.enable_button);
    observe(false, false, true, 13);
    observe(false, false, true, 16);
    observe(false, false, true, 100);
    read_inputs(); CHECK(!output.fault && !output.enable_button);
    observe(false, false, false, 101);
    observe(false, false, false, 106);
    observe(false, false, true, 107);
    observe(false, false, true, 112);
    read_inputs(); CHECK(output.enable_button);
}

static void clock_and_configuration(void)
{
    CHECK(!ct_inputs_init(NULL, 3, 5, (ct_local_inputs){0}, 0));
    CHECK(!ct_inputs_init(&filter, 0, 5, (ct_local_inputs){0}, 0));
    CHECK(!ct_inputs_read(&filter, &output));
    CHECK(!ct_inputs_init(&filter, 3, 0, (ct_local_inputs){0}, 0));
    init((ct_local_inputs){0}, 100);
    CHECK(!ct_inputs_observe(&filter, (ct_local_inputs){0}, 99));
    CHECK(!ct_inputs_read(&filter, &output));
    CHECK(!ct_inputs_observe(&filter, (ct_local_inputs){0}, 101));
    init((ct_local_inputs){0}, UINT64_MAX - 10);
    observe(false, false, false, UINT64_MAX - 5);
    observe(false, false, true, UINT64_MAX - 5);
    observe(false, false, true, UINT64_MAX);
    read_inputs(); CHECK(output.enable_button); /* No deadline addition overflow. */
    CHECK(!ct_inputs_read(&filter, NULL));
    CHECK(!ct_inputs_read(NULL, &output));
}

int main(void)
{
    startup_and_enable_bounce();
    immediate_assert_and_release_bounce();
    pulses_survive_until_read();
    safety_requires_new_stable_release();
    clock_and_configuration();
    puts("PASS: 5 input conditioning scenario groups (synthetic observations)");
    return EXIT_SUCCESS;
}
