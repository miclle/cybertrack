#include "control_sessions.h"
#include <cassert>
#include <cstring>
#include <iostream>
using G = AudioActionGuard;
bool is(const char* a, const char* b) { return !std::strcmp(a,b); }
ShowDraft::Command example() {
    ShowDraft::Command c;
    c.plan.count=2;
    c.plan.steps[0]={"left",100,0,200,0};
    c.plan.steps[1]={"none",0,0,300,0};
    return c;
}
ControlSessions ready() { ControlSessions s; s.WifiLink(0,true); s.VoiceLink(0,true); s.Tick(0,false); return s; }
uint32_t save(ControlSessions& s, uint32_t owner, unsigned seq=1, uint64_t now=0) {
    assert(s.Heartbeat(now,owner));
    assert(is(s.WebDraft(now,owner,seq,s.window,example()),"draft_saved"));
    assert(!s.plan_active && s.guard.Starts()==0);
    return s.draft.revision;
}
void confirm(ControlSessions& s, uint32_t owner, uint32_t revision, unsigned seq=2, uint64_t now=0) {
    assert(s.Heartbeat(now,owner));
    assert(is(s.WebConfirm(now,owner,seq,s.window,revision),"accepted"));
}
int main() {
    {
        ShowDraft d; auto c=example(); assert(is(d.Apply(0,c,1),"draft_saved"));
        auto edit=c; edit.edit=ShowDraft::ReplaceStep;edit.revision=d.revision;edit.step=1;
        edit.plan.count=1;edit.plan.steps[0].move_ms=80;
        assert(is(d.Apply(1,edit,1),"draft_saved")); assert(d.plan.steps[0].move_ms==80 && d.plan.steps[1].bubbles_ms==300);
        assert(is(d.Apply(2,edit,1),"draft_changed")); assert(d.plan.steps[0].move_ms==80);
        edit.revision=d.revision;edit.plan.steps[0].water_ms=1;
        assert(is(d.Apply(3,edit,1),"invalid_plan")); assert(d.revision==2);
        edit.edit=ShowDraft::RemoveStep;edit.step=1;
        assert(is(d.Apply(4,edit,1),"draft_saved"));assert(d.plan.count==1 && d.plan.steps[0].bubbles_ms==300);
        edit.revision=d.revision;
        assert(is(d.Apply(5,edit,1),"invalid_plan"));assert(d.active);
        d.Tick(300004);assert(!d.active);ActionPlan ignored;assert(d.Take(300004,3,ignored));
        assert(is(d.Apply(300004,c,1),"draft_saved"));assert(d.revision==4);
        d.Tick(300003);assert(!d.active); // Clock reversal never extends a proposal.
    }
    {
        auto s=ready();auto owner=s.Acquire(0);auto rev=save(s,owner);
        auto edited=example();edited.revision=rev;edited.plan.steps[1].bubbles_ms=500;
        s.Heartbeat(0,owner);assert(is(s.WebDraft(0,owner,2,s.window,edited),"draft_saved"));
        s.Heartbeat(0,owner);assert(is(s.WebConfirm(0,owner,3,s.window,rev),"draft_changed"));
        assert(s.guard.Starts()==0 && s.draft.active);
        confirm(s,owner,s.draft.revision,4);
        assert(is(s.PlanSource(),"web")&&is(s.MoveSource(),"web")&&is(s.BubblesSource(),"web"));
        assert(!s.draft.active && !s.VoiceClaim(1,1,G::MoveOnly));
        s.VoiceLink(50,false);s.Tick(50,false);assert(s.plan_active&&s.guard.Bubbling());
        s.Tick(200,false);s.Tick(400,false);assert(s.plan_step==2 && s.guard.bubbles.ends_at==900);
        s.Tick(900,false);assert(!s.plan_active&&is(s.plan_result,"completed"));
        auto starts=s.guard.Starts();s.Heartbeat(1000,owner);
        assert(is(s.WebConfirm(1000,owner,5,s.window,rev),"draft_changed"));assert(s.guard.Starts()==starts);
    }
    for (int failure=0;failure<7;++failure) {
        auto s=ready();auto owner=s.Acquire(0);auto rev=save(s,owner);
        if(failure==0)s.Stop(1);
        if(failure==1)s.Tick(1,true);
        if(failure==2)s.WifiLink(1,false);
        if(failure==3)s.Release(1,owner);
        if(failure==4)s.Tick(2000,false);
        if(failure==5)s.Shutdown(1);
        if(failure==6)s.Tick(1,false,true);
        assert(!s.draft.active);
        assert(!is(s.WebConfirm(2,owner,2,s.window,rev),"accepted"));assert(s.guard.Starts()==0);
    }
    for(int failure=0;failure<6;++failure) {
        auto s=ready();auto owner=s.Acquire(0);auto rev=save(s,owner);confirm(s,owner,rev);
        if(failure==0)s.Release(50,owner);
        if(failure==1)s.Tick(2000,false);
        if(failure==2)s.Stop(50);
        if(failure==3)s.Tick(50,true);
        if(failure==4)s.WifiLink(50,false);
        if(failure==5)s.Tick(50,false,true);
        assert(!s.plan_active&&!s.guard.Moving()&&!s.guard.Bubbling());
        auto starts=s.guard.Starts();s.WifiLink(3000,true);s.Tick(3000,false);s.Tick(4000,false);assert(s.guard.Starts()==starts);
    }
    { // An obstacle may leave the independent bubble lane running; it retains web ownership.
        auto s=ready();auto owner=s.Acquire(0);auto c=example();c.plan.steps[0].direction="forward";
        s.Heartbeat(0,owner);assert(is(s.WebDraft(0,owner,1,s.window,c),"draft_saved"));confirm(s,owner,s.draft.revision);
        s.SetForwardBlocked(10,true);assert(!s.plan_active&&s.guard.Bubbling());assert(is(s.BubblesSource(),"web"));
        s.Release(20,owner);assert(!s.guard.Bubbling());
    }
    { // A confirmed but unavailable draft is consumed, never queued for later.
        auto s=ready();auto owner=s.Acquire(0);auto rev=save(s,owner);
        assert(is(s.guard.Water(0,s.VoiceClaim(0,1,G::WaterOnly),100),"accepted"));
        s.Heartbeat(0,owner);assert(is(s.WebConfirm(0,owner,2,s.window,rev),"not_ready_or_busy"));assert(!s.draft.active);
    }
    { // Voice creates a proposal; there is no voice confirmation path.
        auto s=ready();auto c=example();int ticket=s.VoiceClaim(0,1,G::PlanMode);
        assert(is(s.VoiceDraft(0,ticket,c),"draft_saved"));assert(s.guard.Starts()==0);
        assert(!is(s.VoiceDraft(0,ticket,c),"draft_saved"));
        s.VoiceLink(1,false);assert(!s.draft.active);
        s.VoiceLink(2,true);s.Tick(2,false);ticket=s.VoiceClaim(2,2,G::PlanMode);s.Stop(3);
        assert(!is(s.VoiceDraft(4,ticket,c),"draft_saved"));assert(!s.draft.active);
    }
    {
        auto s=ready();auto owner=s.Acquire(0);save(s,owner);s.Tick(100,false);s.Tick(50,false);
        assert(!s.draft.active); // Clock fault even when time remains after the draft's creation.
    }
    std::cout<<"PASS: versioned no-output drafts, isolated edits, one-shot confirmation, expiry, source ownership and cancellation\n";
}
