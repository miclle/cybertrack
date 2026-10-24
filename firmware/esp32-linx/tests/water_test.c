#include "water_mcp.h"
#include "cJSON.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static const char token_a[]="0123456789abcdef0123456789abcdef";
static const char token_b[]="abcdef0123456789abcdef0123456789";
static water_policy w;
static ct_controller c;
static ct_protocol p;
static uint64_t now;
static char reply[CT_RPC_REPLY_CAP];
static water_policy snapshot(void) { return w; }
static void stop(void) { water_stop(&w, now); }
static const char *request(const char *token, uint32_t duration) { return water_request(&w,now,token,duration); }
static ct_rpc_result frame(const char *json)
{
    water_callbacks cb={snapshot,stop,request};
    ct_rpc_delivery delivery={.session=p.session,.received_at_ms=now};
    return water_mcp_handle(&p,json,strlen(json),delivery,now,reply,sizeof(reply),cb);
}
static void initialize(void)
{
    w=(water_policy){0}; now=1; water_tick(&w,now,true,false);
    ct_init(&c,(ct_limits){0},0); ct_boot_complete(&c); ct_protocol_init(&p,&c,0); ct_protocol_open(&p,now);
    assert(frame("{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"test\",\"version\":\"1\"}}}}") == CT_RPC_RESPONSE);
    assert(p.initialized);
}
static void water_call(const char *id, const char *duration, const char *token)
{
    char json[1024];
    snprintf(json,sizeof(json),"{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\",\"id\":%s,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.water\",\"arguments\":{\"duration_ms\":%s,\"permit\":\"%s\"}}}}",id,duration,token);
    frame(json);
}
static unsigned allocations, fail_at;
static void *allocate(size_t n) { return ++allocations == fail_at ? NULL : malloc(n); }
int main(void)
{
    initialize(); water_call("2","5000",token_a); assert(!w.active && w.starts==0);
    assert(water_arm(&w,now,token_a));
    const char *invalid[]={"0","-1","5001","4294967296","5000.0","5e3","true","\"5000\"","null"};
    for(unsigned i=0;i<sizeof(invalid)/sizeof(*invalid);++i) { water_call("3",invalid[i],token_a); assert(!w.active && w.armed); }
    water_call("4","5000",token_b); assert(!w.active);
    water_call("5","5000",token_a); assert(w.active && w.used && !w.armed && w.ends_at==5001 && w.starts==1);
    assert(strstr(reply,"accepted"));
    water_call("5","5000",token_a); water_call("6","5000",token_a);
    assert(w.starts==1 && w.ends_at==5001 && strstr(reply,"permit_used"));
    frame("{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\",\"id\":7,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.get_status\",\"arguments\":{}}}}");
    assert(strstr(reply,"ACTIVE") && strstr(reply,"running"));
    water_tick(&w,5000,true,false); assert(w.active);
    water_tick(&w,5001,true,false); assert(!w.active && !w.armed);
    water_call("8","5000",token_a); assert(w.starts==1);
    assert(!water_arm(&w,5002,token_b));
    now=6002; water_tick(&w,now,true,false); assert(water_arm(&w,now,token_b));
    water_call("9","5000",token_a); assert(!w.active);
    water_call("10","5000",token_b); assert(w.active && w.starts==2);
    water_tick(&w,7000,true,true); assert(!w.active && !w.armed && w.stopped);
    water_tick(&w,7031,true,false); assert(!w.active && w.stopped);
    initialize(); assert(water_arm(&w,now,token_a)); now=30001; water_tick(&w,now,true,false);
    water_call("2","5000",token_a); assert(!w.active && w.starts==0);
    initialize(); assert(water_arm(&w,now,token_a)); water_call("2","5000",token_a);
    water_tick(&w,2,false,false); water_tick(&w,3,true,false); assert(!w.active && !w.armed);
    water_call("3","5000",token_a); assert(w.starts==1);
    initialize(); assert(water_arm(&w,now,token_a)); water_call("2","5000",token_a);
    frame("{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.stop\",\"arguments\":{}}}}");
    assert(!w.active && w.stopped);
    initialize(); assert(water_arm(&w,now,token_a));
    frame("{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\",\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.water\",\"arguments\":{\"duration_ms\":5000,\"permit\":\"0123456789abcdef0123456789abcdef\"}}}}");
    assert(!w.active);
    water_tick(&w,0,true,false); assert(w.clock_fault && !w.armed);
    initialize(); water_call("2","5000",token_a); assert(!w.active); /* reboot loses permit */
    /* Reply allocation failures must not leave an active output. */
    for(unsigned n=1;n<=80;++n) {
        initialize(); assert(water_arm(&w,now,token_a));
        allocations=0; fail_at=n;
        cJSON_Hooks hooks={allocate,free}; cJSON_InitHooks(&hooks);
        water_call("2","5000",token_a);
        if(allocations>=n) assert(!w.active);
        cJSON_InitHooks(NULL);
    }
    puts("PASS: fixed 5s bound, no unarmed/invalid/stale/replayed action, no extension, BOOT latch/release, cooldown, link loss, remote stop, reboot, allocation failures");
}
