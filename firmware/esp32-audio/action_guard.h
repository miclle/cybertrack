#pragma once
#include "water_guard.h"
#include <cstring>

// One shared queue, replay table and deadline for all actuators. No combined load.
class AudioActionGuard {
public:
    static constexpr int MoveMaxMs = 3000;
    static constexpr unsigned MoveCooldownMs = 3000;
    AudioWaterGuard bounded;
    enum class Action { None, Water, Move } action = Action::None;
    int left = 0, right = 0;
    const char* direction = "none";

    void Tick(uint64_t now, bool online, bool pressed) {
        const bool moving = Moving();
        bounded.Tick(now, online, pressed);
        FinishMove(now, moving);
    }
    void Stop(uint64_t now) {
        const bool moving = Moving();
        bounded.Stop(now);
        FinishMove(now, moving);
    }
    int Claim(uint64_t now, int rpc) { return bounded.Claim(now, rpc); }
    const char* Water(uint64_t now, int ticket, int duration) {
        const char* result = bounded.Request(now, ticket, duration);
        if (!std::strcmp(result, "accepted")) {
            action = Action::Water; left = right = 0; direction = "none";
        }
        return result;
    }
    static bool Direction(const char* value, int& a, int& b) {
        if (!value) return false;
        if (!std::strcmp(value, "forward")) { a = 60; b = 60; }
        else if (!std::strcmp(value, "backward")) { a = -60; b = -60; }
        else if (!std::strcmp(value, "left")) { a = -60; b = 60; }
        else if (!std::strcmp(value, "right")) { a = 60; b = -60; }
        else return false;
        return true;
    }
    const char* Move(uint64_t now, int ticket, int duration, const char* value) {
        int a = 0, b = 0;
        const bool valid_direction = Direction(value, a, b);
        // Invalid internal requests also consume their ticket without arming.
        const bool valid = valid_direction && duration >= 1 && duration <= MoveMaxMs;
        const char* result = bounded.Request(now, ticket, valid ? duration : 0);
        if (!std::strcmp(result, "accepted")) {
            action = Action::Move; left = a; right = b;
            direction = a == b ? (a > 0 ? "forward" : "backward") : (a < 0 ? "left" : "right");
        }
        return result;
    }
    bool Moving() const { return bounded.policy.active && action == Action::Move; }
    bool Watering() const { return bounded.policy.active && action == Action::Water; }
private:
    void FinishMove(uint64_t now, bool was_moving) {
        if (was_moving && !bounded.policy.active) {
            bounded.policy.cooldown_until = now <= UINT64_MAX - MoveCooldownMs ? now + MoveCooldownMs : UINT64_MAX;
        }
    }
};
