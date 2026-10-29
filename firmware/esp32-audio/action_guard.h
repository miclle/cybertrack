#pragma once
#include "water_guard.h"
#include <cstring>

// Independent deadlines/cooldowns; one session replay table and stop domain.
// Called only under the adapter mutex. Tickets are bound to their target lanes.
class AudioActionGuard {
public:
    enum Target { MoveOnly = 1, WaterOnly = 2, Both = 3, BubblesOnly = 4, IgnitionOnly = 8, All = 15, FrenzyMode = 16, PlanMode = 32, SpeedMode = 64 };
    static constexpr int MoveMaxMs = INT_MAX;
    static constexpr int BubblesMaxMs = 30000;
    static constexpr int IgnitionMaxMs = 5000;
    static constexpr unsigned CooldownMs = 200;
    water_policy motion{}, spray{}, bubbles{}, ignition{};
    unsigned move_duration_ms = 0, water_duration_ms = 0, bubbles_duration_ms = 0, ignition_duration_ms = 0, last_duration_ms = 0;
    int left = 0, right = 0;
    const char* direction = "none";

    void Tick(uint64_t now, bool online, bool pressed, bool reset_replay = true) {
        if (reset_replay && online && !motion.online) count_ = 0;
        const bool moving = Moving(), watering = Watering(), bubbling = Bubbling(), igniting = Igniting();
        water_tick(&motion, now, online, pressed);
        water_tick(&spray, now, online, pressed);
        water_tick(&bubbles, now, online, pressed);
        water_tick(&ignition, now, online, pressed);
        FinishLane(motion, now, moving);
        FinishLane(spray, now, watering);
        FinishLane(bubbles, now, bubbling);
        FinishIgnition(now, igniting);
        if (!online || motion.held || motion.clock_fault || spray.clock_fault || bubbles.clock_fault || ignition.clock_fault) Cancel(All);
    }
    void NewVoiceSession() { count_ = 0; Cancel(All); }
    void CancelPending(Target target = All) { Cancel(target); }
    static const char* Validate(Target target, int move_ms, int water_ms, const char* value, int bubbles_ms = 0, int ignition_ms = 0, int speed_percent = 100) {
        int a = 0, b = 0;
        if (target != MoveOnly && target != WaterOnly && target != Both && target != BubblesOnly && target != IgnitionOnly) return "invalid_request";
        if ((target & MoveOnly) && (move_ms < 1 || move_ms > MoveMaxMs || !Direction(value, a, b, speed_percent)))
            return "invalid_move";
        if ((target & WaterOnly) && (water_ms < 1 || water_ms > static_cast<int>(WATER_MAX_TIMED_MS)))
            return "duration_out_of_range";
        if (target == BubblesOnly && (bubbles_ms < 1 || bubbles_ms > BubblesMaxMs))
            return "duration_out_of_range";
        if (target == IgnitionOnly && (ignition_ms < 1 || ignition_ms > IgnitionMaxMs))
            return "duration_out_of_range";
        return nullptr;
    }
    const char* WebRequest(uint64_t now, Target target, int move_ms, int water_ms, const char* direction, int bubbles_ms = 0, int ignition_ms = 0, int speed_percent = 100) {
        return Execute(now, target, move_ms, water_ms, direction, bubbles_ms, ignition_ms, speed_percent);
    }
    void Stop(uint64_t now) {
        const bool moving = Moving(), watering = Watering(), bubbling = Bubbling(), igniting = Igniting();
        Cancel(All);
        water_stop(&motion, now);
        water_stop(&spray, now);
        water_stop(&bubbles, now);
        water_stop(&ignition, now);
        FinishLane(motion, now, moving);
        FinishLane(spray, now, watering);
        FinishLane(bubbles, now, bubbling);
        FinishIgnition(now, igniting);
    }
    void StopMove(uint64_t now) {
        const bool moving = Moving();
        Cancel(MoveOnly);
        water_stop(&motion, now);
        FinishLane(motion, now, moving);
    }
    void StopWater(uint64_t now) {
        const bool watering = Watering();
        Cancel(WaterOnly);
        water_stop(&spray, now);
        FinishLane(spray, now, watering);
    }
    void StopBubbles(uint64_t now) {
        const bool bubbling = Bubbling();
        Cancel(BubblesOnly);
        water_stop(&bubbles, now);
        FinishLane(bubbles, now, bubbling);
    }
    void StopIgnition(uint64_t now) {
        const bool igniting = Igniting();
        Cancel(IgnitionOnly);
        water_stop(&ignition, now);
        FinishIgnition(now, igniting);
    }
    const char* ClaimPlan(uint64_t now, int ticket) {
        return Request(now, ticket, PlanMode, 0, 0, nullptr);
    }
    const char* VoiceFrenzy(uint64_t now, int ticket, int duration) {
        return Request(now, ticket, FrenzyMode, duration, 0, nullptr);
    }
    const char* Frenzy(uint64_t now, int duration, int speed_percent = 100) {
        if (duration < 1 || duration > 30000 || speed_percent < 60 || speed_percent > 100 || now > UINT64_MAX - duration) return "duration_out_of_range";
        if (!Ready(now, Both) || !Ready(now, BubblesOnly) || !Ready(now, IgnitionOnly)) return "not_ready_or_busy";
        // Preflight all lanes before changing any output; the caller applies once under its mutex.
        Cancel(All);
        const int pulse = duration < 1000 ? duration : 1000;
        if (std::strcmp(Execute(now, Both, pulse, duration, "left", 0, 0, speed_percent), "accepted") ||
            std::strcmp(Execute(now, BubblesOnly, 0, 0, nullptr, duration), "accepted") ||
            std::strcmp(Execute(now, IgnitionOnly, 0, 0, nullptr, 0, pulse), "accepted")) {
            Stop(now); return "not_ready_or_busy";
        }
        motion.ends_at = now + duration; // Mode motion lasts until the shared mode deadline.
        move_duration_ms = last_duration_ms = duration;
        return "accepted";
    }
    bool RenewWebMove(uint64_t now, unsigned lease_ms) {
        if (!motion.active || !motion.online || motion.held || motion.clock_fault ||
            now < motion.last_ms || now >= motion.ends_at || now > UINT64_MAX - lease_ms)
            return false;
        motion.ends_at = now + lease_ms;
        return true;
    }
    bool RenewWebEffect(uint64_t now, Target target, unsigned lease_ms) {
        // Only the two explicitly supported hold lanes can bypass timed-action duration limits.
        if (target != WaterOnly && target != BubblesOnly) return false;
        auto& lane = target == WaterOnly ? spray : bubbles;
        if (!lane.active || !lane.online || lane.held || lane.clock_fault ||
            now < lane.last_ms || now >= lane.ends_at || now > UINT64_MAX - lease_ms)
            return false;
        lane.ends_at = now + lease_ms;
        return true;
    }
    int Claim(uint64_t now, int rpc, Target target) {
        for (unsigned i = 0; i < count_; ++i) if (requests_[i].rpc == rpc) return 0;
        if (count_ == requests_.size() || next_ticket_ == INT_MAX) return 0;
        auto& r = requests_[count_++];
        r = {rpc, ++next_ticket_, now, target, false, motion.starts};
        if (!Ready(now, target)) return 0;
        r.pending = true;
        return r.ticket;
    }
    const char* SetSpeed(uint64_t now, int ticket, int speed) {
        if (speed < 60 || speed > 100) return "invalid_speed";
        const char* result = Request(now, ticket, SpeedMode, 0, 0, nullptr);
        if (std::strcmp(result, "accepted")) return result;
        SetMoveSpeed(speed);
        return "accepted";
    }
    const char* AdjustSpeed(uint64_t now, int ticket, int delta) {
        if (delta != -10 && delta != 10) return "invalid_speed";
        const char* result = Request(now, ticket, SpeedMode, 0, 0, nullptr);
        if (std::strcmp(result, "accepted")) return result;
        int speed = (left < 0 ? -left : left) + delta;
        if (speed < 60) speed = 60;
        if (speed > 100) speed = 100;
        SetMoveSpeed(speed);
        return "accepted";
    }
    const char* Water(uint64_t now, int ticket, int duration) {
        return Request(now, ticket, WaterOnly, 0, duration, nullptr);
    }
    const char* Bubbles(uint64_t now, int ticket, int duration) {
        return Request(now, ticket, BubblesOnly, 0, 0, nullptr, duration);
    }
    const char* Ignition(uint64_t now, int ticket, int duration) {
        return Request(now, ticket, IgnitionOnly, 0, 0, nullptr, 0, duration);
    }
    const char* Move(uint64_t now, int ticket, int duration, const char* value, int speed_percent = 100) {
        return Request(now, ticket, MoveOnly, duration, 0, value, 0, 0, speed_percent);
    }
    const char* MoveAndWater(uint64_t now, int ticket, int move_ms, int water_ms, const char* value, int speed_percent = 100) {
        return Request(now, ticket, Both, move_ms, water_ms, value, 0, 0, speed_percent);
    }
    static bool Direction(const char* value, int& a, int& b, int speed_percent = 100) {
        if (!value || speed_percent < 60 || speed_percent > 100) return false;
        if (!std::strcmp(value, "forward")) { a = speed_percent; b = speed_percent; }
        else if (!std::strcmp(value, "backward")) { a = -speed_percent; b = -speed_percent; }
        else if (!std::strcmp(value, "left")) { a = -speed_percent; b = speed_percent; }
        else if (!std::strcmp(value, "right")) { a = speed_percent; b = -speed_percent; }
        else return false;
        return true;
    }
    bool SetMoveSpeed(int speed_percent) {
        if (!Moving() || speed_percent < 60 || speed_percent > 100) return false;
        return Direction(direction, left, right, speed_percent);
    }
    bool Moving() const { return motion.active; }
    bool Watering() const { return spray.active; }
    bool Bubbling() const { return bubbles.active; }
    bool Igniting() const { return ignition.active; }
    unsigned Starts() const { return motion.starts + spray.starts + bubbles.starts + ignition.starts; }
    static unsigned Remaining(const water_policy& p, uint64_t now) {
        return p.active && p.ends_at > now ? p.ends_at - now : 0;
    }
private:
    struct RequestRecord { int rpc = 0, ticket = 0; uint64_t received = 0; Target target = All; bool pending = false; unsigned motion_start = 0; };
    std::array<RequestRecord, 128> requests_{};
    unsigned count_ = 0;
    int next_ticket_ = 0;
    uint64_t next_output_nonce_ = 0, ignition_started_ = 0;
    static bool LaneReady(const water_policy& p, uint64_t now) {
        return p.online && !p.held && !p.clock_fault && !p.active && !p.armed &&
               now >= p.last_ms && now >= p.cooldown_until && now <= UINT64_MAX - WATER_PERMIT_MS;
    }
    bool Ready(uint64_t now, Target target) const {
        if (target == SpeedMode) return Moving() && motion.online && !motion.held && !motion.clock_fault &&
            now >= motion.last_ms && now < motion.ends_at;
        if (target == FrenzyMode || target == PlanMode) return Ready(now, Both) && Ready(now, BubblesOnly) && Ready(now, IgnitionOnly);
        return (target == MoveOnly || target == WaterOnly || target == Both || target == BubblesOnly || target == IgnitionOnly) &&
               (!(target & MoveOnly) || LaneReady(motion, now)) &&
               (!(target & WaterOnly) || LaneReady(spray, now)) &&
               (!(target & BubblesOnly) || LaneReady(bubbles, now)) &&
               (!(target & IgnitionOnly) || LaneReady(ignition, now));
    }
    void Cancel(Target target) {
        for (unsigned i = 0; i < count_; ++i)
            if ((requests_[i].target & target) || (requests_[i].target == SpeedMode && (target & MoveOnly)) || requests_[i].target == FrenzyMode || requests_[i].target == PlanMode || target == FrenzyMode || target == PlanMode) requests_[i].pending = false;
    }
    const char* Request(uint64_t now, int ticket, Target target, int move_ms, int water_ms, const char* value, int bubbles_ms = 0, int ignition_ms = 0, int speed_percent = 100) {
        RequestRecord* r = nullptr;
        for (unsigned i = 0; i < count_; ++i) if (requests_[i].ticket == ticket) { r = &requests_[i]; break; }
        if (!r || !r->pending) return "cancelled_or_duplicate";
        r->pending = false;
        if (r->target != target) return "ticket_target_mismatch";
        if (now < r->received || now - r->received >= 5000) return "stale_request";
        if (target == SpeedMode) return r->motion_start == motion.starts && Ready(now, SpeedMode) ? "accepted" : "not_ready_or_busy";
        if (target == PlanMode) return Ready(now, PlanMode) ? "accepted" : "not_ready_or_busy";
        if (target == FrenzyMode) return Frenzy(now, move_ms);
        return Execute(now, target, move_ms, water_ms, value, bubbles_ms, ignition_ms, speed_percent);
    }
    const char* Execute(uint64_t now, Target target, int move_ms, int water_ms, const char* value, int bubbles_ms = 0, int ignition_ms = 0, int speed_percent = 100) {
        int a = 0, b = 0;
        if (const char* error = Validate(target, move_ms, water_ms, value, bubbles_ms, ignition_ms, speed_percent)) return error;
        if ((target & MoveOnly) && now > UINT64_MAX - static_cast<unsigned>(move_ms)) return "clock_fault";
        if (target & MoveOnly) Direction(value, a, b, speed_percent);
        // Both requires both lanes ready. Never start just one half of a rejected combined request.
        if (!Ready(now, target)) return "not_ready_or_busy";
        if (next_output_nonce_ == UINT64_MAX) return "nonce_exhausted";
        // ESP32's nano formatter does not support 64-bit printf conversions.
        // Encode directly so the shared output permit stays valid on device.
        char nonce[33] = {};
        uint64_t value_nonce = ++next_output_nonce_;
        for (int i = 31; i >= 0; --i) {
            nonce[i] = "0123456789abcdef"[value_nonce & 15];
            value_nonce >>= 4;
        }
        if (target & MoveOnly) {
            if (!water_arm(&motion, now, nonce) || std::strcmp(water_request_timed(&motion, now, nonce, 1), "accepted")) {
                Stop(now); return "not_ready_or_busy";
            }
            // The shared water gate still enforces its own 30 s limit. Motion has
            // a separately validated integer duration and overflow-checked deadline.
            motion.ends_at = now + static_cast<unsigned>(move_ms);
            left = a; right = b;
            direction = a == b ? (a > 0 ? "forward" : "backward") : (a < 0 ? "left" : "right");
            move_duration_ms = move_ms;
        }
        if (target & WaterOnly) {
            if (!water_arm(&spray, now, nonce) || std::strcmp(water_request_timed(&spray, now, nonce, water_ms), "accepted")) {
                Stop(now); return "not_ready_or_busy";
            }
            water_duration_ms = water_ms;
        }
        if (target == BubblesOnly) {
            if (!water_arm(&bubbles, now, nonce) || std::strcmp(water_request_timed(&bubbles, now, nonce, bubbles_ms), "accepted")) {
                Stop(now); return "not_ready_or_busy";
            }
            bubbles_duration_ms = bubbles_ms;
        }
        if (target == IgnitionOnly) {
            if (!water_arm(&ignition, now, nonce) || std::strcmp(water_request_timed(&ignition, now, nonce, ignition_ms), "accepted")) {
                Stop(now); return "not_ready_or_busy";
            }
            ignition_started_ = now;
            ignition_duration_ms = ignition_ms;
        }
        last_duration_ms = target == IgnitionOnly ? ignition_ms : target == BubblesOnly ? bubbles_ms : target == MoveOnly ? move_ms : target == WaterOnly ? water_ms : (move_ms > water_ms ? move_ms : water_ms);
        Cancel(target); // Cancel same-lane bursts; independent queued lane remains eligible.
        return "accepted";
    }
    void FinishIgnition(uint64_t now, bool was_active) {
        if (!was_active || ignition.active) return;
        // Use elapsed software ON time, including an early stop or a delayed deadline tick.
        const uint64_t elapsed = now >= ignition_started_ ? now - ignition_started_ : UINT64_MAX;
        ignition.cooldown_until = now <= UINT64_MAX - elapsed ? now + elapsed : UINT64_MAX;
    }
    static void FinishLane(water_policy& lane, uint64_t now, bool was_active, unsigned interval = CooldownMs) {
        // Audio-board interaction interval; leave the standalone water policy unchanged.
        if (was_active && !lane.active)
            lane.cooldown_until = now <= UINT64_MAX - interval ? now + interval : UINT64_MAX;
    }
};
