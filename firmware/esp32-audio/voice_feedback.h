#pragma once
#include "cJSON.h"
#include <mutex>
#include <string_view>
#include <cstdint>

// A match only affects playback. This class has no command or output callbacks.
class VoiceFeedback {
    struct Command {
        std::string_view phrase, tool, direction;
        int duration;
    };
    static constexpr Command commands[] = {
        {"前进","move","forward",1000}, {"后退","move","backward",1000},
        {"左转","move","left",880}, {"右转","move","right",880},
        {"喷水","water","",1000}, {"吹泡泡","bubbles","",1000},
        {"全速","set_speed","",0}, {"最快","set_speed","",0},
        {"最大速度","set_speed","",0}, {"调到全速","set_speed","",0},
        {"停止","stop","",0}, {"停下","stop","",0}, {"全部停止","stop","",0},
        {"停止行走","stop","",0}, {"停止喷水","stop","",0}, {"停止泡泡","stop","",0},
        {"停止狂暴模式","stop","",0}, {"所有动作都停下来","stop","",0},
        {"取消序列","stop","",0}, {"取消正在执行的表演","stop","",0}
    };
    std::mutex mutex_;
    uint64_t generation_ = 0;
    const Command* expected_ = nullptr;
    const Command* pending_ = nullptr;
    bool accepted_ = false, muted_ = false;

public:
    void Input(std::string_view text) {
        std::lock_guard<std::mutex> lock(mutex_);
        ++generation_;
        accepted_ = muted_ = false;
        expected_ = nullptr;
        for (std::string_view suffix : {"。", "！", "!"}) {
            if (text.size() >= suffix.size() && text.substr(text.size()-suffix.size()) == suffix) {
                text.remove_suffix(suffix.size());
                break;
            }
        }
        for (const auto& command : commands)
            if (command.phrase == text) expected_ = &command;
    }
    uint64_t BeginCall(std::string_view tool, const cJSON* args) {
        std::lock_guard<std::mutex> lock(mutex_);
        ++generation_;
        const auto* command = expected_;
        expected_ = nullptr;
        accepted_ = muted_ = false;
        constexpr std::string_view prefix = "self.tank.";
        if (!command || tool.substr(0,prefix.size()) != prefix || tool.substr(prefix.size()) != command->tool)
            return 0;
        if (command->tool == "set_speed") {
            const auto* speed = cJSON_GetObjectItemCaseSensitive(args,"speed_percent");
            if (cJSON_GetArraySize(args) != 1 || !cJSON_IsNumber(speed) || speed->valuedouble != 100)
                return 0;
        }
        if (command->duration) {
            const auto* duration = cJSON_GetObjectItemCaseSensitive(args,"duration_ms");
            if (!cJSON_IsNumber(duration) || duration->valuedouble != command->duration) return 0;
        }
        if (!command->direction.empty()) {
            const auto* dir = cJSON_GetObjectItemCaseSensitive(args,"direction");
            const auto* speed = cJSON_GetObjectItemCaseSensitive(args,"speed_percent");
            if (!cJSON_IsString(dir) || command->direction != dir->valuestring ||
                (speed && (!cJSON_IsNumber(speed) || speed->valuedouble != 100))) return 0;
        }
        pending_ = command;
        return generation_;
    }
    void Receipt(uint64_t call, const char* raw) {
        if (!call) return;
        cJSON* json = cJSON_Parse(raw);
        const auto* result = cJSON_GetObjectItemCaseSensitive(json,"result");
        const auto* op = cJSON_GetObjectItemCaseSensitive(json,"operation");
        const auto* fault = cJSON_GetObjectItemCaseSensitive(json,"fault");
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (call == generation_ && pending_) {
                const bool stop = pending_->tool == "stop";
                accepted_ = cJSON_IsString(op) && pending_->tool == op->valuestring &&
                    cJSON_IsString(result) && std::string_view(result->valuestring) == (stop ? "ok" : "accepted") &&
                    cJSON_IsString(fault) && (std::string_view(fault->valuestring) == "none" ||
                                             (stop && std::string_view(fault->valuestring) == "stopped"));
                if (accepted_ && pending_->tool == "set_speed") {
                    const auto* speed = cJSON_GetObjectItemCaseSensitive(json,"move_speed_percent");
                    accepted_ = cJSON_IsNumber(speed) && speed->valuedouble == 100;
                }
                pending_ = nullptr;
            }
        }
        cJSON_Delete(json);
    }
    void StartSpeech() {
        std::lock_guard<std::mutex> lock(mutex_);
        ++generation_; // An early reply or a delayed receipt stays audible.
        expected_ = nullptr;
        muted_ = accepted_;
        accepted_ = false;
    }
    bool Muted() {
        std::lock_guard<std::mutex> lock(mutex_);
        return muted_;
    }
};
inline VoiceFeedback cybertrack_feedback;
