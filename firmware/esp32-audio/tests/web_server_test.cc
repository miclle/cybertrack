#include "web_server_stubs.h"
#include "web_server.h"
#include <cassert>
#include <iostream>
static unsigned calls=0,acquires=0;
static bool busy=false;
static std::string response="{\"result\":\"ok\"}";
static std::string last_operation;
uint32_t CyberTrackWebAcquire() { ++acquires; return busy?0:acquires; }
void CyberTrackWifiLink(bool) {}
std::string CyberTrackWebCall(uint32_t,const char* operation,const WebCommand*) {
    ++calls; last_operation=operation; return response;
}
// Exercise the actual HTTP handlers; only ESP transport/display calls are stubbed.
#include "../web_server.cc"
static httpd_req_t req(const char* path,const std::string& body) {
    httpd_req_t r; r.uri=path; r.body=body; r.content_len=body.size();
    r.headers={{"Host","192.168.1.123:8080"},{"Origin","http://192.168.1.123:8080"},
               {"X-CyberTrack-Client","1"},{"Content-Type","application/json"}};
    return r;
}
int main() {
    InitializeCyberTrackWeb(); ip_event_got_ip_t event; GotIp(nullptr,IP_EVENT,0,&event);
    auto display=Board::GetInstance().GetDisplay();
    assert(display->address=="192.168.1.123:8080");
    display->SetChatMessage("assistant", "Hello");
    LostIp(nullptr,WIFI_EVENT,WIFI_EVENT_STA_DISCONNECTED,nullptr);
    assert(display->address.empty() && display->text=="Hello");
    event.ip_info.ip.addr=0x0a000002;
    GotIp(nullptr,IP_EVENT,IP_EVENT_STA_GOT_IP,&event);
    assert(display->address=="10.0.0.2:8080" && display->text=="Hello");
    LostIp(nullptr,IP_EVENT,IP_EVENT_STA_LOST_IP,nullptr);
    assert(display->address.empty());
    event.ip_info.ip.addr=0xc0a8017b;
    GotIp(nullptr,IP_EVENT,IP_EVENT_STA_GOT_IP,&event);
    auto r=req("/",""); r.method=HTTP_GET; assert(Page(&r)==ESP_OK);
    assert(r.sent=="TEST_PAGE");
    assert(r.response_headers["Content-Security-Policy"].find("frame-ancestors 'none'")!=std::string::npos);
    auto login=[&](){ test_time+=1000000; return req("/api/pair","{}"); };
    r=login(); r.headers["Origin"]="http://evil.example"; assert(Pair(&r)==ESP_FAIL); assert(acquires==0);
    r=login(); r.headers["Host"]="evil.example:8080"; assert(Pair(&r)==ESP_FAIL); assert(acquires==0);
    r=login(); r.headers.erase("X-CyberTrack-Client"); assert(Pair(&r)==ESP_FAIL); assert(acquires==0);
    r=login(); r.body=R"({"code":"00000000"})"; r.content_len=r.body.size(); assert(Pair(&r)==ESP_FAIL); assert(acquires==0);
    r=req("/api/pair","{}"); assert(Pair(&r)==ESP_FAIL); assert(r.status=="429 Too Many Requests");
    busy=true; r=login(); assert(Pair(&r)==ESP_FAIL); assert(!session); busy=false;
    r=login(); assert(Pair(&r)==ESP_OK); assert(session && bearer[0]);
    std::string token=bearer;
    auto api=[&](const char* path,const std::string& body="{}") { auto a=req(path,body); a.headers["X-CyberTrack-Token"]=token; return a; };
    r=api("/api/state"); r.headers["X-CyberTrack-Token"]="bad"; assert(Api(&r)==ESP_FAIL); assert(calls==0);
    r=api("/api/state"); assert(Api(&r)==ESP_OK); assert(calls==1 && last_operation=="get_status");
    r=api("/api/action",R"({"operation":"water","sequence":1,"window":1,"duration_ms":1000})");
    assert(Api(&r)==ESP_OK); assert(calls==2 && last_operation=="water");
    r=api("/api/action",R"({"operation":"drive_start","sequence":2,"window":1,"direction":"forward"})");
    assert(Api(&r)==ESP_OK && last_operation=="drive_start");
    r=api("/api/action",R"({"operation":"drive_renew","hold_id":2,"renewal":1})");
    assert(Api(&r)==ESP_OK && last_operation=="drive_renew");
    r=api("/api/action",R"({"operation":"drive_stop","hold_id":2})");
    assert(Api(&r)==ESP_OK && last_operation=="drive_stop");
    for(const std::string kind:{"water","bubbles"}) {
        for(const std::string action:{"start","renew","stop"}) {
            const auto op=kind+"_"+action;
            const auto args=action=="start"?"\"sequence\":3,\"window\":1":action=="renew"?"\"hold_id\":3,\"renewal\":1":"\"hold_id\":3";
            r=api("/api/action","{\"operation\":\""+op+"\","+args+"}");
            assert(Api(&r)==ESP_OK && last_operation==op);
        }
    }
    unsigned before=calls;
    for(const auto bad:{"[]","null","{", "{} {}", "{\"extra\":0}"}) {
        r=api("/api/stop",bad); assert(Api(&r)==ESP_FAIL); assert(calls==before);
    }
    r=api("/api/state",std::string(385,' ')); assert(Api(&r)==ESP_FAIL); assert(calls==before);
    r=api("/api/state"); r.chunk=-1; assert(Api(&r)==ESP_FAIL); assert(calls==before);
    r=api("/api/state"); r.headers["Content-Type"]="text/plain"; assert(Api(&r)==ESP_FAIL); assert(calls==before);
    r=api("/api/stop"); assert(Api(&r)==ESP_OK); assert(last_operation=="stop");
    r=api("/api/state"); r.send_fail=true; assert(Api(&r)==ESP_FAIL); assert(last_operation=="release");
    r=api("/api/release"); assert(Api(&r)==ESP_OK); assert(!session && !bearer[0]);
    r=api("/api/state"); assert(Api(&r)==ESP_FAIL);
    r=login(); assert(Pair(&r)==ESP_OK); assert(token!=bearer); token=bearer;
    response="{\"result\":\"session_expired\"}";
    r=api("/api/state"); assert(Api(&r)==ESP_OK); assert(r.status=="401 Unauthorized" && !session && !bearer[0]);
    std::cout << "PASS: actual HTTP handlers, Host/Origin/auth, no-PIN acquire throttle/ownership, token rotation/revocation, bounded/partial bodies, invalid JSON, send failure release\n";
}
