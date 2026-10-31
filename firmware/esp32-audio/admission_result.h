#pragma once
#include "cJSON.h"
#include <string>

// A rejected command is an observed tool outcome, not successful execution.
inline std::string CyberTrackAdmissionResult(const char* operation, const char* reason) {
    auto* receipt = cJSON_CreateObject();
    cJSON_AddStringToObject(receipt,"operation",operation);
    cJSON_AddStringToObject(receipt,"result","rejected");
    cJSON_AddStringToObject(receipt,"rejection_reason",reason);
    cJSON_AddBoolToObject(receipt,"physical_feedback",false);
    char* receipt_text = cJSON_PrintUnformatted(receipt);
    if (!receipt_text) { cJSON_Delete(receipt); return {}; }
    auto* envelope = cJSON_CreateObject();
    auto* content = cJSON_AddArrayToObject(envelope,"content");
    auto* text = cJSON_CreateObject();
    cJSON_AddStringToObject(text,"type","text");
    cJSON_AddStringToObject(text,"text",receipt_text);
    cJSON_AddItemToArray(content,text);
    cJSON_AddBoolToObject(envelope,"isError",false);
    char* wire = cJSON_PrintUnformatted(envelope);
    std::string result = wire ? wire : "";
    cJSON_free(wire);
    cJSON_Delete(envelope);
    cJSON_free(receipt_text);
    cJSON_Delete(receipt);
    return result;
}
