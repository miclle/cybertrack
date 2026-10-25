#include "web_request.h"
#include <cassert>
#include <iostream>
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
    for (const auto text:bad) assert(!parse(text));
    std::cout << "PASS: actual web JSON parser, action schemas, integer/sequence bounds, missing/extra/duplicate fields\n";
}
