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
    send(&s, 200, "f");
    assert(s.active && !s.armed && !s.reverse);
    return s;
}
int main(void)
{
    bench_policy s = {0};
    send(&s, 0, "f"); assert(!s.active && !s.armed);
    send(&s, 1, "r"); assert(!s.active);
    send(&s, 100, "a");
    send(&s, 3100, "f"); assert(!s.active && !s.armed); /* expiry inclusive */
    s = running();
    bench_tick(&s, 400, false); assert(s.active); /* old 200 ms deadline no longer stops */
    bench_tick(&s, 1200, false); assert(s.active); /* old 1 s deadline no longer stops */
    bench_tick(&s, 10199, false); assert(s.active);
    bench_tick(&s, 10200, false); assert(!s.active && !s.armed);
    send(&s, 10201, "a"); assert(!s.armed); /* cooldown */
    send(&s, 11199, "a"); assert(!s.armed);
    send(&s, 11200, "a"); send(&s, 11201, "r"); assert(s.active && s.reverse);
    s = running(); send(&s, 201, "r"); assert(!s.active && !s.armed); /* no live reverse */
    s = running(); send(&s, 5200, "s"); assert(!s.active && !s.armed);
    s = running(); bench_tick(&s, 5200, true); assert(!s.active && !s.armed);
    bench_receive(&s, 6500, true, (const unsigned char *)"a", 1); assert(!s.armed);
    bench_tick(&s, 6501, false); assert(!s.active && !s.armed); /* release no resume */
    s = (bench_policy){0}; send(&s, 1, "af"); assert(!s.active && !s.armed);
    send(&s, 2, "a\nf\n"); assert(!s.active && !s.armed);
    send(&s, 3, "a\r\n"); assert(s.armed);
    send(&s, 4, "\r\n"); assert(s.armed && !s.active);
    send(&s, 5, "?"); assert(!s.armed && !s.active);
    s = running(); send(&s, 201, "af"); assert(!s.active && !s.armed);
    s = running(); bench_tick(&s, 199, false); assert(!s.active && !s.armed);
    send(&s, 202, "a"); assert(!s.armed); /* rollback stays locked */
    s = (bench_policy){0}; send(&s, UINT64_MAX - 10, "a"); assert(!s.armed);
    s = (bench_policy){0}; send(&s, UINT64_MAX - 11000, "a"); assert(s.armed);
    send(&s, UINT64_MAX - 9000, "f"); assert(!s.active && !s.armed); /* pulse overflow */
    s = (bench_policy){0}; send(&s, 1, "a"); send(&s, 2, "f");
    bench_tick(&s, 20000, false); assert(!s.active && !s.armed); /* delayed loop */
    s = (bench_policy){0}; assert(!s.armed && !s.active); /* reboot no recovery */
    puts("PASS: arm/expiry, pulse/deadline, cooldown, reverse, stop/hold/release, bursts, invalid input, time faults, reset");
}
