#include "control_sessions.h"
#include <cassert>
#include <cstring>
#include <iostream>
using G = AudioActionGuard;
static bool accepted(const char* r) { return !std::strcmp(r, "accepted"); }
static uint32_t ready(ControlSessions& s) {
    s.WifiLink(0,true); s.VoiceLink(0,true); auto id=s.Acquire(0); s.Tick(0,false);
    assert(s.Heartbeat(0,id)); return id;
}
static void off(const ControlSessions& s) {
    assert(!s.frenzy_until && !s.guard.Moving() && !s.guard.Watering() && !s.guard.Bubbling() && !s.guard.Igniting());
}
int main() {
    for(int duration : {1,5000,10000,30000}) {
        ControlSessions s; auto id=ready(s);
        assert(accepted(s.FrenzyStart(0,id,1,s.window,duration)));
        assert(s.guard.left==-100 && s.guard.right==100);
        for(int t=0;t<duration;++t) {
            s.Tick(t,false);
            if(t%500==0) assert(s.Heartbeat(t,id));
            assert(s.guard.Moving() && s.guard.Watering() && s.guard.Bubbling());
            assert(s.guard.Igniting()==(t%2000<1000));
            if(!s.guard.Igniting()) {
                assert(!s.VoiceClaim(t,100+t,G::IgnitionOnly));
                assert(accepted(s.WebAction(t,id,2+t,s.window,G::IgnitionOnly,0,0,nullptr,0,1000))==false);
            }
        }
        s.Tick(duration,false);off(s);
        assert(s.guard.motion.starts==1 && s.guard.spray.starts==1 && s.guard.bubbles.starts==1);
        assert(s.guard.ignition.starts==static_cast<unsigned>((duration+1999)/2000));
        s.Tick(duration+1,false);off(s);
    }
    for(int invalid : {-1,0,30001,INT_MAX}) {
        ControlSessions s; auto id=ready(s);
        assert(!accepted(s.FrenzyStart(0,id,1,s.window,invalid)));off(s);
    }
    for(int cause=0;cause<8;++cause) {
        ControlSessions s;auto id=ready(s);assert(accepted(s.FrenzyStart(0,id,1,s.window,30000)));
        s.Tick(100,false);assert(s.Heartbeat(100,id));
        if(cause==0) s.Stop(101);
        if(cause==1) s.Tick(101,true);
        if(cause==2) s.WifiLink(101,false);
        if(cause==3) s.Release(101,id);
        if(cause==4) s.Shutdown(101);
        if(cause==5) s.Tick(101,false,true);
        if(cause==6) s.Tick(99,false);
        if(cause==7) s.Tick(2100,false); // Exact 2 s ownership expiry, even if voice stays online.
        off(s);s.Tick(2200,false);off(s);
        assert(!accepted(s.FrenzyStart(2200,id,1,s.window,30000)));
    }
    { // All lanes must be ready. No partial start or takeover of an existing action.
        ControlSessions s;auto id=ready(s);
        assert(accepted(s.WebAction(0,id,1,s.window,G::WaterOnly,0,30000,nullptr)));
        assert(s.Heartbeat(1,id));assert(!accepted(s.FrenzyStart(1,id,2,s.window,5000)));
        assert(s.guard.Watering() && !s.guard.Moving() && !s.guard.Igniting());
    }
    { // Repeat clicks/new windows never extend the original hard deadline.
        ControlSessions s;auto id=ready(s);assert(accepted(s.FrenzyStart(0,id,1,s.window,5000)));
        assert(s.Heartbeat(1,id));assert(!accepted(s.FrenzyStart(1,id,2,s.window,30000)));
        assert(s.frenzy_until==5000);
        s.Tick(1000,false);assert(!s.guard.Igniting());
        s.VoiceLink(1001,false);s.Tick(1001,false);assert(s.frenzy_until==5000);
        s.Stop(1002);s.Tick(2000,false);off(s);
    }
    { // A delayed OFF starts a full elapsed-duration interval; do not catch up missed pulses.
        ControlSessions s;auto id=ready(s);assert(accepted(s.FrenzyStart(0,id,1,s.window,10000)));
        s.Tick(1200,false);assert(s.guard.ignition.cooldown_until==2400);
        assert(s.Heartbeat(1200,id));s.Tick(2399,false);assert(!s.guard.Igniting());
        s.Tick(2400,false);assert(s.guard.Igniting() && s.guard.ignition.ends_at==3400);
        s.Stop(2700);assert(s.guard.ignition.cooldown_until==3000);off(s);
    }
    { // Ordinary motion now accepts more than 3 s; frenzy retains its own 30 s limit.
        ControlSessions s;ready(s);assert(accepted(s.guard.WebRequest(0,G::MoveOnly,3001,0,"left")));s.Stop(1);off(s);
    }
    for(int duration : {5000,10000,30000}) {
        ControlSessions s;ready(s);s.Release(0,s.owner);
        auto ticket=s.VoiceClaim(0,1,G::FrenzyMode);assert(ticket);
        assert(accepted(s.VoiceFrenzy(0,ticket,duration)));
        assert(!strcmp(s.FrenzySource(),"voice") && s.frenzy_duration_ms==static_cast<unsigned>(duration));
        for(int t=0;t<duration;t+=5) {
            s.Tick(t,false);
            assert(s.guard.Moving() && s.guard.Watering() && s.guard.Bubbling());
            assert(s.guard.Igniting()==(t%2000<1000));
        }
        s.Tick(duration,false);off(s);
        assert(!accepted(s.VoiceFrenzy(duration+5000,ticket,duration))); // consumed ticket
    }
    for(int cause=0;cause<7;++cause) {
        ControlSessions s;auto id=ready(s);auto ticket=s.VoiceClaim(0,1,G::FrenzyMode);
        assert(ticket && accepted(s.VoiceFrenzy(0,ticket,30000)));
        s.Tick(1000,false);assert(!s.guard.Igniting());
        assert(!s.VoiceClaim(1000,2,G::IgnitionOnly)); // reserve even during OFF phase
        if(cause==0) s.VoiceLink(1001,false);
        if(cause==1) s.WifiLink(1001,false);
        if(cause==2) s.Stop(1001);
        if(cause==3) s.Tick(1001,true);
        if(cause==4) s.Tick(1001,false,true);
        if(cause==5) s.Shutdown(1001);
        if(cause==6) {assert(s.Heartbeat(1001,id));assert(!strcmp(s.WebAction(1001,id,1,s.window,G::WaterOnly,0,1000,nullptr),"voice_preempted"));}
        off(s);s.Tick(2000,false);off(s);
    }
    for(bool release : {false,true}) {
        ControlSessions s;auto id=ready(s);auto ticket=s.VoiceClaim(0,1,G::FrenzyMode);
        assert(accepted(s.VoiceFrenzy(0,ticket,5000)));
        if(release) assert(s.Release(1000,id));
        s.Tick(2000,false); // web expiry/release must preserve a voice mode
        assert(s.frenzy_until==5000 && s.guard.Moving() && !strcmp(s.FrenzySource(),"voice"));
        s.Stop(2001);off(s);
    }
    for(int cause=0;cause<4;++cause) {
        ControlSessions s;auto id=ready(s);auto ticket=s.VoiceClaim(0,1,G::FrenzyMode);assert(ticket);
        if(cause==0) s.Stop(1);
        if(cause==1) s.VoiceLink(1,false);
        if(cause==2) assert(accepted(s.WebAction(1,id,1,s.window,G::WaterOnly,0,1000,nullptr)));
        if(cause==3) s.Tick(5000,false); // ticket age limit
        assert(!accepted(s.VoiceFrenzy(cause==3?5000:2,ticket,30000)));
        assert(!s.frenzy_until);
    }
    std::cout << "PASS: voice frenzy ticket replay/expiry/cancellation, 5/10/30 s without web heartbeat, source isolation, web preemption and voice/BOOT/fault/stop cancellation\n";
    std::cout << "PASS: frenzy durations/pulses, atomic admission, absolute deadline, all cancellation paths, source reservation, no extension/replay, delayed OFF and equal elapsed cooldown\n";
}
