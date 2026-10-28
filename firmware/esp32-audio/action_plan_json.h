#pragma once
#include "action_plan.h"
#include <cJSON.h>
#include <string>

// JSON is a string property because the upstream MCP schema supports scalar properties.
// Require all five fields, reject duplicates/unknowns and validate the whole plan first.
inline bool ParseActionPlan(const std::string& text, ActionPlan& plan) {
    plan = {};
    if (text.empty() || text.size() > 4096 || text.find('\0') != std::string::npos ||
        text.find("\\u0000") != std::string::npos) return false;
    cJSON* root = cJSON_ParseWithOpts(text.c_str(), nullptr, true);
    bool valid = cJSON_IsArray(root);
    const int count = valid ? cJSON_GetArraySize(root) : 0;
    valid = valid && count > 0 && count <= static_cast<int>(ActionPlan::MaxSteps);
    for (int i = 0; valid && i < count; ++i) {
        const cJSON* item = cJSON_GetArrayItem(root, i);
        auto& step = plan.steps[i];
        const auto* direction = cJSON_GetObjectItemCaseSensitive(item, "direction");
        valid = cJSON_IsObject(item) && cJSON_GetArraySize(item) == 5 && cJSON_IsString(direction);
        bool known = false;
        if (valid) for (const char* name : {"none", "forward", "backward", "left", "right"}) {
            if (!std::strcmp(direction->valuestring, name)) { step.direction = name; known = true; break; }
        }
        valid = valid && known;
        const char* keys[] = {"move_ms", "water_ms", "bubbles_ms", "ignition_ms"};
        int* values[] = {&step.move_ms, &step.water_ms, &step.bubbles_ms, &step.ignition_ms};
        const int limits[] = {INT_MAX, 30000, 30000, 5000};
        for (unsigned j = 0; valid && j < 4; ++j) {
            const auto* v = cJSON_GetObjectItemCaseSensitive(item, keys[j]);
            valid = cJSON_IsNumber(v) && v->valuedouble >= 0 && v->valuedouble <= limits[j] &&
                v->valuedouble == v->valueint;
            if (valid) *values[j] = v->valueint;
        }
        valid = valid && step.Valid();
    }
    cJSON_Delete(root);
    if (valid) plan.count = count; else plan = {};
    return valid;
}
