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
    send(&s, 50, "3");
    send(&s, 100, "a");
    assert(s.armed && !s.active && s.channels == BENCH_CHANNEL_BOTH);
    send(&s, 200, "f");
    assert(s.active && !s.armed && !s.reverse);
    return s;
}
int main(void)
{
    bench_policy s = {0};
    send(&s, 0, "a"); assert(!s.armed && !s.channels);
    send(&s, 1, "f"); assert(!s.active);
    send(&s, 2, "r"); assert(!s.active);
    send(&s, 3, "1"); assert(s.channels == BENCH_CHANNEL_A);
    send(&s, 4, "a"); assert(s.armed);
    send(&s, 5, "2"); assert(!s.armed && s.channels == BENCH_CHANNEL_B);
    send(&s, 6, "r"); assert(!s.active); /* selection consumes prior arm */
    send(&s, 100, "a");
    send(&s, 3100, "f"); assert(!s.active && !s.armed);
    s = running();
    assert(BENCH_PULSE_MS == 10000); /* user-requested observation window */
    bench_tick(&s, 10199, false); assert(s.active);
    bench_tick(&s, 10200, false); assert(!s.active && !s.armed);
    send(&s, 10201, "a"); assert(!s.armed);
    send(&s, 13199, "2"); assert(s.channels == BENCH_CHANNEL_BOTH);
    send(&s, 13200, "2"); send(&s, 13201, "a"); send(&s, 13202, "r");
    assert(s.active && s.reverse && s.channels == BENCH_CHANNEL_B);
    for (unsigned ch=1; ch<=3; ++ch) {
        for (unsigned direction=0; direction<2; ++direction) {
            s=(bench_policy){0};
            const unsigned char selection=(unsigned char)('0'+ch);
            bench_receive(&s, 1, false, &selection, 1);
            send(&s, 2, "a"); send(&s, 3, direction ? "y" : "x");
            if (ch==3) {
                assert(s.active && s.reverse==(direction!=0) && s.reverse_b==(direction==0));
            } else assert(!s.active && !s.armed);
        }
    }
    s = running(); send(&s, 201, "r"); assert(!s.active && !s.armed);
    s = running(); send(&s, 201, "1");
    assert(!s.active && !s.armed && s.channels == BENCH_CHANNEL_BOTH); /* live selection stops, not changes */
    s = running(); send(&s, 250, "s"); assert(!s.active && !s.armed);
    s = running(); bench_tick(&s, 250, true); assert(!s.active && !s.armed);
    bench_receive(&s, 1300, true, (const unsigned char *)"a", 1); assert(!s.armed);
    bench_tick(&s, 1301, false); assert(!s.active && !s.armed);
    s = (bench_policy){0}; send(&s, 1, "3af"); assert(!s.active && !s.armed && !s.channels);
    send(&s, 2, "1\na\nf\n"); assert(!s.active && !s.armed && !s.channels);
    send(&s, 3, "1\r\n"); send(&s, 4, "a\r\n"); assert(s.armed);
    send(&s, 5, "\r\n"); assert(s.armed && !s.active);
    send(&s, 6, "?"); assert(!s.armed && !s.active);
    s = running(); send(&s, 201, "af"); assert(!s.active && !s.armed);
    s = running(); bench_tick(&s, 199, false); assert(!s.active && !s.armed);
    send(&s, 202, "a"); assert(!s.armed);
    s = (bench_policy){0}; send(&s, 1, "1"); send(&s, UINT64_MAX - 10, "a"); assert(!s.armed);
    s = (bench_policy){0}; send(&s, 1, "1"); send(&s, UINT64_MAX - 10100, "a"); assert(s.armed);
    send(&s, UINT64_MAX - 9999, "f"); assert(!s.active && !s.armed);
    s = running(); bench_tick(&s, 20000, false); assert(!s.active && !s.armed);
    s = (bench_policy){0}; assert(!s.armed && !s.active && !s.channels);
    puts("PASS: explicit A/B/AB selection, arm consumption, 10 s cutoff and mixed directions, cooldown, no live switching, stop/hold/release, bursts, time faults, reset");
}
