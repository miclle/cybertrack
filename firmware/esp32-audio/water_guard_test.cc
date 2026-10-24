#include "water_guard.h"
#include <cassert>
#include <cstring>
#include <iostream>
static bool is(const char* a, const char* b) { return !std::strcmp(a,b); }
int main() {
    AudioWaterGuard g;
    g.Tick(0, true, false);
    int a = g.Claim(0, 1); assert(a);
    assert(is(g.Request(0, a, 5000), "accepted")); // No physical authorization.
    assert(!g.Claim(1, 1)); // Same RPC cannot replay.
    assert(!g.Claim(1, 2)); // Busy at receipt cannot queue a later activation.
    assert(is(g.Request(2, a, 5000), "cancelled_or_duplicate"));
    g.Tick(4999, true, false); assert(g.policy.active);
    g.Tick(5000, true, false); assert(!g.policy.active && g.policy.starts == 1);
    assert(!g.Claim(5999, 3));
    g.Tick(6000, true, false);
    assert(!g.Claim(6000, 2)); // Even a rejected busy RPC remains consumed.
    a = g.Claim(6000, 4); assert(a);
    g.Stop(6001); assert(is(g.Request(6002, a, 5000), "cancelled_or_duplicate"));
    a = g.Claim(6003, 5); assert(is(g.Request(6003, a, 5000), "accepted"));
    g.Tick(6100, true, true); assert(!g.policy.active);
    g.Tick(9000, true, true); assert(!g.Claim(9000, 6));
    g.Tick(9001, true, false); assert(!g.Claim(9001, 7));
    g.Tick(9031, true, false); assert(!g.policy.active); // Release never restarts.
    a = g.Claim(9031, 8); assert(a);
    g.Tick(9032, true, true);
    g.Tick(9063, true, false);
    assert(is(g.Request(9063, a, 5000), "cancelled_or_duplicate"));
    a = g.Claim(9064, 9); assert(a);
    g.Tick(9065, false, false); g.Tick(9066, true, false);
    assert(is(g.Request(9066, a, 5000), "cancelled_or_duplicate"));
    a = g.Claim(9066, 9); assert(a); // RPC namespace resets with audio session.
    assert(is(g.Request(9066, a, 5000), "accepted"));
    g.Tick(9067, false, false); assert(!g.policy.active);
    g.Tick(10068, true, false);
    a = g.Claim(10068, 1); assert(a);
    assert(is(g.Request(15068, a, 5000), "stale_request"));
    a = g.Claim(15069, 2); assert(a);
    assert(is(g.Request(15069, a, 5001), "duration_must_match_5000ms_intent"));
    assert(!g.policy.active);
    g.Tick(15070, true, false); g.Tick(14000, true, false);
    assert(g.policy.clock_fault && !g.Claim(15071, 3));
    AudioWaterGuard full; full.Tick(0, true, false);
    for (int i = 0; i < 128; ++i) { assert(full.Claim(i, i)); full.Stop(i); }
    assert(!full.Claim(128, 128)); // No replay-cache eviction.
    full.Tick(129, false, false); full.Tick(130, true, false);
    assert(full.Claim(130, 128));
    AudioWaterGuard reboot; reboot.Tick(0, true, true);
    assert(!reboot.Claim(0, 1));
    reboot.Tick(40, true, false);
    assert(!reboot.policy.active && !reboot.policy.armed);
    std::cout << "PASS: direct voice, deadline, busy/cooldown, BOOT/stop queue cancellation, reconnect, replay, expiry, clock fault\n";
}
