#include "control_sessions.h"
#include <cassert>
#include <cstring>
#include <iostream>
using G = AudioActionGuard;
static bool accepted(const char* value) { return !std::strcmp(value, "accepted"); }
static void ready(ControlSessions& s) { s.WifiLink(0,true); s.VoiceLink(0,true); s.Tick(0,false); }
static void start_all(ControlSessions& s) {
    ready(s);
    auto b=s.VoiceClaim(0,1,G::BubblesOnly), i=s.VoiceClaim(0,2,G::IgnitionOnly), m=s.VoiceClaim(0,3,G::Both);
    assert(b && i && m);
    assert(accepted(s.guard.Bubbles(0,b,4000)));
    assert(accepted(s.guard.Ignition(0,i,5000)));
    assert(accepted(s.guard.MoveAndWater(0,m,1000,3000,"forward")));
    assert(s.guard.Starts()==4);
}
static void off(const ControlSessions& s) {
    assert(!s.guard.Moving() && !s.guard.Watering() && !s.guard.Bubbling() && !s.guard.Igniting());
}
int main() {
    ControlSessions s; start_all(s);
    assert(!s.VoiceClaim(1,4,G::BubblesOnly) && !s.VoiceClaim(1,5,G::IgnitionOnly));
    assert(!accepted(s.guard.Ignition(1,2,5000))); // No extension by duplicate ticket.
    s.Tick(1000,false); assert(!s.guard.Moving() && s.guard.Watering() && s.guard.Bubbling() && s.guard.Igniting());
    s.Tick(3000,false); assert(!s.guard.Watering() && s.guard.Bubbling() && s.guard.Igniting());
    s.Tick(4000,false); assert(!s.guard.Bubbling() && s.guard.Igniting());
    s.Tick(5000,false); off(s);
    assert(s.guard.ignition.cooldown_until==8000);
    assert(!s.VoiceClaim(7999,6,G::IgnitionOnly));
    s.Tick(8000,false); assert(s.VoiceClaim(8000,7,G::IgnitionOnly));
    // The interval starts at OFF, including early stops, and applies to both entry points.
    for(int cause=0;cause<3;++cause) {
        ControlSessions x; ready(x);
        assert(accepted(x.guard.Ignition(0,x.VoiceClaim(0,1,G::IgnitionOnly),cause==0?10:5000)));
        if(cause==0) x.Tick(10,false);
        if(cause==1) x.Stop(10);
        if(cause==2) x.guard.StopIgnition(10);
        assert(x.guard.ignition.cooldown_until==3010);
        x.Stop(20); // Repeated stop cannot shorten or restart the interval.
        assert(x.guard.ignition.cooldown_until==3010);
        assert(!x.VoiceClaim(3009,2,G::IgnitionOnly));
        assert(!accepted(x.guard.WebRequest(3009,G::IgnitionOnly,0,0,nullptr,0,1000)));
        assert(accepted(x.guard.WebRequest(3009,G::BubblesOnly,0,0,nullptr,1000)));
        x.Tick(3010,false);
        assert(accepted(x.guard.WebRequest(3010,G::IgnitionOnly,0,0,nullptr,0,1000)));
        assert(x.guard.Bubbling() && x.guard.Igniting());
    }
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
        assert(!accepted(x.guard.Bubbles(100,1,1000)) && !accepted(x.guard.Ignition(100,2,1000)));
    }
    for(auto target:{G::BubblesOnly,G::IgnitionOnly}) {
        ControlSessions x; ready(x);
        const int maximum = target == G::BubblesOnly ? 30000 : 5000;
        for(int ms:{0,-1,maximum+1,60000}) {
            const auto r=x.guard.WebRequest(0,target,0,0,nullptr,target==G::BubblesOnly?ms:0,target==G::IgnitionOnly?ms:0);
            assert(!accepted(r)); off(x);
        }
        // Per-lane lower and upper duration boundaries.
        assert(accepted(x.guard.WebRequest(0,target,0,0,nullptr,target==G::BubblesOnly?1:0,target==G::IgnitionOnly?1:0)));
        x.Tick(1,false); off(x);
        x.Tick(5001,false);
        assert(accepted(x.guard.WebRequest(5001,target,0,0,nullptr,target==G::BubblesOnly?maximum:0,target==G::IgnitionOnly?maximum:0)));
        x.Tick(5001+maximum,false); off(x);
        // Voice effect survives unrelated web release; web effect survives voice loss.
        ControlSessions y; ready(y); auto web=y.Acquire(0); y.Tick(0,false); assert(y.Heartbeat(0,web));
        assert(accepted(y.guard.WebRequest(0,target,0,0,nullptr,target==G::BubblesOnly?5000:0,target==G::IgnitionOnly?5000:0)));
        assert(y.Release(1,web)); y.Tick(1,false);
        assert(target==G::BubblesOnly?y.guard.Bubbling():y.guard.Igniting());
        web=y.Acquire(2); assert(y.Heartbeat(2,web));
        assert(!std::strcmp(y.WebAction(2,web,1,y.window,target,0,0,nullptr,target==G::BubblesOnly?1000:0,target==G::IgnitionOnly?1000:0),"voice_preempted"));
        off(y);
        y.Tick(5002,false); web=y.Acquire(5002); assert(web); assert(y.Heartbeat(5002,web));
        assert(accepted(y.WebAction(5002,web,1,y.window,target,0,0,nullptr,target==G::BubblesOnly?1000:0,target==G::IgnitionOnly?1000:0)));
        assert(!y.VoiceClaim(5002,55,target)); y.VoiceLink(5003,false); y.Tick(5003,false);
        assert(target==G::BubblesOnly?y.guard.Bubbling():y.guard.Igniting());
        assert(y.Release(5004,web)); off(y);
        // Queued effects are cancelled by all-stop and by a conflicting web request.
        ControlSessions z; ready(z); auto ticket=z.VoiceClaim(0,1,target); assert(ticket); z.Stop(1);
        assert(!accepted(target==G::BubblesOnly?z.guard.Bubbles(2,ticket,1000):z.guard.Ignition(2,ticket,1000)));
    }
    std::cout << "PASS: four concurrent lanes, independent expiry, per-lane duration boundaries, no extension, ignition interval, all stop/fault paths, effect source isolation and preemption\n";
}
