#include "action_guard.h"
#include <cassert>
#include <cstring>
#include <iostream>
using G = AudioActionGuard;
static bool is(const char* a, const char* b) { return !std::strcmp(a, b); }
int main() {
    for (const char* d : {"forward","backward","left","right"}) {
        G g; g.Tick(0,true,false);
        int m=g.Claim(0,1,G::MoveOnly), w=g.Claim(0,2,G::WaterOnly), extra=g.Claim(0,3,G::MoveOnly);
        assert(is(g.Move(0,m,3000,d),"accepted"));
        assert(g.left==((!strcmp(d,"left")||!strcmp(d,"backward"))?-60:60));
        assert(g.right==((!strcmp(d,"right")||!strcmp(d,"backward"))?-60:60));
        assert(is(g.Water(0,w,5000),"accepted")); // Cross-lane queued request survives.
        assert(is(g.Move(0,extra,1000,d),"cancelled_or_duplicate"));
        assert(g.Moving() && g.Watering() && g.Starts()==2);
        assert(!g.Claim(1,4,G::MoveOnly) && !g.Claim(1,5,G::WaterOnly));
        g.Tick(3000,true,false); assert(!g.Moving() && g.Watering());
        assert(G::Remaining(g.spray,3000)==2000);
        g.Tick(5000,true,false); assert(!g.Watering());
        assert(!g.Claim(5999,6,G::MoveOnly));
        g.Tick(6000,true,false); assert(g.Claim(6000,7,G::MoveOnly) && g.Claim(6000,8,G::WaterOnly));
    }
    for (bool water_first : {false,true}) {
        G g; g.Tick(0,true,false);
        if(water_first) {
            assert(is(g.Water(0,g.Claim(0,1,G::WaterOnly),3000),"accepted"));
            g.Tick(100,true,false);
            assert(is(g.Move(100,g.Claim(100,2,G::MoveOnly),1000,"forward"),"accepted"));
            g.Tick(1100,true,false); assert(!g.Moving() && g.Watering());
        } else {
            assert(is(g.Move(0,g.Claim(0,1,G::MoveOnly),3000,"forward"),"accepted"));
            g.Tick(100,true,false);
            assert(is(g.Water(100,g.Claim(100,2,G::WaterOnly),1000),"accepted"));
            g.Tick(1100,true,false); assert(g.Moving() && !g.Watering());
            g.Tick(2100,true,false); assert(g.Claim(2100,3,G::WaterOnly));
        }
    }
    for(int move_ms : {1,1000,3000}) for(int water_ms : {1,500,30000}) {
        G g;g.Tick(0,true,false);
        assert(is(g.MoveAndWater(0,g.Claim(0,1,G::Both),move_ms,water_ms,"right"),"accepted"));
        assert(g.Starts()==2 && g.Moving() && g.Watering());
        auto first=move_ms<water_ms?move_ms:water_ms;
        g.Tick(first,true,false);assert(g.Moving()==(move_ms>first));assert(g.Watering()==(water_ms>first));
        g.Tick(move_ms>water_ms?move_ms:water_ms,true,false);assert(!g.Moving()&&!g.Watering());
    }
    for(G::Target active : {G::MoveOnly,G::WaterOnly}) {
        G g;g.Tick(0,true,false);int both=g.Claim(0,1,G::Both);
        if(active==G::MoveOnly) g.Move(0,g.Claim(0,2,active),1000,"left");
        else g.Water(0,g.Claim(0,2,active),1000);
        assert(!g.Claim(1,3,G::Both));
        assert(is(g.MoveAndWater(1,both,1000,1000,"left"),"cancelled_or_duplicate"));
        assert(g.Starts()==1 && g.Moving()==(active==G::MoveOnly) && g.Watering()==(active==G::WaterOnly));
    }
    for(int mode=0;mode<4;++mode) {
        G g;g.Tick(0,true,false);
        g.MoveAndWater(0,g.Claim(0,1,G::Both),3000,30000,"forward");
        if(mode==0) g.Stop(100);
        else if(mode==3) {g.Tick(100,true,false);g.Tick(99,true,false);}
        else g.Tick(100,mode!=1,mode==2);
        assert(!g.Moving()&&!g.Watering());
        g.Tick(200,true,false);assert(!g.Moving()&&!g.Watering());
        assert(!g.Claim(200,2,G::Both));
    }
    for(int ms : {-1,0,3001,INT_MAX}) {
        G g;g.Tick(0,true,false);
        assert(!is(g.MoveAndWater(0,g.Claim(0,1,G::Both),ms,1000,"forward"),"accepted"));
        assert(g.Starts()==0&&!g.Moving()&&!g.Watering());
    }
    for(int ms : {-1,0,30001,INT_MAX}) {
        G g;g.Tick(0,true,false);
        assert(!is(g.MoveAndWater(0,g.Claim(0,1,G::Both),1000,ms,"forward"),"accepted"));assert(g.Starts()==0);
    }
    G g;g.Tick(0,true,false);
    int t=g.Claim(0,1,G::Both);
    assert(!g.Claim(0,1,G::WaterOnly)); // Shared RPC replay domain.
    assert(is(g.Move(0,t,1000,"forward"),"ticket_target_mismatch"));
    t=g.Claim(0,2,G::Both);g.Stop(1);
    assert(is(g.MoveAndWater(1,t,1000,1000,"forward"),"cancelled_or_duplicate"));
    t=g.Claim(2,3,G::Both);assert(is(g.MoveAndWater(5002,t,1000,1000,"forward"),"stale_request"));
    t=g.Claim(5003,4,G::Both);g.Tick(5004,false,false);g.Tick(5005,true,false);
    assert(is(g.MoveAndWater(5005,t,1000,1000,"forward"),"cancelled_or_duplicate"));
    assert(g.Claim(5005,4,G::Both));
    for(int i=5;i<132;++i) assert(g.Claim(5005,i,G::Both));
    assert(!g.Claim(5005,132,G::Both));
    std::cout << "PASS: independent concurrent timers/cooldowns, both arrival orders, atomic combined requests, same-lane refusal, replay/expiry/stop/BOOT/offline/clock\n";
}
