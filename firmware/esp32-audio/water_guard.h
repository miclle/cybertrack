#pragma once
#include <array>
#include <climits>
#include <cstdio>
#include <cstdint>
extern "C" {
#include "water_policy.h"
}

// All methods run under the adapter lock. Tickets are local queue bookkeeping,
// never cloud arguments or a physical authorization requirement.
class AudioWaterGuard {
public:
    void Tick(uint64_t now, bool online, bool pressed) {
        if (online && !policy.online) count_ = 0; // RPC IDs are session scoped.
        water_tick(&policy, now, online, pressed);
        if (!online || policy.held || policy.clock_fault) CancelPending();
    }
    void Stop(uint64_t now) {
        CancelPending();
        water_stop(&policy, now);
    }
    int Claim(uint64_t now, int rpc_id) {
        for (unsigned i = 0; i < count_; ++i)
            if (requests_[i].rpc_id == rpc_id) return 0;
        if (count_ == requests_.size() || next_ticket_ == INT_MAX) return 0;
        auto& r = requests_[count_++];
        r = {rpc_id, ++next_ticket_, now, false};
        // Reject a request received while busy, even if its callback runs later.
        if (!policy.online || policy.held || policy.clock_fault || policy.active ||
            now < policy.last_ms || now < policy.cooldown_until) return 0;
        r.pending = true;
        return r.ticket;
    }
    const char* Request(uint64_t now, int ticket, int duration) {
        for (unsigned i = 0; i < count_; ++i) {
            auto& r = requests_[i];
            if (r.ticket != ticket) continue;
            if (!r.pending) return "cancelled_or_duplicate";
            r.pending = false;
            if (now < r.received || now - r.received >= 5000) return "stale_request";
            if (duration < 1 || duration > static_cast<int>(WATER_MAX_TIMED_MS)) return "duration_out_of_range";
            // Reuse the bounded policy atomically, without exposing a permit.
            char nonce[33];
            std::snprintf(nonce, sizeof(nonce), "%032x", static_cast<unsigned>(ticket));
            if (!water_arm(&policy, now, nonce)) return "not_ready_or_busy";
            const char* result = water_request_timed(&policy, now, nonce, duration);
            if (policy.active) last_duration_ms = duration;
            return result;
        }
        return "cancelled_or_duplicate";
    }
    water_policy policy{};
    unsigned last_duration_ms = 0;
private:
    struct RequestRecord { int rpc_id = 0, ticket = 0; uint64_t received = 0; bool pending = false; };
    // Fail closed if one audio session exhausts the replay table; never evict IDs.
    std::array<RequestRecord, 128> requests_{};
    unsigned count_ = 0;
    int next_ticket_ = 0;
    void CancelPending() {
        for (unsigned i = 0; i < count_; ++i) requests_[i].pending = false;
    }
};
