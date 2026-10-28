#include "control_sessions.h"
#include <cassert>
#include <cstring>
#include <iostream>
using G = AudioActionGuard;
static bool is(const char* a, const char* b) { return !std::strcmp(a,b); }
static ControlSessions ready() {
    ControlSessions s; s.WifiLink(0,true); s.VoiceLink(0,true); s.Tick(0,false); return s;
}
static ActionPlan example(bool spray) {
    ActionPlan p;
    p.count=3;
    p.steps[0]={"forward",5000,0,0,0};
    p.steps[1]={"left",1000,spray?1000:0,0,0};
    p.steps[2]={"forward",5000,0,0,0};
    return p;
}
static void start(ControlSessions& s, const ActionPlan& p) {
    assert(is(s.VoicePlan(0,s.VoiceClaim(0,1,G::PlanMode),p),"accepted"));
}
int main() {
    // Requested durations, including >30 s and the protocol integer boundary, never truncate.
    for (const char* d : {"forward","backward","left","right"}) for (int ms : {5000,60000,INT_MAX}) {
        auto s=ready(); assert(is(s.guard.Move(0,s.VoiceClaim(0,1,G::MoveOnly),ms,d),"accepted"));
        s.Tick(ms-1,false); assert(s.guard.Moving());
        assert(G::Remaining(s.guard.motion,ms-1)==1);
        s.Tick(ms,false); assert(!s.guard.Moving());
    }
    {
        auto s=ready(); assert(is(s.guard.MoveAndWater(0,s.VoiceClaim(0,1,G::Both),5000,5000,"forward"),"accepted"));
        s.Tick(4999,false); assert(s.guard.Moving()&&s.guard.Watering());
        s.Tick(5000,false); assert(!s.guard.Moving()&&!s.guard.Watering());
    }
    for (bool spray : {false,true}) {
        auto s=ready(); auto p=example(spray); start(s,p);
        assert(!s.VoiceClaim(1,2,G::WaterOnly)); // Entire sequence reserved, including future lanes.
        s.Tick(4999,false); assert(s.plan_step==1&&is(s.guard.direction,"forward")&&!s.guard.Watering());
        s.Tick(5000,false); assert(s.plan_active&&is(s.plan_result,"waiting")&&!s.guard.Moving());
        s.Tick(5199,false); assert(s.plan_step==1);
        s.Tick(5200,false); assert(s.plan_step==2&&is(s.guard.direction,"left")&&s.guard.Watering()==spray);
        s.Tick(6200,false); assert(!s.guard.Moving()&&!s.guard.Watering());
        s.Tick(6400,false); assert(s.plan_step==3&&is(s.guard.direction,"forward"));
        s.Tick(11400,false); assert(!s.plan_active&&is(s.plan_result,"completed")&&s.guard.Starts()==(spray?4u:3u));
    }
    {
        auto s=ready(); auto p=example(true); p.count=2; start(s,p);
        s.Tick(5000,false); assert(!s.guard.Watering());
        s.Tick(5200,false); assert(s.guard.Moving()&&s.guard.Watering()&&is(s.guard.direction,"left"));
        s.Tick(6200,false); assert(!s.plan_active&&is(s.plan_result,"completed")&&s.guard.Starts()==3);
        s.Tick(10000,false); assert(s.guard.Starts()==3);
    }
    // Stops and source changes cancel during both output and inter-step waiting.
    for (uint64_t when : {100u,5000u}) for (int mode=0; mode<8; ++mode) {
        auto s=ready(); start(s,example(true)); s.Tick(when,false);
        if(mode==0) s.Stop(when);
        if(mode==1) s.Tick(when,true);
        if(mode==2) s.VoiceLink(when,false);
        if(mode==3) s.WifiLink(when,false);
        if(mode==4) s.Shutdown(when);
        if(mode==5) s.Tick(when,false,true);
        if(mode==6) s.Tick(when-1,false);
        if(mode==7) {
            auto web=s.Acquire(when); assert(web&&s.Heartbeat(when,web));
            assert(is(s.WebAction(when,web,1,s.window,G::WaterOnly,0,1000,nullptr),"voice_preempted"));
        }
        assert(!s.plan_active&&!s.guard.Moving()&&!s.guard.Watering()&&is(s.plan_result,"cancelled"));
        auto starts=s.guard.Starts(); s.WifiLink(when+1000,true); s.VoiceLink(when+1000,true); s.Tick(when+1000,false);
        s.Tick(when+20000,false); assert(s.guard.Starts()==starts&&!s.plan_active);
    }
    {
        auto s=ready(); auto p=example(false); p.steps[2].water_ms=30001;
        assert(is(s.VoicePlan(0,s.VoiceClaim(0,1,G::PlanMode),p),"invalid_plan")); assert(s.guard.Starts()==0);
    }
    for (int mode=0; mode<5; ++mode) {
        auto s=ready(); auto p=example(false); int ticket=s.VoiceClaim(0,1,G::PlanMode); assert(ticket);
        if(mode==0) {s.Stop(1);}
        if(mode==1) {s.Tick(5000,false);}
        if(mode==2) {s.VoiceLink(1,false);s.VoiceLink(2,true);s.Tick(2,false);}
        if(mode==3) {s.guard.Water(0,s.VoiceClaim(0,2,G::WaterOnly),1000);}
        if(mode==4) {assert(is(s.VoicePlan(0,ticket,p),"accepted"));s.Stop(1);}
        assert(!is(s.VoicePlan(mode==1?5000:2,ticket,p),"accepted"));
        assert(!s.plan_active);
    }
    // Atomic multi-channel start, independent deadlines, and equal elapsed ignition cooldown.
    {
        auto s=ready(); ActionPlan p; p.count=2;
        p.steps[0]={"left",1000,2000,3000,1000}; p.steps[1]={"none",0,1000,0,1000}; start(s,p);
        assert(s.guard.Starts()==4);
        s.Tick(1000,false); assert(!s.guard.Moving()&&!s.guard.Igniting()&&s.guard.Watering()&&s.guard.Bubbling());
        s.Tick(2000,false); assert(!s.guard.Watering()&&s.guard.Bubbling());
        s.Tick(3000,false); assert(s.plan_step==1);
        s.Tick(3200,false); assert(s.plan_step==2&&s.guard.Watering()&&s.guard.Igniting());
        s.Tick(4200,false); assert(!s.plan_active);
    }
    {
        auto s=ready(); ActionPlan p; p.count=2; p.steps[0]={"none",0,0,0,1000}; p.steps[1]=p.steps[0]; start(s,p);
        s.Tick(1000,false); s.Tick(1999,false); assert(s.plan_step==1&&!s.guard.Igniting());
        s.Tick(2000,false); assert(s.plan_step==2&&s.guard.Igniting());
    }
    {
        auto s=ready(); auto web=s.Acquire(0); assert(s.Heartbeat(0,web));
        assert(is(s.WebAction(0,web,1,s.window,G::WaterOnly,0,1000,nullptr),"accepted"));
        assert(!s.VoiceClaim(0,1,G::PlanMode));
    }
    { // An idle web page may expire without cancelling a voice sequence.
        auto s=ready(); assert(s.Acquire(0)); start(s,example(false));
        s.Tick(2000,false); assert(!s.owner&&s.plan_active&&s.guard.Moving());
    }
    { // Late ticks preserve full intervals; no catch-up of later steps.
        auto s=ready(); start(s,example(false)); s.Tick(9000,false);
        assert(s.plan_step==1&&is(s.plan_result,"waiting"));
        s.Tick(9200,false); assert(s.plan_step==2&&s.guard.motion.ends_at==10200);
    }
    { // Long motion overflow is rejected before either part of a combined action starts.
        G g; auto now=UINT64_MAX-10000; g.Tick(now,true,false);
        assert(!is(g.MoveAndWater(now,g.Claim(now,1,G::Both),INT_MAX,1000,"forward"),"accepted"));
        assert(!g.Moving()&&!g.Watering()&&g.Starts()==0);
    }
    std::cout<<"PASS: long movement, simultaneous/ordered steps, cooldowns, atomic validation, cancellation/reconnect, replay, web priority\n";
}
