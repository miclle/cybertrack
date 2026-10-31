// Execute the prepared firmware's parameter gate without action callbacks or IO.
#include "action_plan_json.h"
#include "show_command_json.h"
#include <cJSON.h>
#include <cstring>
#include <iostream>
#include <string>

static const char* error = nullptr;
static bool stopped = false;
static void ReplyError(int, const char* message) { error = message; }
static void CyberTrackActionStop() { stopped = true; }
#define ESP_LOGI(...) ((void)0)
static void Validate(const std::string& tool_name, cJSON* tool_arguments) {
    [[maybe_unused]] const int id = 1;
    auto reject = [](const char* message) { ReplyError(1, message); };
#include "argument_checks.inc"
}
int main() {
    std::string input;
    if (!std::getline(std::cin,input)) return 1;
    auto* call = cJSON_ParseWithOpts(input.c_str(),nullptr,true);
    auto* name = cJSON_GetObjectItemCaseSensitive(call,"name");
    if (!cJSON_IsObject(call) || !cJSON_IsString(name)) { cJSON_Delete(call); return 1; }
    Validate(name->valuestring,cJSON_GetObjectItemCaseSensitive(call,"arguments"));
    auto* result = cJSON_CreateObject();
    cJSON_AddBoolToObject(result,"valid",error == nullptr);
    cJSON_AddStringToObject(result,"error",error ? error : "");
    cJSON_AddBoolToObject(result,"stop_requested",stopped);
    char* raw = cJSON_PrintUnformatted(result);
    if (!raw) { cJSON_Delete(result); cJSON_Delete(call); return 1; }
    std::cout << raw << '\n';
    cJSON_free(raw); cJSON_Delete(result); cJSON_Delete(call);
}
