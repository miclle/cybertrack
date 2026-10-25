#include "action_guard.h"
#include <cassert>
#include <cstring>
#include <iostream>
static bool is(const char* a, const char* b) { return !std::strcmp(a, b); }
int main() {
    for (const char* direction : {"forward", "backward", "left", "right"}) {
        AudioActionGuard g; g.Tick(0, true, false);
        assert(!g.Moving() && !g.Watering());
        int t = g.Claim(0, 1), queued = g.Claim(0, 2);
        assert(is(g.Move(0, t, 3000, direction), "accepted"));
        assert(g.Moving() && !g.Watering());
        assert(g.left == ((!strcmp(direction,"backward") || !strcmp(direction,"left")) ? -60 : 60));
        assert(g.right == ((!strcmp(direction,"backward") || !strcmp(direction,"right")) ? -60 : 60));
        assert(!g.Claim(1, 3));
        assert(is(g.Water(1, queued, 1000), "cancelled_or_duplicate"));
        g.Tick(2999, true, false); assert(g.Moving());
        g.Tick(3000, true, false); assert(!g.Moving());
        assert(!g.Claim(5999, 4));
        g.Tick(6000, true, false);
        t = g.Claim(6000, 5); assert(t);
        assert(is(g.Water(6000, t, 30000), "accepted"));
        assert(g.Watering() && !g.Moving());
        assert(!g.Claim(6001, 6));
        g.Tick(36000, true, false); assert(!g.Watering());
        assert(!g.Claim(36999, 7));
        assert(g.Claim(37000, 8)); // Water retains one-second cooldown.
    }
    for (int duration : {-1, 0, 3001, INT_MAX, INT_MIN}) {
        AudioActionGuard g; g.Tick(0, true, false); int t = g.Claim(0, 1);
        assert(is(g.Move(0,t,duration,"forward"),"duration_out_of_range"));
        assert(!g.Moving() && !g.Watering());
        assert(is(g.Move(1,t,1000,"forward"),"cancelled_or_duplicate"));
    }
    for (const char* d : {"", "Forward", "spin", "forward;water"}) {
        AudioActionGuard g; g.Tick(0, true, false);
        assert(!is(g.Move(0,g.Claim(0,1),1000,d),"accepted"));
        assert(!g.Moving());
    }
    for (int stop = 0; stop < 3; ++stop) {
        AudioActionGuard g; g.Tick(0,true,false);
        assert(is(g.Move(0,g.Claim(0,1),3000,"forward"),"accepted"));
        if (stop == 0) g.Stop(100);
        else g.Tick(100,stop != 1,stop == 2);
        assert(!g.Moving() && !g.Watering());
        g.Tick(200,true,false); assert(!g.Moving() && !g.Claim(200,2));
        g.Tick(3100,true,false); assert(!g.Moving());
        int t = g.Claim(3100,3); assert(t);
        g.Stop(3101);
        assert(is(g.Move(3102,t,1000,"backward"),"cancelled_or_duplicate"));
    }
    AudioActionGuard g; g.Tick(0,true,false);
    int t = g.Claim(0,1);
    g.Tick(1,false,false); g.Tick(2,true,false);
    assert(is(g.Move(2,t,1000,"forward"),"cancelled_or_duplicate"));
    t = g.Claim(2,1); assert(t);
    assert(is(g.Move(5002,t,1000,"forward"),"stale_request"));
    g.Tick(6000,true,false); g.Tick(5999,true,false);
    assert(!g.Claim(6001,2) && !g.Moving());
    std::cout << "PASS: four directions, bounds, motor/water exclusion, burst cancellation, cooldown, stop/BOOT/disconnect, stale session, clock fault\n";
}
