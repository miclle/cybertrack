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
    std::cout << "PASS: web ownership/replay and held drive: 15 s continuous run, single start, release/renew reorder, 600 ms boundary, no heartbeat-only renewal, per-lane release, global cancellation and cooldown\n";
}
