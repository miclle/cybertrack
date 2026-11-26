#pragma once
#include <cstdint>

// Only SafetyTask clocks the two flip-flops. All callers sample U27 under
// the action mutex; its asynchronous clear retains even a sub-tick trip.
class A4Interlock {
public:
    bool Sample(bool high, uint64_t now) {
        if (high != feedback_high_) {
            feedback_high_ = high;
            if (high) admit_after_ = now + QualifyMs;
            else next_clock_ = now + ClockIntervalMs;
        }
        return high && now >= admit_after_;
    }

    bool ClockDue(uint64_t now) const { return !feedback_high_ && now >= next_clock_; }
    void ClockIssued(uint64_t now) { next_clock_ = now + ClockIntervalMs; }

private:
    // Prototype allowances. Recheck the ramp and tWAKE on the actual board.
    static constexpr uint64_t ClockIntervalMs = 100, QualifyMs = 5;
    uint64_t next_clock_ = ClockIntervalMs, admit_after_ = 0;
    bool feedback_high_ = false;
};
