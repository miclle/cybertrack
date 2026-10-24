#pragma once
#include <cstdint>
#include <charconv>
#include <cstdio>
#include <string>
extern "C" {
#include "cybertrack/control.h"
}

// Owned by Xiaozhi's serialized main task. No GPIO adapter, enable or action API.
class CyberTrackAudioState {
public:
    explicit CyberTrackAudioState(uint64_t now) {
        ct_init(&control_, ct_limits{}, now);
        ct_boot_complete(&control_);
    }
    std::string Call(bool stop, uint64_t now, const std::string& device_id,
                     const std::string& boot_id) {
        ct_tick(&control_, now);
        if (stop) ct_stop(&control_);
        ++sequence_;
        const char* state = control_.state == CT_FAULT ? "FAULT" : "DISARMED";
        const char* fault = control_.fault == CT_STOPPED ? "stopped" :
                            control_.fault == CT_CLOCK_FAULT ? "clock_fault" : "none";
        // The original board uses newlib-nano: its printf cannot consume %llu.
        // Integer to_chars is independent of printf and preserves all 64 bits.
        const auto sequence = Decimal(sequence_);
        const auto uptime = Decimal(now);
        // Device/boot identifiers are generated locally as MAC/hex, never tool input.
        char result[1024];
        std::snprintf(result, sizeof(result),
            "{\"device_id\":\"%s\",\"boot_id\":\"%s\",\"request_sequence\":%s,"
            "\"operation\":\"%s\",\"state\":\"%s\",\"fault\":\"%s\",\"uptime_ms\":%s,"
            "\"logical_outputs\":{\"left\":%d,\"right\":%d,\"water\":%s,\"bubbles\":%s},"
            "\"capabilities\":{\"move\":false,\"water\":false,\"bubbles\":false},"
            "\"actuator_backend\":\"not_installed\",\"physical_feedback\":false,"
            "\"source\":\"cybertrack_audio_board\",\"stop_scope\":\"logical_control_only\"}",
            device_id.c_str(), boot_id.c_str(), sequence.c_str(),
            stop ? "stop" : "get_status", state, fault, uptime.c_str(),
            control_.output.left_level, control_.output.right_level,
            control_.output.water ? "true" : "false", control_.output.bubbles ? "true" : "false");
        return result;
    }
private:
    static std::string Decimal(uint64_t value) {
        char text[20];  // UINT64_MAX has exactly 20 decimal digits.
        auto result = std::to_chars(text, text + sizeof(text), value);
        return std::string(text, result.ptr);
    }
    ct_controller control_{};
    uint64_t sequence_ = 0;
};
