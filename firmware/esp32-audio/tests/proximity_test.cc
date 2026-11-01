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
        assert(guard.Moving() && guard.Watering() && !guard.forward_blocked && !sound_enabled && sound_event==P::None);
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
    { // Isolated and paired near spikes never sound; repeated ticks are not samples.
        P p;
        for (uint64_t base : {0u, 1000u, 2000u}) {
            assert(p.Update(reading(499,base),base,false,false)==P::None && !p.beeping);
            for (uint64_t t=base+5; t<base+100; t+=5)
                assert(p.Update(reading(499,base),t,false,false)==P::None && !p.beeping);
            assert(p.Update(reading(399,base+100),base+100,false,false)==P::None && !p.beeping);
            assert(p.Update(reading(500,base+200),base+200,false,false)==P::None && !p.beeping);
        }
        assert(p.Update(reading(499,3000),3000,false,false)==P::None);
        assert(p.Update(reading(450,3100),3100,false,false)==P::None);
        assert(p.Update(reading(400,3200),3200,false,false)==P::Beep && p.beeping);
        for (uint64_t t=3300; t<4000; t+=100)
            assert(p.Update(reading(400,t),t,false,false)==P::None && p.beeping);
        assert(p.Update(reading(400,4000),4000,false,false)==P::Beep);
        assert(p.Update(reading(399,4300),4300,false,false)==P::None);
        assert(p.Update(reading(399,4400),4400,false,false)==P::Beep);
        assert(p.Update(reading(500,4401),4401,false,false)==P::None && !p.beeping);
    }
    { // Every invalid/far snapshot resets confirmation, even after beeping began.
        auto invalid=reading(100,300); invalid.error=ultrasonic::Error::NoEcho;
        auto unsampled=reading(100,300); unsampled.sampled=false;
        for (const auto& interrupted : {invalid, unsampled, reading(19,300), reading(4001,300),
                                       reading(500,300), reading(100,0), reading(100,1000)}) {
            P p;
            assert(p.Update(reading(100,100),100,false,false)==P::None);
            assert(p.Update(reading(100,200),200,false,false)==P::None);
            assert(p.Update(reading(100,300),300,false,false)==P::Beep);
            assert(p.Update(interrupted,600,false,false)==P::None && !p.beeping);
            assert(p.Update(reading(100,700),700,false,false)==P::None && !p.beeping);
            assert(p.Update(reading(100,800),800,false,false)==P::None && !p.beeping);
            assert(p.Update(reading(100,900),900,false,false)==P::Beep);
        }
    }
    { // Missing control ticks and backward sample times cannot preserve confirmation.
        P p;
        assert(p.Update(reading(100,0),0,false,false)==P::None);
        assert(p.Update(reading(100,100),100,false,false)==P::None);
        assert(p.Update(reading(100,601),601,false,false)==P::None && !p.beeping);
        assert(p.Update(reading(100,701),701,false,false)==P::None);
        assert(p.Update(reading(100,801),801,false,false)==P::Beep);
        assert(p.Update(reading(100,10000),10000,false,false)==P::None && !p.beeping);
        assert(p.Update(reading(100,10100),10100,false,false)==P::None);
        assert(p.Update(reading(100,10200),10200,false,false)==P::Beep);
        assert(p.Update(reading(100,10150),10205,false,false)==P::None && !p.beeping);
        assert(p.Update(reading(100,10300),10300,false,false)==P::None && !p.beeping);
        assert(p.Update(reading(100,10400),10400,false,false)==P::None && p.beeping);
    }
    { // Cadence survives a short reset and never catches up missed events.
        P p;
        p.Update(reading(399,0),0,false,false);
        p.Update(reading(399,100),100,false,false);
        assert(p.Update(reading(399,200),200,false,false)==P::Beep);
        assert(p.Update(reading(500,205),205,false,false)==P::None);
        assert(p.Update(reading(399,210),210,false,false)==P::None);
        assert(p.Update(reading(399,310),310,false,false)==P::None);
        assert(p.Update(reading(399,410),410,false,false)==P::None && p.beeping);
        assert(p.Update(reading(399,600),600,false,false)==P::Beep);
        assert(p.Update(reading(399,600),605,false,false)==P::None);
        assert(p.Update(reading(399,600),1101,false,false)==P::None && !p.beeping);
    }
    { // Protection still acts on the first sample, including exact boundary/fault cases.
        P p;
        assert(p.Update(reading(300,0),0,true,true)==P::None && !p.blocked);
        assert(p.Update(reading(150,100),100,true,true)==P::None && !p.blocked);
        assert(p.Update(reading(149,101),101,true,true)==P::Stop && p.blocked && !p.beeping);
        for (unsigned mm : {149u,150u,199u})
            assert(p.Update(reading(mm,200),200,false,true)==P::None && p.blocked);
        auto invalid=reading(1000,300); invalid.error=ultrasonic::Error::NoEcho;
        assert(p.Update(invalid,300,false,true)==P::None && p.blocked);
        assert(p.Update(reading(1000,300),801,false,true)==P::None && p.blocked);
        assert(p.Update(reading(1000,1000),999,false,true)==P::None && p.blocked);
        assert(p.Update(reading(200,1000),1000,false,true)==P::None && !p.blocked);
    }
    for (bool enabled : {false,true}) {
        for (const char* direction : {"none","forward","backward","left","right"}) {
            sessions=ready(); sessions.auto_avoidance_enabled=enabled; proximity={};
            if (!is(direction,"none"))
                assert(is(guard.Move(0,sessions.VoiceClaim(0,1,G::MoveOnly),5000,direction),"accepted"));
            const auto starts=guard.Starts();
            sensor=reading(450,0); TickLocked(0); assert(!sound_enabled && sound_event==P::None);
            TickLocked(5); assert(!sound_enabled && sound_event==P::None);
            sensor=reading(450,100); TickLocked(100); assert(!sound_enabled && sound_event==P::None);
            sensor=reading(450,200); TickLocked(200); assert(sound_enabled && sound_event==P::Beep);
            sensor=reading(400,600); TickLocked(600); assert(sound_event==P::None);
            sensor=reading(400,1000); TickLocked(1000); assert(sound_event==P::Beep);
            sensor=reading(500,1001); TickLocked(1001);
            assert(!sound_enabled && sound_event==P::None && !guard.forward_blocked && guard.Starts()==starts);
            assert(guard.Moving()==!is(direction,"none"));
        }
    }
    { // Movement and switch transitions neither bypass confirmation nor reset cadence.
        P p;
        assert(p.Update(reading(100,0),0,true,false)==P::None);
        assert(p.Update(reading(100,100),100,false,false)==P::None);
        assert(p.Update(reading(100,200),200,false,true)==P::Beep && p.blocked);
        assert(p.Update(reading(100,300),300,false,false)==P::None && !p.blocked && p.beeping);
        assert(p.Update(reading(100,600),600,true,false)==P::Beep);
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
        TickLocked(15); assert(sound_event==P::None && !sound_enabled);
        sensor=reading(149,110); TickLocked(110); assert(sound_event==P::None && !sound_enabled);
        sensor=reading(149,210); TickLocked(210); assert(sound_event==P::None && sound_enabled);
        sensor=reading(149,410); TickLocked(410);
        assert(sound_event==P::Beep && sound_enabled && !guard.Moving() && guard.Watering());
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
    std::cout << "three-sample audio confirmation, spike rejection, cadence, freshness, immediate voice/web/sequence stops and no-resume: PASS\n";
}
