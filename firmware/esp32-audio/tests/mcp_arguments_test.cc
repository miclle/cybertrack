#include <cJSON.h>
#include "action_plan_json.h"
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
    for (const char* speed : {"60","70","80","100"}) {
        auto move=std::string(R"({"direction":"forward","duration_ms":5000,"speed_percent":)")+speed+"}";
        check("self.tank.move",move.c_str(),true);
        auto both=std::string(R"({"direction":"left","move_duration_ms":5000,"water_duration_ms":1000,"speed_percent":)")+speed+"}";
        check("self.tank.move_and_water",both.c_str(),true);
    }
    for (const char* speed : {"0","1","50","59","101","-1","1.5","true","null","\"50\"","50,\"speed_percent\":50"}) {
        auto move=std::string(R"({"direction":"left","duration_ms":1000,"speed_percent":)")+speed+"}";
        check("self.tank.move",move.c_str(),false);
        auto both=std::string(R"({"direction":"left","move_duration_ms":1000,"water_duration_ms":1000,"speed_percent":)")+speed+"}";
        check("self.tank.move_and_water",both.c_str(),false);
    }
    for(const char* speed:{"60","70","80","100"}) check("self.tank.set_speed",(std::string(R"({"speed_percent":)")+speed+"}").c_str(),true);
    for(const char* speed:{"0","1","50","59","101","60.5","true","null","\"60\"","60,\"speed_percent\":60","60,\"extra\":1"})
        check("self.tank.set_speed",(std::string(R"({"speed_percent":)")+speed+"}").c_str(),false);
    check("self.tank.set_speed","{}",false);check("self.tank.set_speed",nullptr,false);
    check("self.tank.adjust_speed",R"({"delta_percent":10})",true);
    check("self.tank.adjust_speed",R"({"delta_percent":-10})",true);
    for(const char* bad:{"{}","null",R"({"delta_percent":0})",R"({"delta_percent":20})",R"({"delta_percent":10.5})",R"({"delta_percent":"10"})",R"({"delta_percent":10,"delta_percent":10})"}) check("self.tank.adjust_speed",bad,false);
    const std::string step = R"({"direction":"left","move_ms":5000,"water_ms":5000,"bubbles_ms":0,"ignition_ms":0})";
    auto check_plan = [&](const std::string& text, bool valid) {
        cJSON* obj = cJSON_CreateObject();
        cJSON_AddStringToObject(obj, "steps_json", text.c_str());
        char* json = cJSON_PrintUnformatted(obj);
        check("self.tank.sequence", json, valid);
        cJSON_free(json); cJSON_Delete(obj);
    };
    check_plan(R"([{"direction":"left","move_ms":1000,"water_ms":0,"bubbles_ms":0,"ignition_ms":0,"speed_percent":60}])",true);
    for(const char* speed:{"0","101","1.5","true","50,\"speed_percent\":50"})
        check_plan(std::string(R"([{"direction":"left","move_ms":1000,"water_ms":0,"bubbles_ms":0,"ignition_ms":0,"speed_percent":)")+speed+"}]",false);
    check_plan("[" + step + "]", true);
    std::string many = "[" + step;
    for (int i=1; i<16; ++i) many += "," + step;
    check_plan(many + "]", true);
    check_plan(many + "," + step + "]", false);
    for (const char* invalid : {"[]", "{}", "null", "[{}]", "[false]", "[1]", "[", "[null]"}) check_plan(invalid, false);
    for (auto pair : {std::pair<const char*,const char*>{"5000", "2147483648"},
                     {"5000", "-1"}, {"5000", "0.5"}, {"5000", "true"}, {"left", "none"}, {"left", "spin"},
                     {"left", "left\\u0000junk"}, {"move_ms", "water_ms"}, {"ignition_ms", "unknown"}}) {
        auto bad = step; bad.replace(bad.find(pair.first), std::strlen(pair.first), pair.second);
        check_plan("[" + bad + "]", false);
    }
    check_plan("[" + step + "] trailing", false);
    check_plan(R"([{"direction":"none","move_ms":0,"water_ms":30001,"bubbles_ms":0,"ignition_ms":0}])", false);
    check_plan(R"([{"direction":"none","move_ms":0,"water_ms":0,"bubbles_ms":0,"ignition_ms":5001}])", false);
    check_plan(R"([{"direction":"none","move_ms":0,"water_ms":0,"bubbles_ms":0,"ignition_ms":0}])", false);
    check("self.tank.sequence", R"({"steps_json":[]})", false);
    check("self.tank.sequence", R"({"steps_json":"[]","_ct_ticket":1})", false);
    check("self.tank.sequence", nullptr, false);

    for(const char* tool : {"self.tank.bubbles","self.tank.ignition","self.tank.frenzy"}) {
        for(const char* j : {R"({"duration_ms":1})", R"({"duration_ms":1000})", R"({"duration_ms":5000})"}) check(tool,j,true);
        for(const char* j : {"{}","[]","null",R"({"duration_ms":0})",R"({"duration_ms":-1})",
            R"({"duration_ms":30001})",R"({"duration_ms":0.5})",R"({"duration_ms":true})",R"({"duration_ms":"1000"})",
            R"({"duration_ms":1,"_ct_ticket":1})",R"({"duration_ms":1,"duration_ms":1})"}) check(tool,j,false);
        check(tool,nullptr,false);
    }
    check("self.tank.bubbles",R"({"duration_ms":30000})",true);
    check("self.tank.frenzy",R"({"duration_ms":30000})",true);
    check("self.tank.ignition",R"({"duration_ms":5001})",false);
    for (const char* d : {"forward","backward","left","right"})
        for (int ms : {1,500,1000,3000,5000,60000,2147483647}) {
            auto j = std::string("{\"direction\":\"") + d + "\",\"duration_ms\":" + std::to_string(ms) + "}";
            check("self.tank.move",j.c_str(),true);
        }
    for (const char* j : {"{}", "null", "[]", "1", "{\"direction\":\"forward\"}",
         "{\"direction\":\"forward\",\"duration_ms\":0}", "{\"direction\":\"forward\",\"duration_ms\":2147483648}",
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
        "{\"direction\":\"forward\",\"move_duration_ms\":2147483648,\"water_duration_ms\":1000}",
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
