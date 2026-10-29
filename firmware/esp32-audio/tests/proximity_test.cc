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
    ControlSessions s; s.WifiLink(0,true); s.VoiceLink(0,true); s.Tick(0,false); return s;
}
int main() {
    P p;
    assert(p.Update(reading(500,0),0)==P::None);
    assert(p.Update(reading(499,1),1)==P::Caution && !p.blocked);
    assert(p.Update(reading(300,2),2)==P::None && !p.blocked);
    assert(p.Update(reading(299,3),3)==P::Stop && p.blocked);
    for (unsigned mm : {299u,300u,349u}) assert(p.Update(reading(mm,4),4)==P::None && p.blocked);
    auto invalid = reading(1000,5); invalid.error = ultrasonic::Error::NoEcho;
    assert(p.Update(invalid,5)==P::None && p.blocked);
    assert(p.Update(reading(1000,5),506)==P::None && p.blocked);
    assert(p.Update(reading(1000,10),9)==P::None && p.blocked);
    assert(p.Update(reading(350,6),6)==P::None && !p.blocked);
    assert(p.Update(reading(299,7),7)==P::None && p.blocked); // Cooldown never delays protection.
    p.Update(reading(550,6000),6000);
    assert(p.Update(reading(299,6001),6001)==P::Stop); // Escalation announces only the critical zone.
    p.Update(reading(550,12000),12000);
    assert(p.Update(reading(499,12001),12001)==P::Caution);
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
    std::cout << "proximity thresholds, freshness, voice/web/sequence stops and no-resume: PASS\n";
}
