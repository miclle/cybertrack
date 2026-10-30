#include "proximity_guard.h"
#include "control_sessions.h"
#include <cassert>
#include <cstring>
#include <iostream>
using G = AudioActionGuard;
using P = ProximityGuard;
static bool is(const char* a, const char* b) { return !std::strcmp(a,b); }
static ultrasonic::Reading reading(unsigned mm, uint64_t time) {
    return {ultrasonic::Error::None, mm, 0, time, true};
}
static ControlSessions ready() {
    ControlSessions s; s.auto_avoidance_enabled=true; s.WifiLink(0,true); s.VoiceLink(0,true); s.Tick(0,false); return s;
}
// Exercise the actual adapter tick order, not a reimplementation of it.
ControlSessions sessions;
AudioActionGuard& guard=sessions.guard;
P proximity;
struct { bool fault=false; } outputs;
constexpr int stop_pin=0;
bool pressed=false, sound_enabled=false;
P::Alert sound_event=P::None;
ultrasonic::Reading sensor;
int gpio_get_level(int) { return !pressed; }
ultrasonic::Reading CyberTrackDistanceSnapshot() { return sensor; }
void CyberTrackProximityAlert(P::Alert a,bool enabled) { sound_event=a; sound_enabled=enabled; }
#include "proximity_tick.inc"
int main() {
    assert(!ControlSessions{}.auto_avoidance_enabled);
    for (int source=0; source<3; ++source) { // Voice, web hold, and voice sequence share the switch.
        sessions=ready(); sessions.auto_avoidance_enabled=false; proximity={};
        auto owner=sessions.Acquire(0); assert(owner && sessions.Heartbeat(0,owner));
        sensor=reading(100,0); TickLocked(0);
        assert(!guard.forward_blocked);
        if (source==0)
            assert(is(guard.MoveAndWater(0,sessions.VoiceClaim(0,1,G::Both),10000,10000,"forward"),"accepted"));
        else if (source==1)
            assert(is(sessions.DriveStart(0,owner,1,sessions.window,"forward",10000),"accepted"));
        else {
            ActionPlan plan; plan.count=2;
            plan.steps[0]={"forward",10000,10000,0,0}; plan.steps[1]={"left",1000,0,0,0};
            assert(is(sessions.VoicePlan(0,sessions.VoiceClaim(0,1,G::PlanMode),plan),"accepted"));
        }
        sensor=reading(100,10); TickLocked(10);
        assert(guard.Moving() && guard.Watering() && !guard.forward_blocked && sound_event==P::Beep);
        assert(is(sessions.WebAutoAvoidance(10,owner+1,2,sessions.window,true),"session_expired"));
        assert(!sessions.auto_avoidance_enabled);
        assert(sessions.Heartbeat(20,owner));
        assert(is(sessions.WebAutoAvoidance(20,owner,2,sessions.window,true),"ok"));
        TickLocked(20); // Enabling immediately applies the current fresh near reading.
        assert(!guard.Moving() && guard.Watering() && guard.forward_blocked && sound_event==P::Stop);
        assert(!sessions.plan_active);
        assert(is(sessions.WebAutoAvoidance(21,owner,2,sessions.window,false),"duplicate_request"));
        assert(sessions.auto_avoidance_enabled);
        assert(sessions.Heartbeat(21,owner));
        assert(is(sessions.WebAutoAvoidance(21,owner,3,sessions.window+1,false),"stale_request"));
        assert(sessions.auto_avoidance_enabled);
        const auto starts=guard.Starts();
        assert(sessions.Heartbeat(30,owner));
        assert(is(sessions.WebAutoAvoidance(30,owner,4,sessions.window,false),"ok"));
        sensor.error=ultrasonic::Error::NoEcho; TickLocked(30);
        assert(!guard.forward_blocked && !guard.Moving() && guard.Starts()==starts);
        if (source==1) assert(is(sessions.DriveRenew(31,owner,1,1),"drive_cancelled"));
        sensor=reading(100,300); TickLocked(300);
        assert(is(guard.Move(300,sessions.VoiceClaim(300,5,G::MoveOnly),1000,"forward"),"accepted"));
        TickLocked(300); assert(guard.Moving());
    }
    { // Browser release/reconnect and link loss do not reset the device-wide preference.
        auto s=ready(); auto owner=s.Acquire(0);
        assert(s.Release(1,owner) && s.auto_avoidance_enabled);
        assert(s.Acquire(2) && s.auto_avoidance_enabled);
        s.WifiLink(3,false); assert(s.auto_avoidance_enabled);
    }
    P p;
    assert(p.Update(reading(500,0),0,true,true)==P::None);
    assert(p.Update(reading(499,1),1,true,true)==P::Beep && p.beeping && !p.blocked);
    assert(p.Update(reading(400,800),800,true,true)==P::None);
    assert(p.Update(reading(400,801),801,true,true)==P::Beep);
    assert(p.Update(reading(399,1200),1200,true,true)==P::None);
    assert(p.Update(reading(150,1201),1201,true,true)==P::Beep && !p.blocked);
    assert(p.Update(reading(149,1202),1202,true,true)==P::Stop && p.blocked && !p.beeping);
    for (unsigned mm : {149u,150u,199u}) assert(p.Update(reading(mm,1300),1300,false,true)==P::None && p.blocked);
    auto invalid = reading(1000,1400); invalid.error = ultrasonic::Error::NoEcho;
    assert(p.Update(invalid,1400,false,true)==P::None && p.blocked);
    assert(p.Update(reading(1000,1400),1901,false,true)==P::None && p.blocked);
    assert(p.Update(reading(1000,2000),1999,false,true)==P::None && p.blocked);
    assert(p.Update(reading(200,2000),2000,false,true)==P::None && !p.blocked);
    assert(p.Update(reading(149,2100),2100,false,true)==P::None && p.blocked);
    { // 15 cm is an exclusive stop threshold; the former 30 cm zone remains passable.
        P closer;
        assert(closer.Update(reading(300,0),0,true,true)==P::Beep && !closer.blocked);
        assert(closer.Update(reading(200,400),400,true,true)==P::Beep && !closer.blocked);
        assert(closer.Update(reading(150,800),800,true,true)==P::Beep && !closer.blocked);
        assert(closer.Update(reading(149,801),801,true,true)==P::Stop && closer.blocked);
        assert(closer.Update(reading(199,900),900,false,true)==P::None && closer.blocked);
        assert(closer.Update(reading(200,1000),1000,false,true)==P::None && !closer.blocked);
        assert(closer.Update(reading(150,1100),1100,false,true)==P::None && !closer.blocked);
    }
    { // Standby/reverse/turning stay silent, including repeated 15/20 cm crossings.
        P quiet;
        for (uint64_t t=0; t<60000; t+=100)
            assert(quiet.Update(reading(t%200 ? 149 : 450,t),t,false,true)==P::None && !quiet.beeping);
        quiet.Update(reading(200,60000),60000,false,true);
        assert(quiet.Update(reading(149,60100),60100,true,true)==P::Stop);
        assert(quiet.Update(reading(149,60200),60200,true,true)==P::None); // One stop event, even before caller cancels.
    }
    { // Band jitter, invalid data and far spikes cannot produce catch-up bursts.
        P cadence;
        assert(cadence.Update(reading(450,0),0,true,true)==P::Beep);
        for (uint64_t t=5; t<400; t+=5) {
            const unsigned mm=t%10 ? 399 : 401;
            assert(cadence.Update(reading(mm,t),t,true,true)==P::None);
        }
        assert(cadence.Update(reading(399,400),400,true,true)==P::Beep);
        assert(cadence.Update(reading(550,500),500,true,true)==P::None && !cadence.beeping);
        assert(cadence.Update(reading(399,600),600,true,true)==P::None);
        auto lost=reading(399,700); lost.error=ultrasonic::Error::NoEcho;
        assert(cadence.Update(lost,700,true,true)==P::None && !cadence.beeping);
        assert(cadence.Update(reading(399,750),750,true,true)==P::None);
        assert(cadence.Update(reading(399,800),800,true,true)==P::Beep);
        assert(cadence.Update(reading(399,10000),10000,true,true)==P::Beep);
        assert(cadence.Update(reading(399,10000),10005,true,true)==P::None);
        assert(cadence.Update(reading(399,10000),10501,true,true)==P::None && !cadence.beeping);
    }
    { // Stop sound follows actual forward motion, not a rejected request or an unlocked reading.
        auto s=ready(); P g;
        assert(is(s.guard.Move(0,s.VoiceClaim(0,1,G::MoveOnly),10000,"forward"),"accepted"));
        const auto alert=g.Update(reading(149,10),10,s.guard.Moving() && is(s.guard.direction,"forward"),true);
        s.SetForwardBlocked(10,g.blocked);
        assert(alert==P::Stop && !s.guard.Moving());
        assert(g.Update(reading(149,20),20,s.guard.Moving(),true)==P::None);
        s.SetForwardBlocked(30,false);
        assert(!s.guard.Moving());
        // A command that has reached its deadline must not generate a stop tone.
        auto deadline=ready(); P expired;
        assert(is(deadline.guard.Move(0,deadline.VoiceClaim(0,1,G::MoveOnly),100,"forward"),"accepted"));
        deadline.Tick(100,false);
        assert(expired.Update(reading(149,100),100,deadline.guard.Moving(),true)==P::None && expired.blocked);
    }
    { // A newly near obstacle must reject the NEXT step before its spray starts.
        sessions=ready(); proximity={}; ActionPlan plan; plan.count=2;
        plan.steps[0]={"left",1000,0,0,0}; plan.steps[1]={"forward",1000,1000,0,0};
        assert(is(sessions.VoicePlan(0,sessions.VoiceClaim(0,1,G::PlanMode),plan),"accepted"));
        sensor=reading(1000,1000); TickLocked(1000);
        sensor=reading(149,1200); TickLocked(1200);
        assert(guard.Starts()==1 && !guard.Moving() && !guard.Watering());
        assert(is(sessions.plan_result,"obstacle_blocked") && sound_event==P::None);
    }
    { // Real adapter stops forward before audio and preserves independent effects.
        sessions=ready(); proximity={};
        assert(is(guard.MoveAndWater(0,sessions.VoiceClaim(0,1,G::Both),10000,10000,"forward"),"accepted"));
        sensor=reading(149,10); TickLocked(10);
        assert(sound_event==P::Stop && !sound_enabled && !guard.Moving() && guard.Watering());
        TickLocked(15); assert(sound_event==P::None);
        sessions=ready(); proximity={};
        assert(is(guard.Move(0,sessions.VoiceClaim(0,1,G::MoveOnly),100,"forward"),"accepted"));
        sensor=reading(149,100); TickLocked(100);
        assert(sound_event==P::None && !sound_enabled && !guard.Moving());
        sessions=ready(); proximity={};
        assert(is(guard.Move(0,sessions.VoiceClaim(0,1,G::MoveOnly),1000,"forward"),"accepted"));
        sensor=reading(149,100); pressed=true; TickLocked(100); pressed=false;
        assert(sound_event==P::None && !sound_enabled && !guard.Moving());
    }
    { // Voice combined action: stop only forward and keep the independent spray deadline.
        auto s=ready();
        assert(is(s.guard.MoveAndWater(0,s.VoiceClaim(0,1,G::Both),10000,10000,"forward"),"accepted"));
        s.SetForwardBlocked(100,true); s.Tick(100,false);
        assert(!s.guard.Moving() && s.guard.Watering());
        s.SetForwardBlocked(300,false); s.Tick(300,false);
        assert(!s.guard.Moving() && s.guard.Watering()); // No automatic resume.
    }
    for (const char* d : {"backward","left","right"}) {
        auto s=ready(); s.SetForwardBlocked(0,true);
        assert(is(s.guard.Move(0,s.VoiceClaim(0,1,G::MoveOnly),1000,d),"accepted"));
        s.SetForwardBlocked(1,true); s.Tick(1,false); assert(s.guard.Moving());
    }
    { // No partial startup of a blocked forward + spray command, even with an older ticket.
        auto s=ready(); int ticket=s.VoiceClaim(0,1,G::Both);
        s.SetForwardBlocked(1,true);
        assert(!is(s.guard.MoveAndWater(1,ticket,1000,1000,"forward"),"accepted"));
        assert(is(s.guard.MoveAndWater(1,s.VoiceClaim(1,2,G::Both),1000,1000,"forward"),"obstacle_blocked"));
        assert(s.guard.Starts()==0);
        s.SetForwardBlocked(2,false);
        assert(!is(s.guard.MoveAndWater(2,ticket,1000,1000,"forward"),"accepted"));
    }
    { // Held forward cancellation must not fall through StopWeb and stop other held lanes.
        auto s=ready(); auto owner=s.Acquire(0); s.Heartbeat(0,owner);
        assert(is(s.EffectStart(0,owner,1,s.window,G::WaterOnly),"accepted"));
        s.Heartbeat(1,owner);
        assert(is(s.DriveStart(1,owner,2,s.window,"forward",0),"accepted"));
        s.SetForwardBlocked(100,true); s.Tick(100,false);
        assert(!s.drive_id && !s.guard.Moving() && s.guard.Watering() && s.water_hold.id);
        assert(is(s.DriveRenew(101,owner,2,1),"drive_cancelled"));
        assert(s.guard.Watering());
        s.Heartbeat(301,owner);
        assert(is(s.DriveStart(301,owner,3,s.window,"forward",0),"obstacle_blocked"));
        s.SetForwardBlocked(302,false);
        assert(is(s.DriveRenew(302,owner,2,1),"drive_cancelled"));
    }
    { // Cancel future steps when forward is interrupted, preserve running effects until their deadline.
        auto s=ready(); ActionPlan plan; plan.count=2;
        plan.steps[0]={"forward",1000,2000,0,0}; plan.steps[1]={"left",1000,0,0,0};
        assert(is(s.VoicePlan(0,s.VoiceClaim(0,1,G::PlanMode),plan),"accepted"));
        s.SetForwardBlocked(100,true); s.Tick(100,false);
        assert(!s.plan_active && is(s.plan_result,"obstacle_blocked") && s.guard.Watering());
        s.SetForwardBlocked(300,false); s.Tick(2300,false);
        assert(!s.guard.Moving() && !s.guard.Watering() && s.guard.Starts()==2);
    }
    { // A future forward step is rejected before any of its effects start.
        auto s=ready(); ActionPlan plan; plan.count=2;
        plan.steps[0]={"left",1000,0,0,0}; plan.steps[1]={"forward",1000,1000,0,0};
        assert(is(s.VoicePlan(0,s.VoiceClaim(0,1,G::PlanMode),plan),"accepted"));
        s.SetForwardBlocked(100,true); s.Tick(1000,false); s.Tick(1200,false);
        assert(!s.plan_active && is(s.plan_result,"obstacle_blocked") && s.guard.Starts()==1);
    }
    std::cout << "proximity forward-only tones, cadence, quiet standby, freshness, voice/web/sequence stops and no-resume: PASS\n";
}
