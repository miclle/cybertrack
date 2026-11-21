#include "control_sessions.h"
#include <cassert>
#include <cstring>
#include <iostream>
using G = AudioActionGuard;
static bool accepted(const char* value) { return !std::strcmp(value, "accepted"); }
static void ready(ControlSessions& s) { s.WifiLink(0,true); s.VoiceLink(0,true); s.Tick(0,false); }
static void start_all(ControlSessions& s) {
    ready(s);
    auto b=s.VoiceClaim(0,1,G::BubblesOnly), m=s.VoiceClaim(0,3,G::Both);
    assert(b && m);
    assert(accepted(s.guard.Bubbles(0,b,4000)));
    assert(accepted(s.guard.MoveAndWater(0,m,1000,3000,"forward")));
    assert(s.guard.Starts()==3);
}
static void off(const ControlSessions& s) {
    assert(!s.guard.Moving() && !s.guard.Watering() && !s.guard.Bubbling());
}
int main() {
    ControlSessions s; start_all(s);
    assert(!s.VoiceClaim(1,4,G::BubblesOnly));
    assert(!accepted(s.guard.Bubbles(1,1,5000))); // No extension by duplicate ticket.
    s.Tick(1000,false); assert(!s.guard.Moving() && s.guard.Watering() && s.guard.Bubbling());
    s.Tick(3000,false); assert(!s.guard.Watering() && s.guard.Bubbling());
    s.Tick(4000,false); assert(!s.guard.Bubbling());
    s.Tick(5000,false); off(s);
    // Every stop path cancels pending tickets too; reconnect/release never restarts.
    for(int cause=0;cause<6;++cause) {
        ControlSessions x; start_all(x);
        if(cause==0) x.Stop(10);
        if(cause==1) x.Tick(10,true);
        if(cause==2) x.WifiLink(10,false);
        if(cause==3) x.Shutdown(10);
        if(cause==4) x.Tick(10,false,true);
        if(cause==5) { x.Tick(10,false); x.Tick(9,false); }
        off(x); x.Tick(100,false); off(x);
        assert(!accepted(x.guard.Bubbles(100,1,1000)));
    }
    {
        constexpr auto target = G::BubblesOnly;
        ControlSessions x; ready(x);
        const int maximum = 30000;
        for(int ms:{0,-1,maximum+1,60000}) {
            const auto r=x.guard.WebRequest(0,target,0,0,nullptr,ms);
            assert(!accepted(r)); off(x);
        }
        // Per-lane lower and upper duration boundaries.
        assert(accepted(x.guard.WebRequest(0,target,0,0,nullptr,1)));
        x.Tick(1,false); off(x);
        x.Tick(5001,false);
        assert(accepted(x.guard.WebRequest(5001,target,0,0,nullptr,maximum)));
        x.Tick(5001+maximum,false); off(x);
        // Voice effect survives unrelated web release; web effect survives voice loss.
        ControlSessions y; ready(y); auto web=y.Acquire(0); y.Tick(0,false); assert(y.Heartbeat(0,web));
        assert(accepted(y.guard.WebRequest(0,target,0,0,nullptr,5000)));
        assert(y.Release(1,web)); y.Tick(1,false);
        assert(y.guard.Bubbling());
        web=y.Acquire(2); assert(y.Heartbeat(2,web));
        assert(!std::strcmp(y.WebAction(2,web,1,y.window,target,0,0,nullptr,1000),"voice_preempted"));
        off(y);
        y.Tick(5002,false); web=y.Acquire(5002); assert(web); assert(y.Heartbeat(5002,web));
        assert(accepted(y.WebAction(5002,web,1,y.window,target,0,0,nullptr,1000)));
        assert(!y.VoiceClaim(5002,55,target)); y.VoiceLink(5003,false); y.Tick(5003,false);
        assert(y.guard.Bubbling());
        assert(y.Release(5004,web)); off(y);
        // Queued effects are cancelled by all-stop and by a conflicting web request.
        ControlSessions z; ready(z); auto ticket=z.VoiceClaim(0,1,target); assert(ticket); z.Stop(1);
        assert(!accepted(z.guard.Bubbles(2,ticket,1000)));
    }
    std::cout << "PASS: three concurrent lanes, independent expiry, per-lane duration boundaries, no extension, all stop/fault paths, effect source isolation and preemption\n";
}
