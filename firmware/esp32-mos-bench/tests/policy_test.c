#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "bench_policy.h"

static void send(bench_policy *s, uint64_t t, const char *input)
{
    bench_receive(s, t, false, (const unsigned char *)input, strlen(input));
}

static bench_policy running(void)
{
    bench_policy s = {0};
    send(&s, 100, "a");
    assert(s.armed && !s.active);
    send(&s, 200, "g");
    assert(s.active && !s.armed);
    return s;
}

int main(void)
{
    bench_policy s = {0};
    send(&s, 0, "g"); assert(!s.active && !s.armed);
    send(&s, 100, "a");
    send(&s, 3100, "g"); assert(!s.active && !s.armed);
    s = running();
    bench_tick(&s, 1200, false); assert(s.active); /* old 1-second limit */
    bench_tick(&s, 5199, false); assert(s.active);
    bench_tick(&s, 5200, false); assert(!s.active && !s.armed);
    send(&s, 5201, "a"); assert(!s.armed);
    send(&s, 6199, "a"); assert(!s.armed);
    send(&s, 6200, "a"); send(&s, 6201, "g"); assert(s.active);
    s = running(); send(&s, 201, "g"); assert(!s.active && !s.armed);
    s = running(); send(&s, 2700, "s"); assert(!s.active && !s.armed);
    s = running(); bench_tick(&s, 2700, true); assert(!s.active && !s.armed);
    bench_receive(&s, 3800, true, (const unsigned char *)"a", 1); assert(!s.armed);
    bench_tick(&s, 3801, false); assert(!s.active && !s.armed);
    s = (bench_policy){0}; send(&s, 1, "ag"); assert(!s.active && !s.armed);
    send(&s, 2, "a\ng\n"); assert(!s.active && !s.armed);
    send(&s, 3, "a\r\n"); assert(s.armed);
    send(&s, 4, "\r\n"); assert(s.armed && !s.active);
    send(&s, 5, "?"); assert(!s.armed && !s.active);
    /* Commands from the motor bench must never turn on this output. */
    send(&s, 6, "a"); send(&s, 7, "f"); assert(!s.armed && !s.active);
    send(&s, 8, "a"); send(&s, 9, "r"); assert(!s.armed && !s.active);
    s = running(); send(&s, 201, "ag"); assert(!s.active && !s.armed);
    s = running(); bench_tick(&s, 199, false); assert(!s.active && !s.armed);
    send(&s, 202, "a"); assert(!s.armed);
    s = (bench_policy){0}; send(&s, UINT64_MAX - 10, "a"); assert(!s.armed);
    s = (bench_policy){0}; send(&s, UINT64_MAX - 6000, "a"); assert(s.armed);
    send(&s, UINT64_MAX - 4500, "g"); assert(!s.active && !s.armed);
    s = running(); bench_tick(&s, 20000, false); assert(!s.active && !s.armed);
    s = (bench_policy){0}; assert(!s.armed && !s.active);
    puts("PASS: one-shot, deadlines, stop, cooldown, bursts, stale motor keys, clock faults, reset");
}
