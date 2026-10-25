#pragma once
#include "water_guard.h"
#include <cstring>

// Independent deadlines/cooldowns; one session replay table and stop domain.
// Called only under the adapter mutex. Tickets are bound to their target lanes.
class AudioActionGuard {
public:
    enum Target { MoveOnly = 1, WaterOnly = 2, Both = 3 };
    static constexpr int MoveMaxMs = 3000;
    static constexpr unsigned CooldownMs = 200;
    water_policy motion{}, spray{};
    unsigned move_duration_ms = 0, water_duration_ms = 0, last_duration_ms = 0;
    int left = 0, right = 0;
    const char* direction = "none";

    void Tick(uint64_t now, bool online, bool pressed, bool reset_replay = true) {
        if (reset_replay && online && !motion.online) count_ = 0;
        const bool moving = Moving(), watering = Watering();
        water_tick(&motion, now, online, pressed);
        water_tick(&spray, now, online, pressed);
        FinishLane(motion, now, moving);
        FinishLane(spray, now, watering);
        if (!online || motion.held || motion.clock_fault || spray.clock_fault) Cancel(Both);
    }
    void NewVoiceSession() { count_ = 0; Cancel(Both); }
    void CancelPending(Target target = Both) { Cancel(target); }
    static const char* Validate(Target target, int move_ms, int water_ms, const char* value) {
        int a = 0, b = 0;
        if (target != MoveOnly && target != WaterOnly && target != Both) return "invalid_request";
        if ((target & MoveOnly) && (move_ms < 1 || move_ms > MoveMaxMs || !Direction(value, a, b)))
            return "invalid_move";
        if ((target & WaterOnly) && (water_ms < 1 || water_ms > static_cast<int>(WATER_MAX_TIMED_MS)))
            return "duration_out_of_range";
        return nullptr;
    }
    const char* WebRequest(uint64_t now, Target target, int move_ms, int water_ms, const char* direction) {
        return Execute(now, target, move_ms, water_ms, direction);
    }
    void Stop(uint64_t now) {
        const bool moving = Moving(), watering = Watering();
        Cancel(Both);
        water_stop(&motion, now);
        water_stop(&spray, now);
        FinishLane(motion, now, moving);
        FinishLane(spray, now, watering);
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
    bool RenewWebMove(uint64_t now, unsigned lease_ms) {
        if (!motion.active || !motion.online || motion.held || motion.clock_fault ||
            now < motion.last_ms || now >= motion.ends_at || now > UINT64_MAX - lease_ms)
            return false;
        motion.ends_at = now + lease_ms;
        return true;
    }
    int Claim(uint64_t now, int rpc, Target target) {
        for (unsigned i = 0; i < count_; ++i) if (requests_[i].rpc == rpc) return 0;
        if (count_ == requests_.size() || next_ticket_ == INT_MAX) return 0;
        auto& r = requests_[count_++];
        r = {rpc, ++next_ticket_, now, target, false};
        if (!Ready(now, target)) return 0;
        r.pending = true;
        return r.ticket;
    }
    const char* Water(uint64_t now, int ticket, int duration) {
        return Request(now, ticket, WaterOnly, 0, duration, nullptr);
    }
    const char* Move(uint64_t now, int ticket, int duration, const char* value) {
        return Request(now, ticket, MoveOnly, duration, 0, value);
    }
    const char* MoveAndWater(uint64_t now, int ticket, int move_ms, int water_ms, const char* value) {
        return Request(now, ticket, Both, move_ms, water_ms, value);
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
    bool Moving() const { return motion.active; }
    bool Watering() const { return spray.active; }
    unsigned Starts() const { return motion.starts + spray.starts; }
    static unsigned Remaining(const water_policy& p, uint64_t now) {
        return p.active && p.ends_at > now ? p.ends_at - now : 0;
    }
private:
    struct RequestRecord { int rpc = 0, ticket = 0; uint64_t received = 0; Target target = Both; bool pending = false; };
    std::array<RequestRecord, 128> requests_{};
    unsigned count_ = 0;
    int next_ticket_ = 0;
    uint64_t next_output_nonce_ = 0;
    static bool LaneReady(const water_policy& p, uint64_t now) {
        return p.online && !p.held && !p.clock_fault && !p.active && !p.armed &&
               now >= p.last_ms && now >= p.cooldown_until && now <= UINT64_MAX - WATER_PERMIT_MS;
    }
    bool Ready(uint64_t now, Target target) const {
        return (target == MoveOnly || target == WaterOnly || target == Both) &&
               (!(target & MoveOnly) || LaneReady(motion, now)) &&
               (!(target & WaterOnly) || LaneReady(spray, now));
    }
    void Cancel(Target target) {
        for (unsigned i = 0; i < count_; ++i)
            if (requests_[i].target & target) requests_[i].pending = false;
    }
    const char* Request(uint64_t now, int ticket, Target target, int move_ms, int water_ms, const char* value) {
        RequestRecord* r = nullptr;
        for (unsigned i = 0; i < count_; ++i) if (requests_[i].ticket == ticket) { r = &requests_[i]; break; }
        if (!r || !r->pending) return "cancelled_or_duplicate";
        r->pending = false;
        if (r->target != target) return "ticket_target_mismatch";
        if (now < r->received || now - r->received >= 5000) return "stale_request";
        return Execute(now, target, move_ms, water_ms, value);
    }
    const char* Execute(uint64_t now, Target target, int move_ms, int water_ms, const char* value) {
        int a = 0, b = 0;
        if (const char* error = Validate(target, move_ms, water_ms, value)) return error;
        if (target & MoveOnly) Direction(value, a, b);
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
            if (!water_arm(&motion, now, nonce) || std::strcmp(water_request_timed(&motion, now, nonce, move_ms), "accepted")) {
                Stop(now); return "not_ready_or_busy";
            }
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
        last_duration_ms = target == MoveOnly ? move_ms : target == WaterOnly ? water_ms : (move_ms > water_ms ? move_ms : water_ms);
        Cancel(target); // Cancel same-lane bursts; independent queued lane remains eligible.
        return "accepted";
    }
    static void FinishLane(water_policy& lane, uint64_t now, bool was_active) {
        // Audio-board interaction interval; leave the standalone water policy unchanged.
        if (was_active && !lane.active)
            lane.cooldown_until = now <= UINT64_MAX - CooldownMs ? now + CooldownMs : UINT64_MAX;
    }
};
