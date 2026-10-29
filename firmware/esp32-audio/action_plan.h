#pragma once
#include "action_guard.h"

// Fixed storage copied at acceptance. No allocation or JSON work in the safety task.
struct ActionPlan {
    static constexpr unsigned MaxSteps = 16;
    struct Step {
        const char* direction = "none";
        int move_ms = 0, water_ms = 0, bubbles_ms = 0, ignition_ms = 0;
        int speed_percent = 100;
        bool Valid() const {
            if (speed_percent < 60 || speed_percent > 100 || move_ms < 0 || water_ms < 0 || bubbles_ms < 0 || ignition_ms < 0 ||
                !(move_ms || water_ms || bubbles_ms || ignition_ms)) return false;
            return (!move_ms ? !std::strcmp(direction, "none") :
                    !AudioActionGuard::Validate(AudioActionGuard::MoveOnly, move_ms, 0, direction)) &&
                water_ms <= static_cast<int>(WATER_MAX_TIMED_MS) &&
                bubbles_ms <= AudioActionGuard::BubblesMaxMs && ignition_ms <= AudioActionGuard::IgnitionMaxMs;
        }
    };
    std::array<Step, MaxSteps> steps{};
    unsigned count = 0;
    bool Valid() const {
        if (!count || count > MaxSteps) return false;
        for (unsigned i = 0; i < count; ++i) if (!steps[i].Valid()) return false;
        return true;
    }
};
