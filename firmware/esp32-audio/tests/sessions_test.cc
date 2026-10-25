#include "control_sessions.h"
#include <cassert>
#include <cstring>
#include <iostream>
using Target = AudioActionGuard;
static bool is(const char* actual, const char* expected) { return !strcmp(actual, expected); }
static uint32_t pair(ControlSessions& s, uint64_t now) {
    s.WifiLink(now, true); s.Tick(now, false);
    auto id = s.Acquire(now); assert(id); s.Tick(now, false);
    assert(s.Heartbeat(now, id)); return id;
}
int main() {
    // Web operates with no cloud audio session. Independent deadlines survive voice closure.
    ControlSessions s;
    auto id = pair(s, 0);
    assert(is(s.WebAction(0,id,1,s.window,Target::Both,1000,3000,"forward"), "accepted"));
    s.VoiceLink(100,true); s.VoiceLink(200,false); s.Tick(200,false);
    assert(s.guard.Moving() && s.guard.Watering());
    assert(!s.VoiceClaim(200,1,Target::MoveOnly)); assert(!s.Acquire(200));
    s.Tick(1000,false); assert(!s.guard.Moving() && s.guard.Watering());
    assert(s.Heartbeat(1000,id));
    s.Tick(1999,false); assert(s.guard.Watering());
    s.Tick(2999,false); assert(s.guard.Watering());
    s.Tick(3000,false); assert(!s.owner && !s.guard.Watering()); // exact lease boundary
    assert(!s.Heartbeat(3000,id)); assert(!s.Release(3000,id));
    assert(is(s.WebAction(3000,id,2,s.window,Target::MoveOnly,1,0,"forward"),"session_expired"));

    // Opening/closing a webpage leaves active and queued voice commands intact.
    ControlSessions v; v.WifiLink(0,true); v.VoiceLink(0,true); v.Tick(0,false);
    int ticket = v.VoiceClaim(0,10,Target::WaterOnly); assert(ticket);
    auto web = v.Acquire(1); assert(web); v.Tick(1,false); assert(v.Heartbeat(1,web));
    assert(is(v.guard.Water(1,ticket,10000), "accepted"));
    assert(!strcmp(v.WaterSource(),"voice"));
    assert(v.Release(2,web)); v.Tick(2,false); assert(v.guard.Watering());
    web=v.Acquire(3);v.Tick(3,false);assert(v.Heartbeat(3,web));
    assert(is(v.DriveStart(3,web,1,v.window,"forward",0),"accepted"));
    assert(!strcmp(v.MoveSource(),"web") && !strcmp(v.WaterSource(),"voice"));
    assert(!v.VoiceClaim(4,11,Target::MoveOnly)); // Cannot supersede web movement.
    assert(v.Release(5,web));v.Tick(5,false);
    assert(!v.guard.Moving() && v.guard.Watering()); // Page release stops its own lane only.
    v.VoiceLink(6,false);v.Tick(6,false);assert(!v.guard.Watering());
    v.VoiceLink(1006,true);v.Tick(1006,false);
    web=v.Acquire(1006);assert(v.Heartbeat(1006,web));
    ticket=v.VoiceClaim(1006,12,Target::WaterOnly);assert(ticket);
    assert(is(v.WebAction(1006,web,1,v.window,Target::WaterOnly,0,1000,nullptr),"accepted"));
    assert(is(v.guard.Water(1007,ticket,1000),"cancelled_or_duplicate")); // Web cancels conflicting queued voice.
    v.Tick(2006,false);v.Tick(3006,false);assert(!v.owner && !v.guard.Watering());
    assert(!v.VoiceClaim(3006,12,Target::WaterOnly)); // Voice replay history survived opening and closing page.

    // Active voice is interrupted by a valid conflicting web request; cooldown is retained, no queued restart.
    ControlSessions priority; priority.WifiLink(0,true);priority.VoiceLink(0,true);priority.Tick(0,false);
    ticket=priority.VoiceClaim(0,1,Target::Both);assert(ticket);
    assert(is(priority.guard.MoveAndWater(0,ticket,3000,10000,"forward"),"accepted"));
    auto pid=priority.Acquire(1);assert(pid);priority.Tick(1,false);assert(priority.Heartbeat(1,pid));
    assert(is(priority.DriveStart(1,pid,1,priority.window,"right",0),"voice_preempted"));
    assert(!priority.guard.Moving() && priority.guard.Watering());
    assert(priority.guard.motion.cooldown_until==201 && priority.drive_id==0);
    assert(priority.Heartbeat(2,pid));
    assert(is(priority.WebAction(2,pid,2,priority.window,Target::WaterOnly,0,0,nullptr),"duration_out_of_range"));
    assert(priority.guard.Watering()); // Invalid input cannot preempt.
    assert(priority.Heartbeat(3,pid));
    assert(is(priority.WebAction(3,pid,3,priority.window,Target::WaterOnly,0,1000,nullptr),"voice_preempted"));
    assert(!priority.guard.Watering() && priority.guard.spray.cooldown_until==203);
    priority.Tick(1003,false);assert(priority.Heartbeat(1003,pid));
    assert(is(priority.WebAction(1003,pid,4,priority.window,Target::WaterOnly,0,10000,nullptr),"accepted"));
    priority.Tick(2003,false);assert(priority.Heartbeat(2003,pid));priority.Tick(3001,false);
    ticket=priority.VoiceClaim(3001,2,Target::MoveOnly);assert(ticket);
    assert(is(priority.guard.Move(3001,ticket,1000,"left"),"accepted")); // Web water + voice move coexist.
    priority.Tick(4003,false);assert(!priority.owner && !priority.guard.Watering() && !priority.guard.Moving());

    // Web lease expiry must not cancel a separate active voice lane, and voice loss must not cancel web.
    ControlSessions mixed; auto mid=pair(mixed,0);mixed.VoiceLink(0,true);
    assert(is(mixed.DriveStart(0,mid,1,mixed.window,"forward",0),"accepted"));
    ticket=mixed.VoiceClaim(1,1,Target::WaterOnly);assert(ticket);
    assert(is(mixed.guard.Water(1,ticket,10000),"accepted"));
    mixed.Tick(600,false);assert(!mixed.guard.Moving() && mixed.guard.Watering());
    mixed.Tick(2000,false);assert(!mixed.owner && mixed.guard.Watering());
    mixed.WifiLink(2001,false);mixed.Tick(2001,false);assert(!mixed.guard.Watering());

    // One-shot windows, sequence monotonicity, exact expiry, and stop cancellation.
    ControlSessions w; auto wid = pair(w,0); auto window = w.window;
    assert(is(w.WebAction(1500,wid,1,window,Target::MoveOnly,1000,0,"forward"),"stale_request"));
    assert(w.Heartbeat(1500,wid)); window=w.window;
    assert(is(w.WebAction(1500,wid,1,window,Target::MoveOnly,1000,0,"forward"),"duplicate_request"));
    assert(is(w.WebAction(1500,wid,2,window,Target::MoveOnly,1000,0,"forward"),"accepted"));
    w.Stop(1501);
    assert(is(w.WebAction(1501,wid,3,window,Target::WaterOnly,0,1000,nullptr),"stale_request"));
    assert(!w.guard.Moving() && !w.guard.Watering());
    assert(w.Heartbeat(1502,wid)); window=w.window;
    w.Tick(1503,true); w.Tick(1534,false);
    assert(is(w.WebAction(1534,wid,4,window,Target::WaterOnly,0,1000,nullptr),"stale_request"));
    assert(w.Heartbeat(1534,wid));
    assert(is(w.WebAction(1534,wid,5,w.window,Target::Both,1000,1000,"forward"),"not_ready_or_busy"));
    assert(!w.guard.Watering()); // combined request must not partially start during move cooldown
    assert(w.Heartbeat(1535,wid));
    assert(is(w.WebAction(1535,wid,6,w.window,Target::WaterOnly,0,1000,nullptr),"accepted"));
    w.Tick(1536,false,true); assert(!w.guard.Watering());

    // Wi-Fi loss, shutdown and clock rollback cannot be healed by a late heartbeat.
    for (int fault=0;fault<3;++fault) {
        ControlSessions f; auto sid=pair(f,100);
        assert(is(f.WebAction(100,sid,1,f.window,Target::Both,3000,30000,"backward"),"accepted"));
        if(fault==0) f.WifiLink(101,false);
        if(fault==1) f.Shutdown(101);
        f.Tick(fault==2?99:101,false);
        assert(!f.owner && !f.guard.Moving() && !f.guard.Watering());
        assert(!f.Heartbeat(102,sid));
        if(fault==1) { f.WifiLink(102,true); f.VoiceLink(102,true); assert(!f.Acquire(102)); }
    }
    // Held movement stays continuous beyond the voice 3 s limit, with one start only.
    ControlSessions h; auto hid=pair(h,0);
    assert(is(h.DriveStart(0,hid,1,h.window,"forward",30000),"accepted"));
    for(uint64_t t=150;t<=15000;t+=150) {
        h.Tick(t,false);
        assert(h.guard.Moving());
        assert(is(h.DriveRenew(t,hid,1,h.drive_renewal),"renewed"));
        assert(h.guard.Starts()==2); // One motor start and one water start, never restart per renewal.
    }
    assert(is(h.DriveStop(15001,hid,1),"ok"));
    assert(!h.guard.Moving() && h.guard.Watering()); // Normal release stops only the tracks.
    assert(is(h.DriveRenew(15002,hid,1,101),"drive_cancelled"));
    h.Tick(17000,false); assert(!h.owner && !h.guard.Watering());

    // Renewals are response-chained. Replayed, expired or background state heartbeats cannot sustain a hold.
    ControlSessions d; auto did=pair(d,0);
    assert(is(d.DriveStart(0,did,1,d.window,"left",30000),"accepted"));
    assert(is(d.DriveRenew(150,did,1,1),"renewed"));
    assert(is(d.DriveRenew(300,did,1,1),"drive_cancelled"));
    assert(d.Heartbeat(700,did)); // State polling alone must not extend motor deadline.
    d.Tick(749,false); assert(d.guard.Moving());
    d.Tick(750,false); assert(!d.drive_id && !d.guard.Moving() && !d.guard.Watering());
    assert(is(d.DriveRenew(750,did,1,2),"drive_cancelled"));

    // A release can arrive before start; an old release cannot stop a newer hold.
    ControlSessions r; auto rid=pair(r,0); auto old_window=r.window;
    assert(is(r.DriveStop(1,rid,1),"ok"));
    assert(is(r.DriveStart(2,rid,1,old_window,"right",0),"duplicate_request"));
    assert(r.Heartbeat(3,rid));
    assert(is(r.DriveStart(3,rid,2,r.window,"right",0),"accepted"));
    assert(is(r.DriveStop(4,rid,1),"ok")); assert(r.guard.Moving());
    assert(is(r.DriveStop(4,rid,2),"ok")); assert(!r.guard.Moving());
    assert(r.Heartbeat(5,rid));
    assert(is(r.DriveStart(5,rid,3,r.window,"backward",0),"not_ready_or_busy")); // Cooldown remains.

    // Every global stop revokes renewal, even if the browser still thinks the pointer is down.
    for(int stop=0;stop<5;++stop) {
        ControlSessions b; auto bid=pair(b,100);
        assert(is(b.DriveStart(100,bid,1,b.window,"forward",30000),"accepted"));
        if(stop==0) b.Stop(101);
        if(stop==1) b.WifiLink(101,false);
        if(stop==2) b.Shutdown(101);
        b.Tick(stop==4?99:101,stop==3);
        assert(!b.drive_id && !b.guard.Moving() && !b.guard.Watering());
        assert(!is(b.DriveRenew(102,bid,1,1),"renewed"));
    }
    ControlSessions stale; auto stale_id=pair(stale,0);
    assert(is(stale.DriveStart(600,stale_id,1,stale.window,"forward",0),"stale_request"));
    ControlSessions boot; auto boot_id=pair(boot,0);
    boot.Tick(1,true); assert(boot.Heartbeat(1,boot_id)); auto boot_window=boot.window;
    boot.Tick(32,false);
    assert(is(boot.DriveStart(32,boot_id,1,boot_window,"forward",0),"stale_request"));
    // Three independent held lanes can continue beyond all timed limits without restarting.
    ControlSessions held; auto hs=pair(held,0);
    assert(is(held.DriveStart(0,hs,1,held.window,"forward",0),"accepted"));
    assert(held.Heartbeat(0,hs));
    assert(is(held.EffectStart(0,hs,2,held.window,Target::WaterOnly),"accepted"));
    assert(held.Heartbeat(0,hs));
    assert(is(held.EffectStart(0,hs,3,held.window,Target::BubblesOnly),"accepted"));
    assert(held.Heartbeat(0,hs));
    assert(is(held.WebAction(0,hs,4,held.window,Target::IgnitionOnly,0,0,nullptr,0,5000),"accepted"));
    for(unsigned t=150;t<=45000;t+=150) {
        held.Tick(t,false);
        assert(is(held.DriveRenew(t,hs,1,held.drive_renewal),"renewed"));
        assert(is(held.EffectRenew(t,hs,Target::WaterOnly,2,held.water_hold.renewal),"renewed"));
        assert(is(held.EffectRenew(t,hs,Target::BubblesOnly,3,held.bubbles_hold.renewal),"renewed"));
        assert(held.guard.Moving() && held.guard.Watering() && held.guard.Bubbling());
        assert(held.guard.Starts()==4);
        if(t>=5100) assert(!held.guard.Igniting());
    }
    assert(is(held.EffectStop(45001,hs,Target::WaterOnly,2),"ok"));
    assert(!held.guard.Watering() && held.guard.Bubbling() && held.guard.Moving());
    assert(is(held.EffectRenew(45002,hs,Target::WaterOnly,2,held.water_hold.renewal),"hold_cancelled"));
    assert(is(held.DriveStop(45003,hs,1),"ok"));
    assert(!held.guard.Moving() && held.guard.Bubbling());
    assert(is(held.EffectStop(45004,hs,Target::BubblesOnly,3),"ok"));
    assert(!held.guard.Bubbling() && !held.bubbles_hold.id);

    for(auto target:{Target::WaterOnly,Target::BubblesOnly}) {
        ControlSessions x;auto sid=pair(x,0);
        assert(is(x.EffectStop(1,sid,target,1),"ok"));
        assert(is(x.EffectStart(2,sid,1,x.window,target),"duplicate_request"));
        assert(x.Heartbeat(3,sid));
        assert(is(x.EffectStart(3,sid,2,x.window,target),"accepted"));
        assert(is(x.EffectRenew(150,sid,target,2,1),"renewed"));
        assert(is(x.EffectRenew(151,sid,target,2,1),"hold_cancelled")); // Replay never extends.
        assert(is(x.EffectStop(152,sid,target,1),"ok")); // Old stop cannot stop newer hold.
        assert(x.guard.Watering() || x.guard.Bubbling());
        // Timed request / status heartbeat cannot prolong a held lane.
        assert(x.Heartbeat(500,sid));
        assert(is(x.WebAction(500,sid,3,x.window,target,0,target==Target::WaterOnly?30000:0,nullptr,
                              target==Target::BubblesOnly?30000:0),"not_ready_or_busy"));
        assert(x.Heartbeat(749,sid));x.Tick(749,false);assert(x.guard.Watering() || x.guard.Bubbling());
        x.Tick(750,false);assert(!x.guard.Watering() && !x.guard.Bubbling());
        assert(is(x.EffectRenew(750,sid,target,2,2),"hold_cancelled"));
        assert(!x.guard.RenewWebEffect(751,Target::IgnitionOnly,600));
        assert(is(x.EffectStart(751,sid,4,x.window,Target::IgnitionOnly),"invalid_request"));
        assert(x.Heartbeat(949,sid));
        assert(is(x.EffectStart(949,sid,4,x.window,target),"not_ready_or_busy"));
        x.Tick(950,false);assert(x.Heartbeat(950,sid));
        assert(is(x.EffectStart(950,sid,5,x.window,target),"accepted"));
        // Expiry affects its lane, not a separately renewed effect.
        auto other=target==Target::WaterOnly?Target::BubblesOnly:Target::WaterOnly;
        assert(x.Heartbeat(950,sid));assert(is(x.EffectStart(950,sid,6,x.window,other),"accepted"));
        assert(is(x.EffectRenew(1400,sid,other,6,1),"renewed"));x.Tick(1550,false);
        assert(target==Target::WaterOnly?!x.guard.Watering()&&x.guard.Bubbling():x.guard.Watering()&&!x.guard.Bubbling());
    }
    for(int cause=0;cause<7;++cause) {
        ControlSessions x;auto sid=pair(x,100);
        assert(is(x.EffectStart(100,sid,1,x.window,Target::WaterOnly),"accepted"));
        assert(x.Heartbeat(100,sid));assert(is(x.EffectStart(100,sid,2,x.window,Target::BubblesOnly),"accepted"));
        if(cause==0)x.Stop(101);
        if(cause==1)x.Release(101,sid);
        if(cause==2)x.WifiLink(101,false);
        if(cause==3)x.Shutdown(101);
        x.Tick(cause==6?99:101,cause==4,cause==5);
        assert(!x.guard.Watering()&&!x.guard.Bubbling()&&!x.water_hold.id&&!x.bubbles_hold.id);
        assert(!is(x.EffectRenew(102,sid,Target::WaterOnly,1,1),"renewed"));
        assert(!is(x.EffectRenew(102,sid,Target::BubblesOnly,2,1),"renewed"));
    }
    std::cout << "PASS: held water/bubbles: 45 s concurrent continuity, per-lane release/expiry, nonce replay, late release/start, cooldown, no ignition lease, all stop/fault paths\n";
    std::cout << "PASS: web ownership/replay and held drive: 15 s continuous run, single start, release/renew reorder, 600 ms boundary, no heartbeat-only renewal, per-lane release, global cancellation and cooldown\n";
}
