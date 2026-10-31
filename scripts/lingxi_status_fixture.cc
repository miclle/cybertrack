// Host adapter for the firmware's status explanations. No board or IO code.
#include "status_facts.h"
#include "cJSON.h"
#include <iostream>
int main() {
    std::string input;
    if (!std::getline(std::cin, input)) return 1;
    auto* status = cJSON_Parse(input.c_str());
    if (!cJSON_IsObject(status)) { cJSON_Delete(status); return 1; }
    auto get = cJSON_GetObjectItemCaseSensitive;
    auto str = [](const cJSON* value) { return cJSON_IsString(value) ? value->valuestring : ""; };
    auto* outputs = get(status,"logical_outputs");
    bool active = false;
    for (auto key : {"left", "right", "water", "bubbles", "ignition"}) {
        auto* value = get(outputs,key);
        active |= cJSON_IsTrue(value) || (cJSON_IsNumber(value) && value->valuedouble != 0);
    }
    auto* recent = get(status,"recent_command");
    std::cout << StatusFacts(str(get(status,"fault")), cJSON_IsTrue(get(get(status,"proximity"),"forward_blocked")),
        cJSON_IsTrue(get(status,"sequence_active")), active,
        cJSON_IsTrue(get(recent,"valid")) ? str(get(recent,"result")) : "") << '\n';
    cJSON_Delete(status);
}
