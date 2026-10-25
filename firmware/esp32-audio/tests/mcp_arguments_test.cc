#include <cJSON.h>
#include <cassert>
#include <cstring>
#include <string>
#include <iostream>
static bool rejected, stopped;
static void ReplyError(int, const char*) { rejected = true; }
static void CyberTrackActionStop() { stopped = true; }
#define ESP_LOGI(...) ((void)0)
static void validate(const std::string& tool_name, cJSON* tool_arguments) {
    [[maybe_unused]] const int id = 1;
#include "argument_checks.inc"
}
static void check(const char* tool, const char* json, bool valid) {
    rejected = stopped = false;
    cJSON* args = json ? cJSON_Parse(json) : nullptr;
    if (json) assert(args);
    validate(tool, args);
    assert(rejected != valid);
    assert(stopped == (valid && !strcmp(tool,"self.tank.stop")));
    cJSON_Delete(args);
}
int main() {
    for(const char* tool : {"self.tank.bubbles","self.tank.ignition"}) {
        for(const char* j : {R"({"duration_ms":1})", R"({"duration_ms":1000})", R"({"duration_ms":5000})"}) check(tool,j,true);
        for(const char* j : {"{}","[]","null",R"({"duration_ms":0})",R"({"duration_ms":-1})",
            R"({"duration_ms":30001})",R"({"duration_ms":0.5})",R"({"duration_ms":true})",R"({"duration_ms":"1000"})",
            R"({"duration_ms":1,"_ct_ticket":1})",R"({"duration_ms":1,"duration_ms":1})"}) check(tool,j,false);
        check(tool,nullptr,false);
    }
    check("self.tank.bubbles",R"({"duration_ms":30000})",true);
    check("self.tank.ignition",R"({"duration_ms":5001})",false);
    for (const char* d : {"forward","backward","left","right"})
        for (int ms : {1,500,1000,3000}) {
            auto j = std::string("{\"direction\":\"") + d + "\",\"duration_ms\":" + std::to_string(ms) + "}";
            check("self.tank.move",j.c_str(),true);
        }
    for (const char* j : {"{}", "null", "[]", "1", "{\"direction\":\"forward\"}",
         "{\"direction\":\"forward\",\"duration_ms\":0}", "{\"direction\":\"forward\",\"duration_ms\":3001}",
         "{\"direction\":\"forward\",\"duration_ms\":1.5}", "{\"direction\":\"forward\",\"duration_ms\":true}",
         "{\"direction\":\"forward\",\"duration_ms\":\"1000\"}", "{\"direction\":false,\"duration_ms\":1000}",
         "{\"direction\":\"spin\",\"duration_ms\":1000}", "{\"direction\":\"forward\",\"duration_ms\":1000,\"speed\":100}",
         "{\"direction\":\"forward\",\"duration_ms\":1000,\"_ct_ticket\":1}",
         "{\"duration_ms\":1000,\"duration_ms\":1000}", "{\"direction\":\"forward\",\"direction\":\"left\"}"})
        check("self.tank.move",j,false);
    check("self.tank.move",nullptr,false);
    for (int ms : {1,1000,30000}) {
        auto j=std::string("{\"duration_ms\":")+std::to_string(ms)+"}";
        check("self.tank.water",j.c_str(),true);
    }
    for(const char* j : {"{}","[]","null","{\"duration_ms\":30001}","{\"duration_ms\":-1}",
        "{\"duration_ms\":0.5}","{\"duration_ms\":\"1000\"}","{\"duration_ms\":1000,\"direction\":\"forward\"}"})
        check("self.tank.water",j,false);
    for (const char* d : {"forward","backward","left","right"}) {
        auto j=std::string("{\"direction\":\"")+d+"\",\"move_duration_ms\":3000,\"water_duration_ms\":30000}";
        check("self.tank.move_and_water",j.c_str(),true);
    }
    for(const char* j : {"{}","null","[]",
        "{\"direction\":\"forward\",\"move_duration_ms\":1000}",
        "{\"direction\":\"forward\",\"move_duration_ms\":3001,\"water_duration_ms\":1000}",
        "{\"direction\":\"forward\",\"move_duration_ms\":1000,\"water_duration_ms\":30001}",
        "{\"direction\":\"forward\",\"move_duration_ms\":0,\"water_duration_ms\":1000}",
        "{\"direction\":\"forward\",\"move_duration_ms\":1000,\"water_duration_ms\":-1}",
        "{\"direction\":\"forward\",\"move_duration_ms\":true,\"water_duration_ms\":1000}",
        "{\"direction\":\"forward\",\"move_duration_ms\":1000,\"water_duration_ms\":1.5}",
        "{\"direction\":\"spin\",\"move_duration_ms\":1000,\"water_duration_ms\":1000}",
        "{\"direction\":\"forward\",\"move_duration_ms\":1000,\"water_duration_ms\":1000,\"_ct_ticket\":1}",
        "{\"direction\":\"forward\",\"move_duration_ms\":1000,\"move_duration_ms\":1000}"})
        check("self.tank.move_and_water",j,false);
    check("self.tank.move_and_water",nullptr,false);
    for(const char* tool : {"self.tank.stop","self.tank.get_status"}) {
        check(tool,"{}",true); check(tool,nullptr,true);
        for(const char* j : {"[]","null","{\"duration_ms\":1000}"}) check(tool,j,false);
    }
    std::cout << "PASS: generated MCP argument checks, directions/ranges/types, missing/extra/duplicate keys, injected ticket, stop/status isolation\n";
}
