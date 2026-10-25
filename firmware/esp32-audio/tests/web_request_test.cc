#include "web_request.h"
#include <cassert>
#include <iostream>
#include <string>
static bool parse(const char* text) {
    auto root=cJSON_Parse(text); WebCommand command;
    bool result=ParseWebCommand(root,command); cJSON_Delete(root); return result;
}
int main() {
    assert(parse(R"({"operation":"drive_start","sequence":1,"window":1,"direction":"forward"})"));
    assert(parse(R"({"operation":"drive_start","sequence":1,"window":1,"direction":"left","water_duration_ms":30000})"));
    assert(parse(R"({"operation":"drive_renew","hold_id":1,"renewal":1})"));
    assert(parse(R"({"operation":"drive_stop","hold_id":1})"));
    assert(parse(R"({"operation":"move","sequence":1,"window":1,"direction":"left","duration_ms":1})"));
    assert(parse(R"({"operation":"water","sequence":4294967295,"window":1,"duration_ms":30000})"));
    assert(parse(R"({"operation":"move_and_water","sequence":1,"window":1,"direction":"backward","move_duration_ms":3000,"water_duration_ms":30000})"));
    for(const char* op : {"bubbles", "ignition"}) {
        const auto prefix=std::string("{\"operation\":\"")+op+"\",\"sequence\":1,\"window\":1,\"duration_ms\":";
        for(const char* ms : {"1", "1000", "5000"}) {
            const auto json=prefix+ms+"}";
            auto root=cJSON_Parse(json.c_str()); WebCommand cmd; assert(ParseWebCommand(root,cmd));
            assert(cmd.target==(!strcmp(op,"bubbles")?AudioActionGuard::BubblesOnly:AudioActionGuard::IgnitionOnly));
            assert((!strcmp(op,"bubbles")?cmd.bubbles_ms:cmd.ignition_ms)==atoi(ms));
            cJSON_Delete(root);
        }
        for(const char* ms : {"0","-1","30001","1.5","true","\"1000\"","1,\"duration_ms\":1","1,\"extra\":0"})
            assert(!parse((prefix+ms+"}").c_str()));
    }
    for(const std::string kind:{"water","bubbles"}) {
        for(const std::string action:{"start","renew","stop"}) {
            const auto prefix=std::string("{\"operation\":\"")+kind+"_"+action+"\",";
            const auto args=action=="start"?"\"sequence\":1,\"window\":1":action=="renew"?"\"hold_id\":1,\"renewal\":1":"\"hold_id\":1";
            auto json=prefix+args+"}";auto root=cJSON_Parse(json.c_str());WebCommand cmd;
            assert(ParseWebCommand(root,cmd));assert(cmd.target==(kind=="water"?AudioActionGuard::WaterOnly:AudioActionGuard::BubblesOnly));
            assert(std::string(cmd.operation)==kind+"_"+action);cJSON_Delete(root);
            assert(!parse((prefix+args+",\"extra\":1}").c_str()));
            assert(!parse((prefix+"\"hold_id\":0}").c_str()));
        }
    }
    assert(!parse(R"({"operation":"ignition_start","sequence":1,"window":1})"));
    assert(!parse(R"({"operation":"water_start","sequence":1,"sequence":1})"));
    assert(!parse(R"({"operation":"water_renew","hold_id":1,"renewal":1.5})"));
    assert(!parse(R"({"operation":"bubbles_stop","hold_id":1,"hold_id":2})"));
    for (const char* ms : {"1", "5000", "10000", "30000"}) {
        const auto json = std::string(R"({"operation":"frenzy","sequence":1,"window":1,"duration_ms":)") + ms + "}";
        auto root = cJSON_Parse(json.c_str()); WebCommand cmd;
        assert(ParseWebCommand(root, cmd) && cmd.frenzy_ms == atoi(ms));
        assert(std::string(cmd.operation) == "frenzy"); cJSON_Delete(root);
    }
    for (const char* ms : {"0", "-1", "30001", "1.5", "true", "\"5000\"", "5000,\"duration_ms\":5000", "5000,\"extra\":1"})
        assert(!parse((std::string(R"({"operation":"frenzy","sequence":1,"window":1,"duration_ms":)") + ms + "}").c_str()));
    const char* bad[]={
        "null", "[]", "{}",
        R"({"operation":"drive_start","sequence":1,"window":1,"direction":"left","duration_ms":1000})",
        R"({"operation":"drive_start","sequence":1,"window":1,"direction":"left","water_duration_ms":0})",
        R"({"operation":"drive_renew","hold_id":1,"renewal":0})",
        R"({"operation":"drive_renew","hold_id":1,"renewal":1,"direction":"backward"})",
        R"({"operation":"drive_stop","hold_id":0})",
        R"({"operation":"drive_stop","hold_id":1,"hold_id":2})",
        R"({"operation":"gpio","sequence":1,"window":1,"duration_ms":1})",
        R"({"operation":"water","sequence":0,"window":1,"duration_ms":1})",
        R"({"operation":"water","sequence":4294967296,"window":1,"duration_ms":1})",
        R"({"operation":"water","sequence":1.1,"window":1,"duration_ms":1})",
        R"({"operation":"water","sequence":1,"window":0,"duration_ms":1})",
        R"({"operation":"water","sequence":1,"window":1,"duration_ms":"1"})",
        R"({"operation":"water","sequence":1,"window":1,"duration_ms":0})",
        R"({"operation":"water","sequence":1,"window":1,"duration_ms":30001})",
        R"({"operation":"water","sequence":1,"window":1,"duration_ms":1.5})",
        R"({"operation":"water","sequence":1,"window":1,"duration_ms":1e100})",
        R"({"operation":"water","sequence":1,"window":1,"duration_ms":1,"extra":0})",
        R"({"operation":"water","sequence":1,"window":1,"window":2,"duration_ms":1})",
        R"({"operation":"water","sequence":1,"sequence":2,"duration_ms":1})",
        R"({"operation":"move","sequence":1,"window":1,"direction":"up","duration_ms":1})",
        R"({"operation":"move","sequence":1,"window":1,"direction":"forward","duration_ms":3001})",
        R"({"operation":"move_and_water","sequence":1,"window":1,"direction":"left","move_duration_ms":1})",
        R"({"operation":"move_and_water","sequence":1,"window":1,"direction":"left","move_duration_ms":1,"water_duration_ms":-1})"
    };
    assert(parse(R"({"operation":"bubbles","sequence":1,"window":1,"duration_ms":30000})"));
    assert(!parse(R"({"operation":"ignition","sequence":1,"window":1,"duration_ms":5001})"));
    for (const auto text:bad) assert(!parse(text));
    std::cout << "PASS: actual web JSON parser, action schemas, integer/sequence bounds, missing/extra/duplicate fields\n";
}
