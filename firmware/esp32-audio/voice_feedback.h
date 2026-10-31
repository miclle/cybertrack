#pragma once
#include "cJSON.h"
#include "spoken_duration.h"
#include "spoken_playback.h"
#include <mutex>
#include <string_view>
#include <cstdint>

// A match only affects playback. This class has no command or output callbacks.
class VoiceFeedback {
    struct Command {
        std::string_view phrase, tool, direction;
        int duration;
        bool verify_duration;
        std::string_view duration_field;
    };
    static constexpr Command commands[] = {
        {"前进","move","forward",1000,false,{}}, {"后退","move","backward",1000,false,{}},
        {"左转","move","left",880,false,{}}, {"右转","move","right",880,false,{}},
        {"全速","set_speed","",0,false,{}}, {"最快","set_speed","",0,false,{}},
        {"最大速度","set_speed","",0,false,{}}, {"调到全速","set_speed","",0,false,{}},
        {"停止","stop","",0,false,{}}, {"停下","stop","",0,false,{}}, {"全部停止","stop","",0,false,{}},
        {"停止行走","stop","",0,false,{}}, {"停止喷水","stop","",0,false,{}}, {"停止泡泡","stop","",0,false,{}},
        {"停止狂暴模式","stop","",0,false,{}}, {"所有动作都停下来","stop","",0,false,{}},
        {"停止点火","stop","",0,false,{}}, {"停止放电","stop","",0,false,{}},
        {"停止射击","stop","",0,false,{}}, {"关闭护盾","stop","",0,false,{}},
        {"停止饭店","stop","",0,false,{}},
        {"取消序列","stop","",0,false,{}}, {"取消正在执行的表演","stop","",0,false,{}}
    };
    struct Effect {
        std::string_view phrase, tool, duration_field;
        int default_ms, maximum_ms;
    };
    static constexpr Effect effects[] = {
        {"喷水","water","water_last_duration_ms",1000,30000},
        {"发射","water","water_last_duration_ms",1000,30000},
        {"开枪","water","water_last_duration_ms",1000,30000},
        {"射击","water","water_last_duration_ms",1000,30000},
        {"吹泡泡","bubbles","bubbles_last_duration_ms",1000,30000},
        {"开炮","bubbles","bubbles_last_duration_ms",1000,30000},
        {"点火","ignition","ignition_last_duration_ms",1000,5000},
        {"放电","ignition","ignition_last_duration_ms",1000,5000},
        {"闪电","ignition","ignition_last_duration_ms",1000,5000},
        {"护盾","ignition","ignition_last_duration_ms",1000,5000},
        {"打火","ignition","ignition_last_duration_ms",1000,5000},
        {"电击","ignition","ignition_last_duration_ms",1000,5000},
        {"饭店","ignition","ignition_last_duration_ms",1000,5000},
        {"狂暴模式","frenzy","frenzy_last_duration_ms",5000,30000}
    };
    Command timed_effect_{};
    std::mutex mutex_;
    uint64_t generation_ = 0;
    const Command* expected_ = nullptr;
    const Command* pending_ = nullptr;
    SpokenPlayback plan_{};
    bool expected_plan_ = false, pending_plan_ = false;
    bool accepted_ = false, muted_ = false;

public:
    void Input(std::string_view text) {
        std::lock_guard<std::mutex> lock(mutex_);
        ++generation_;
        accepted_ = muted_ = false;
        expected_ = nullptr;
        expected_plan_ = pending_plan_ = false;
        for (std::string_view suffix : {"。", "！", "!"}) {
            if (text.size() >= suffix.size() && text.substr(text.size()-suffix.size()) == suffix) {
                text.remove_suffix(suffix.size());
                break;
            }
        }
        for (const auto& command : commands)
            if (command.phrase == text) expected_ = &command;
        auto effect_text = text;
        if (effect_text.substr(0,std::string_view("开启").size()) == "开启")
            effect_text.remove_prefix(std::string_view("开启").size());
        for (const auto& effect : effects) {
            if (effect_text.substr(0,effect.phrase.size()) != effect.phrase) continue;
            auto suffix = effect_text.substr(effect.phrase.size());
            int ms = suffix.empty() || suffix == "一下" ? effect.default_ms : SpokenEffectMs(suffix);
            // Preserve limit explanations; only a complete, bounded phrase matches.
            if (ms > 0 && ms <= effect.maximum_ms) {
                timed_effect_ = {{},effect.tool,{},ms,true,effect.duration_field};
                expected_ = &timed_effect_;
            }
        }
        if (!expected_) expected_plan_ = plan_.Parse(text);
    }
    uint64_t BeginCall(std::string_view tool, const cJSON* args) {
        std::lock_guard<std::mutex> lock(mutex_);
        ++generation_;
        const auto* command = expected_;
        expected_ = nullptr;
        pending_ = nullptr;
        accepted_ = muted_ = false;
        constexpr std::string_view prefix = "self.tank.";
        const bool candidate = expected_plan_;
        expected_plan_ = pending_plan_ = false;
        if (candidate && tool.substr(0,prefix.size()) == prefix && tool.substr(prefix.size()) == plan_.tool && plan_.Request(args)) {
            pending_plan_ = true;
            return generation_;
        }
        if (!command || tool.substr(0,prefix.size()) != prefix || tool.substr(prefix.size()) != command->tool)
            return 0;
        if (command->tool == "set_speed") {
            const auto* speed = cJSON_GetObjectItemCaseSensitive(args,"speed_percent");
            if (cJSON_GetArraySize(args) != 1 || !cJSON_IsNumber(speed) || speed->valuedouble != 100)
                return 0;
        }
        if (command->verify_duration && (!cJSON_IsObject(args) || cJSON_GetArraySize(args)!=1)) return 0;
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
            if (call == generation_ && pending_plan_) {
                accepted_ = plan_.Receipt(json);
                pending_plan_ = false;
            } else if (call == generation_ && pending_) {
                const bool stop = pending_->tool == "stop";
                accepted_ = cJSON_IsString(op) && pending_->tool == op->valuestring &&
                    cJSON_IsString(result) && std::string_view(result->valuestring) == (stop ? "ok" : "accepted") &&
                    cJSON_IsString(fault) && (std::string_view(fault->valuestring) == "none" ||
                                             (stop && std::string_view(fault->valuestring) == "stopped"));
                if (accepted_ && pending_->tool == "set_speed") {
                    const auto* speed = cJSON_GetObjectItemCaseSensitive(json,"move_speed_percent");
                    accepted_ = cJSON_IsNumber(speed) && speed->valuedouble == 100;
                }
                if (accepted_ && pending_->verify_duration) {
                    // Other concurrently running lanes may dominate last_duration_ms.
                    const auto* duration = cJSON_GetObjectItemCaseSensitive(json,pending_->duration_field.data());
                    accepted_ = cJSON_IsNumber(duration) && duration->valuedouble == pending_->duration;
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
        expected_plan_ = pending_plan_ = false;
        muted_ = accepted_;
        accepted_ = false;
    }
    bool Muted() {
        std::lock_guard<std::mutex> lock(mutex_);
        return muted_;
    }
};
inline VoiceFeedback cybertrack_feedback;
