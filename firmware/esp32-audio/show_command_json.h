#pragma once
#include "show_draft.h"
#include "status_facts.h"
#include "action_plan_json.h"
#include <cmath>
#include <cstdio>
#include <algorithm>

inline bool ShowInteger(const cJSON* value, int low, int high) {
    return cJSON_IsNumber(value) && std::isfinite(value->valuedouble) &&
        value->valuedouble >= low && value->valuedouble <= high && value->valuedouble == value->valueint;
}
inline bool ParseShowEdit(const cJSON* root, ShowDraft::Command& command) {
    if (!cJSON_IsObject(root) || cJSON_GetArraySize(root) != 4) return false;
    const auto edit=cJSON_GetObjectItemCaseSensitive(root,"edit"), revision=cJSON_GetObjectItemCaseSensitive(root,"revision"),
        step=cJSON_GetObjectItemCaseSensitive(root,"step"), steps=cJSON_GetObjectItemCaseSensitive(root,"steps_json");
    if (!cJSON_IsString(edit) || !cJSON_IsString(steps) || !ShowInteger(revision,0,INT_MAX) || !ShowInteger(step,0,16)) return false;
    command.revision=revision->valueint;command.step=step->valueint;
    if (!std::strcmp(edit->valuestring,"replace")) command.edit=ShowDraft::Replace;
    else if (!std::strcmp(edit->valuestring,"replace_step")) command.edit=ShowDraft::ReplaceStep;
    else if (!std::strcmp(edit->valuestring,"remove_step")) command.edit=ShowDraft::RemoveStep;
    else if (!std::strcmp(edit->valuestring,"cancel")) command.edit=ShowDraft::Cancel;
    else return false;
    const bool single = command.edit==ShowDraft::ReplaceStep || command.edit==ShowDraft::RemoveStep;
    if (single ? (!command.step || !command.revision) : command.step != 0) return false;
    if (command.edit==ShowDraft::Cancel || command.edit==ShowDraft::RemoveStep)
        return !steps->valuestring[0];
    return ParseActionPlan(steps->valuestring,command.plan) && ShowDraft::Valid(command.plan) &&
        (command.edit!=ShowDraft::ReplaceStep || command.plan.count==1);
}
inline std::string ShowDraftJson(const ShowDraft& draft, uint64_t now) {
    std::string result="{\"active\":";
    result+=draft.active?"true":"false";
    result+=",\"editing_capabilities\":";
    result+=DraftEditingCapabilities;
    result+=",\"revision\":"+std::to_string(draft.CurrentRevision())+",\"expires_in_ms\":"+std::to_string(draft.Remaining(now));
    result+=",\"source\":\"";result+=!draft.active?"none":draft.web_owner?"web":"voice";result+="\",\"steps\":[";
    uint64_t duration=0;
    for(unsigned i=0;draft.active && i<draft.plan.count;++i) {
        const auto& s=draft.plan.steps[i];char item[240];
        std::snprintf(item,sizeof(item),"%s{\"direction\":\"%s\",\"move_ms\":%d,\"water_ms\":0,\"bubbles_ms\":%d,\"ignition_ms\":0,\"speed_percent\":%d}",
            i?",":"",s.direction,s.move_ms,s.bubbles_ms,s.speed_percent);
        result+=item;duration+=std::max(s.move_ms,s.bubbles_ms)+(i?AudioActionGuard::CooldownMs:0);
    }
    result+="],\"nominal_duration_ms\":"+std::to_string(duration)+"}";
    return result;
}
