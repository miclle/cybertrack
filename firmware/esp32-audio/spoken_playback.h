#pragma once
#include "spoken_duration.h"
#include <cJSON.h>
#include <array>
#include <algorithm>
#include <cstring>
#include <string_view>
#include <utility>

// A whole-utterance playback whitelist, never an action parser for execution.
// Unknown syntax, truncation and effect limiting must remain audible.
struct SpokenPlayback {
    struct Step {
        const char* direction = "none";
        std::array<int, 3> ms{}; // move, water, bubbles; -1 means unspecified while parsing.
        unsigned specified = 0;
    };
    std::array<Step, 16> steps{};
    unsigned count = 0;
    const char* tool = "";
    int speed = 100;

    static void Trim(std::string_view& text) {
        while (!text.empty() && text.front() == ' ') text.remove_prefix(1);
        while (!text.empty() && text.back() == ' ') text.remove_suffix(1);
    }
    static bool Take(std::string_view& text, std::string_view prefix) {
        Trim(text);
        if (text.substr(0, prefix.size()) != prefix) return false;
        text.remove_prefix(prefix.size());
        return true;
    }
    static bool Number(const cJSON* object, const char* key, int value) {
        const auto* field = cJSON_GetObjectItemCaseSensitive(object, key);
        return cJSON_IsNumber(field) && field->valuedouble == value;
    }
    static bool Text(const cJSON* object, const char* key, const char* value) {
        const auto* field = cJSON_GetObjectItemCaseSensitive(object, key);
        return cJSON_IsString(field) && !std::strcmp(field->valuestring, value);
    }
    static bool DefaultSpeed(const cJSON* object) {
        const auto* value = cJSON_GetObjectItemCaseSensitive(object, "speed_percent");
        return !value || Number(object, "speed_percent", 100);
    }
    bool Parse(std::string_view text) {
        *this = {};
        if (text.empty() || text.size() > 1024) return false;
        Trim(text);
        for (auto prefix : {"速度调到", "调到", "减速到", "加速到", "掉到", "速度"}) {
            auto value = text;
            if (!Take(value, prefix)) continue;
            const bool percent = Take(value, "百分之");
            Trim(value);
            bool suffix = false;
            for (auto unit : {std::string_view("%"), std::string_view("％")})
                if (value.size() >= unit.size() && value.substr(value.size()-unit.size()) == unit) {
                    value.remove_suffix(unit.size()); suffix = true; break;
                }
            Trim(value);
            const int target = value == "一百" ? 100 : SpokenWhole(value);
            if (target < 60 || target > 100 || (std::string_view(prefix) == "掉到" && !percent && !suffix)) return false;
            tool = "set_speed"; speed = target; return true;
        }
        Take(text, "先");
        count = 1;
        bool beginning = true;
        while (true) {
            if (beginning) Take(text, "同时");
            beginning = false;
            auto& step = steps[count-1];
            int lane = -1;
            for (const auto& verb : {std::pair{"前进", "forward"}, {"后退", "backward"},
                                     {"左转", "left"}, {"右转", "right"}, {"喷水", "none"}, {"吹泡泡", "none"}}) {
                if (!Take(text, verb.first)) continue;
                lane = std::string_view(verb.first) == "喷水" ? 1 : std::string_view(verb.first) == "吹泡泡" ? 2 : 0;
                if (lane == 0) step.direction = verb.second;
                break;
            }
            if (lane < 0 || step.ms[lane]) return false;
            auto end = text.size();
            for (auto separator : {"，", ",", "同时", "并", "和", "然后", "再", "接着"})
                end = std::min(end, text.find(separator));
            auto duration = text.substr(0, end); Trim(duration);
            text.remove_prefix(end);
            if (duration.empty()) step.ms[lane] = -1;
            else {
                step.ms[lane] = SpokenEffectMs(duration);
                if (!step.ms[lane]) return false;
                step.specified |= 1u << lane;
            }
            Trim(text);
            if (text.empty()) break;
            if (!Take(text, "，")) Take(text, ",");
            if (Take(text, "然后") || Take(text, "再") || Take(text, "接着")) {
                if (count == steps.size()) return false;
                ++count; beginning = true;
            } else if (!(Take(text, "同时") || Take(text, "并") || Take(text, "和"))) return false;
        }
        for (unsigned i = 0; i < count; ++i) {
            auto& step = steps[i];
            int shared = 0;
            if (step.specified && !(step.specified & (step.specified-1)))
                for (int ms : step.ms) if (ms > 0) shared = ms;
            for (unsigned lane = 0; lane < 3; ++lane)
                if (step.ms[lane] < 0) step.ms[lane] = shared ? shared :
                    (lane == 0 && (!std::strcmp(step.direction, "left") || !std::strcmp(step.direction, "right"))) ? 880 : 1000;
        }
        const auto& first = steps[0];
        tool = count > 1 || (first.ms[2] && (first.ms[0] || first.ms[1])) ? "sequence" :
               first.ms[0] && first.ms[1] ? "move_and_water" : first.ms[0] ? "move" : first.ms[1] ? "water" : "bubbles";
        return true;
    }
    bool Request(const cJSON* args) const {
        if (!*tool || !cJSON_IsObject(args)) return false;
        const int size = cJSON_GetArraySize(args);
        if (!std::strcmp(tool, "set_speed")) return size == 1 && Number(args, "speed_percent", speed);
        const auto& first = steps[0];
        const bool has_speed = cJSON_GetObjectItemCaseSensitive(args, "speed_percent");
        if (!std::strcmp(tool, "move"))
            return size == 2+has_speed && Text(args, "direction", first.direction) && Number(args, "duration_ms", first.ms[0]) && DefaultSpeed(args);
        if (!std::strcmp(tool, "water") || !std::strcmp(tool, "bubbles"))
            return size == 1 && Number(args, "duration_ms", first.ms[first.ms[1] ? 1 : 2]);
        if (!std::strcmp(tool, "move_and_water"))
            return size == 3+has_speed && Text(args, "direction", first.direction) && Number(args, "move_duration_ms", first.ms[0]) &&
                   Number(args, "water_duration_ms", first.ms[1]) && DefaultSpeed(args);
        const auto* encoded = cJSON_GetObjectItemCaseSensitive(args, "steps_json");
        if (size != 1 || !cJSON_IsString(encoded) || std::strlen(encoded->valuestring) > 4096) return false;
        auto* plan = cJSON_ParseWithOpts(encoded->valuestring, nullptr, true);
        bool same = cJSON_IsArray(plan) && cJSON_GetArraySize(plan) == static_cast<int>(count);
        for (unsigned i = 0; same && i < count; ++i) {
            const auto* item = cJSON_GetArrayItem(plan, i);
            same = cJSON_IsObject(item) && cJSON_GetArraySize(item) == 5+(cJSON_GetObjectItemCaseSensitive(item, "speed_percent") != nullptr) &&
                   Text(item, "direction", steps[i].direction) && Number(item, "move_ms", steps[i].ms[0]) &&
                   Number(item, "water_ms", steps[i].ms[1]) && Number(item, "bubbles_ms", steps[i].ms[2]) &&
                   Number(item, "ignition_ms", 0) && DefaultSpeed(item);
        }
        cJSON_Delete(plan);
        return same;
    }
    bool Receipt(const cJSON* receipt) const {
        if (!Text(receipt, "operation", tool) || !Text(receipt, "result", "accepted") || !Text(receipt, "fault", "none")) return false;
        if (!std::strcmp(tool, "set_speed")) return Number(receipt, "move_speed_percent", speed);
        if (!std::strcmp(tool, "sequence") &&
            (!cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(receipt, "sequence_active")) || !Number(receipt, "sequence_step", 1) ||
             !Number(receipt, "sequence_steps", count) || !Text(receipt, "sequence_source", "voice") || !Text(receipt, "sequence_result", "running"))) return false;
        const char* durations[] = {"move_last_duration_ms", "water_last_duration_ms", "bubbles_last_duration_ms"};
        const char* sources[] = {"move_source", "water_source", "bubbles_source"};
        for (unsigned lane = 0; lane < 3; ++lane)
            if (steps[0].ms[lane] && (!Number(receipt, durations[lane], steps[0].ms[lane]) || !Text(receipt, sources[lane], "voice"))) return false;
        return !steps[0].ms[0] || (Text(receipt, "move_direction", steps[0].direction) && Number(receipt, "move_speed_percent", 100));
    }
};
