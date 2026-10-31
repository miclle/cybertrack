// Host adapter for the firmware's status explanations. No board or IO code.
#include "status_facts.h"
#include "cJSON.h"
#include <iostream>
int main(int argc, char** argv) {
    std::string input;
    if (!std::getline(std::cin, input)) return 1;
    auto* status = cJSON_Parse(input.c_str());
    if (!cJSON_IsObject(status)) { cJSON_Delete(status); return 1; }
    auto get = cJSON_GetObjectItemCaseSensitive;
    auto str = [](const cJSON* value) { return cJSON_IsString(value) ? value->valuestring : ""; };
    if (argc == 2 && std::string_view(argv[1]) == "draft_read") {
        auto* draft = get(status,"show_draft");
        auto* value = get(draft,"active");
        if (!cJSON_IsBool(value)) { cJSON_Delete(status); return 1; }
        auto* fields = cJSON_CreateObject();
        cJSON_AddStringToObject(fields,"draft_status_facts",DraftReadFacts(cJSON_IsTrue(value)));
        char* raw = cJSON_PrintUnformatted(fields);
        if (!raw) { cJSON_Delete(fields); cJSON_Delete(status); return 1; }
        std::cout << raw << '\n';
        cJSON_free(raw); cJSON_Delete(fields); cJSON_Delete(status);
        return 0;
    }
    auto* outputs = get(status,"logical_outputs");
    bool active = false;
    for (auto key : {"left", "right", "water", "bubbles", "ignition"}) {
        auto* value = get(outputs,key);
        active |= cJSON_IsTrue(value) || (cJSON_IsNumber(value) && value->valuedouble != 0);
    }
    auto* recent = get(status,"recent_command");
    auto facts = StatusFacts(str(get(status,"fault")), cJSON_IsTrue(get(get(status,"proximity"),"forward_blocked")),
        cJSON_IsTrue(get(status,"sequence_active")), active,
        cJSON_IsTrue(get(recent,"valid")) ? str(get(recent,"result")) : "");
    if (argc == 2 && std::string_view(argv[1]) == "ct47") {
        auto* fields = cJSON_CreateObject();
        cJSON_AddStringToObject(fields, "status_facts", facts.c_str());
        cJSON_AddRawToObject(fields, "editing_capabilities", DraftEditingCapabilities);
        if (const char* guidance = FaultRecovery(str(get(status,"fault"))))
            cJSON_AddStringToObject(fields, "fault_recovery", guidance);
        char* json = cJSON_PrintUnformatted(fields);
        if (!json) { cJSON_Delete(fields); cJSON_Delete(status); return 1; }
        std::cout << json << '\n';
        cJSON_free(json);
        cJSON_Delete(fields);
    } else std::cout << facts << '\n';
    cJSON_Delete(status);
}
