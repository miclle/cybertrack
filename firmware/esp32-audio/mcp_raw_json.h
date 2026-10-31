#pragma once
#include <cJSON.h>
#include <string_view>
#include <cstring>

// cJSON strings cannot retain an embedded zero. Check the original frame
// before a robot RPC can interpret a truncated enum as a valid command.
inline bool McpJsonContainsZero(std::string_view raw) {
    for (size_t i=0;i<raw.size();++i) {
        if (!raw[i]) return true;
        if (raw[i]!='\\' || i+1==raw.size()) continue;
        if (raw[i+1]=='u' && raw.substr(i+2,4)=="0000") return true;
        ++i; // A quoted backslash is not a Unicode escape.
    }
    return false;
}
inline bool RejectZeroInRobotMcp(std::string_view raw, const cJSON* root, int& id) {
    const auto* type=cJSON_GetObjectItemCaseSensitive(root,"type");
    if (!McpJsonContainsZero(raw)) return false;
    if (type && (!cJSON_IsString(type) || std::strcmp(type->valuestring,"mcp"))) return false;
    const auto* payload=type ? cJSON_GetObjectItemCaseSensitive(root,"payload") : root;
    const auto* method=cJSON_GetObjectItemCaseSensitive(payload,"method");
    const auto* rpc=cJSON_GetObjectItemCaseSensitive(payload,"id");
    const auto* params=cJSON_GetObjectItemCaseSensitive(payload,"params");
    const auto* name=cJSON_GetObjectItemCaseSensitive(params,"name");
    if (!cJSON_IsString(method) || std::strcmp(method->valuestring,"tools/call") || !cJSON_IsString(name) ||
        (std::strncmp(name->valuestring,"self.tank.",10) && std::strncmp(name->valuestring,"self_tank_",10)) ||
        !cJSON_IsNumber(rpc)) return false;
    // Match the SDK's numeric-ID conversion. Requiring an integer here would
    // let a fractional/out-of-range ID bypass the raw guard and reach the SDK.
    id=rpc->valueint;
    return true;
}
