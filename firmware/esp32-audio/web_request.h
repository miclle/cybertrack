#pragma once
#include "action_guard.h"
#include "cJSON.h"
#include <cmath>

struct WebCommand {
    AudioActionGuard::Target target = AudioActionGuard::Both;
    uint32_t sequence = 0, window = 0;
    uint32_t hold_id = 0, renewal = 0;
    int move_ms = 0, water_ms = 0, bubbles_ms = 0, ignition_ms = 0;
    const char* operation = nullptr;
    const char* direction = nullptr;
};
inline bool WebInteger(const cJSON* item, double low, double high) {
    return cJSON_IsNumber(item) && std::isfinite(item->valuedouble) &&
           item->valuedouble >= low && item->valuedouble <= high && std::floor(item->valuedouble) == item->valuedouble;
}
inline bool ParseWebCommand(const cJSON* root, WebCommand& cmd) {
    if (!cJSON_IsObject(root)) return false;
    auto get = [root](const char* key) { return cJSON_GetObjectItemCaseSensitive(root, key); };
    const auto op = get("operation"), seq = get("sequence"), window = get("window");
    if (!cJSON_IsString(op)) return false;
    const bool renew = !strcmp(op->valuestring, "drive_renew"), stop = !strcmp(op->valuestring, "drive_stop");
    if (renew || stop) {
        const auto id = get("hold_id"), nonce = get("renewal");
        if (cJSON_GetArraySize(root) != (renew ? 3 : 2) || !WebInteger(id, 1, UINT32_MAX) ||
            (renew && !WebInteger(nonce, 1, UINT32_MAX))) return false;
        cmd.operation = renew ? "drive_renew" : "drive_stop";
        cmd.hold_id = static_cast<uint32_t>(id->valuedouble);
        cmd.renewal = renew ? static_cast<uint32_t>(nonce->valuedouble) : 0;
        return true;
    }
    if (!WebInteger(seq, 1, UINT32_MAX) || !WebInteger(window, 1, UINT32_MAX)) return false;
    if (!strcmp(op->valuestring, "drive_start")) {
        const auto direction = get("direction"), water = get("water_duration_ms");
        int left, right;
        if (cJSON_GetArraySize(root) != (water ? 5 : 4) || !cJSON_IsString(direction) ||
            !AudioActionGuard::Direction(direction->valuestring, left, right) ||
            (water && !WebInteger(water, 1, 30000))) return false;
        cmd.operation = "drive_start"; cmd.direction = direction->valuestring;
        cmd.sequence = static_cast<uint32_t>(seq->valuedouble);
        cmd.window = static_cast<uint32_t>(window->valuedouble);
        cmd.water_ms = water ? water->valueint : 0;
        return true;
    }
    const bool move = !strcmp(op->valuestring, "move"), water = !strcmp(op->valuestring, "water");
    const bool bubbles = !strcmp(op->valuestring, "bubbles");
    const bool ignition = !strcmp(op->valuestring, "ignition");
    const bool both = !strcmp(op->valuestring, "move_and_water");
    if (!move && !water && !both && !bubbles && !ignition) return false;
    if (cJSON_GetArraySize(root) != (both ? 6 : (water || bubbles || ignition) ? 4 : 5)) return false;
    const auto duration = get("duration_ms"), direction = get("direction");
    const auto move_duration = both ? get("move_duration_ms") : duration;
    const auto water_duration = both ? get("water_duration_ms") : duration;
    int left, right;
    if ((move || both) && (!WebInteger(move_duration, 1, 3000) || !cJSON_IsString(direction) ||
                          !AudioActionGuard::Direction(direction->valuestring, left, right))) return false;
    if ((water || both) && !WebInteger(water_duration, 1, 30000)) return false;
    if (bubbles && !WebInteger(duration, 1, AudioActionGuard::BubblesMaxMs)) return false;
    if (ignition && !WebInteger(duration, 1, AudioActionGuard::IgnitionMaxMs)) return false;
    // Count plus all required unique keys rejects duplicates and unknown fields.
    cmd.sequence = static_cast<uint32_t>(seq->valuedouble);
    cmd.window = static_cast<uint32_t>(window->valuedouble);
    cmd.target = ignition ? AudioActionGuard::IgnitionOnly : bubbles ? AudioActionGuard::BubblesOnly : both ? AudioActionGuard::Both : move ? AudioActionGuard::MoveOnly : AudioActionGuard::WaterOnly;
    cmd.operation = ignition ? "ignition" : bubbles ? "bubbles" : both ? "move_and_water" : move ? "move" : "water";
    cmd.direction = (move || both) ? direction->valuestring : nullptr;
    cmd.move_ms = (move || both) ? move_duration->valueint : 0;
    cmd.water_ms = (water || both) ? water_duration->valueint : 0;
    cmd.ignition_ms = ignition ? duration->valueint : 0;
    cmd.bubbles_ms = bubbles ? duration->valueint : 0;
    return true;
}
