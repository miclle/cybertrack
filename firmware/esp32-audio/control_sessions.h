#pragma once
#include "action_guard.h"
#include "action_plan.h"

// All methods run under the adapter mutex, including the 5 ms deadline tick.
// One expiring web session coexists with voice; active web lanes have priority.
class ControlSessions {
public:
    static constexpr uint64_t LeaseMs = 2000, WindowMs = 1500;
    static constexpr unsigned DriveLeaseMs = 600;
    struct EffectHold { uint32_t id = 0, renewal = 0; uint64_t started = 0, until = 0; };
    EffectHold water_hold, bubbles_hold;
    AudioActionGuard guard;
    bool plan_active = false;
    unsigned plan_step = 0, plan_count = 0;
    const char* plan_result = "idle";
    bool wifi = false, voice = false, shutdown = false;
    uint32_t owner = 0, window = 0;
    uint32_t drive_id = 0, drive_renewal = 0;
    uint64_t frenzy_until = 0;
    unsigned frenzy_duration_ms = 0;
    const char* FrenzySource() const { return !frenzy_until ? "none" : frenzy_web_ ? "web" : "voice"; }

    void Tick(uint64_t now, bool pressed, bool output_fault = false) {
        if (owner && (now < heartbeat_ || now - heartbeat_ >= LeaseMs || !wifi || shutdown)) {
            owner = 0;
            StopWeb(now);
        }
        if (pressed && !pressed_) Stop(now);
        if (drive_id && (now >= drive_until_ || now < drive_started_)) StopWeb(now);
        for (auto target : {AudioActionGuard::WaterOnly, AudioActionGuard::BubblesOnly}) {
            auto& h = Hold(target);
            if (h.id && (now >= h.until || now < h.started)) StopEffect(now, target);
        }
        pressed_ = pressed;
        guard.Tick(now, !shutdown && !output_fault && wifi && (owner || voice), pressed, false);
        if (frenzy_until) {
            if (now < frenzy_started_ || now >= frenzy_until || (frenzy_web_ ? !owner : !voice) || output_fault ||
                !guard.Moving() || !guard.Watering() || !guard.Bubbling() || guard.ignition.clock_fault || guard.ignition.held) {
                Stop(now);
            } else if (!guard.Igniting() && now >= guard.ignition.cooldown_until) {
                const int pulse = frenzy_until - now < 1000 ? frenzy_until - now : 1000;
                if (std::strcmp(guard.WebRequest(now, AudioActionGuard::IgnitionOnly, 0, 0, nullptr, 0, pulse), "accepted")) Stop(now);
            }
        }
        TickPlan(now, output_fault);
        if (drive_id && !guard.Moving()) StopWeb(now);
        if (!guard.Watering()) water_hold = {};
        if (!guard.Bubbling()) bubbles_hold = {};
        if (!guard.Moving()) web_targets_ &= ~AudioActionGuard::MoveOnly;
        if (!guard.Watering()) web_targets_ &= ~AudioActionGuard::WaterOnly;
        if (!guard.Bubbling()) web_targets_ &= ~AudioActionGuard::BubblesOnly;
        if (!guard.Igniting() && !frenzy_until) web_targets_ &= ~AudioActionGuard::IgnitionOnly;
    }
    void Stop(uint64_t now) {
        if (plan_active) { plan_active = false; plan_result = "cancelled"; }
        guard.Stop(now);
        web_targets_ = 0;
        window_valid_ = false;
        drive_id = drive_renewal = 0;
        water_hold = {}; bubbles_hold = {};
        frenzy_until = 0;
    }
    void VoiceLink(uint64_t now, bool online) {
        if (online && !voice) guard.NewVoiceSession();
        voice = online;
        if (!online) {
            if (plan_active || (frenzy_until && !frenzy_web_)) Stop(now);
            guard.CancelPending();
            if (!(web_targets_ & AudioActionGuard::MoveOnly)) guard.StopMove(now);
            if (!(web_targets_ & AudioActionGuard::WaterOnly)) guard.StopWater(now);
            if (!(web_targets_ & AudioActionGuard::BubblesOnly)) guard.StopBubbles(now);
            if (!(web_targets_ & AudioActionGuard::IgnitionOnly)) guard.StopIgnition(now);
        }
    }
    void WifiLink(uint64_t now, bool online) {
        wifi = online;
        if (!online) { voice = false; owner = 0; Stop(now); }
    }
    void Shutdown(uint64_t now) {
        shutdown = true; owner = 0; voice = false; Stop(now);
    }
    uint32_t Acquire(uint64_t now) {
        if (owner || !wifi || shutdown || generation_ == UINT32_MAX)
            return 0;
        window_valid_ = false; // Opening a page must not interrupt voice work.
        owner = ++generation_;
        heartbeat_ = now;
        window_issued_ = now;
        sequence_ = 0;
        return owner;
    }
    bool Owns(uint32_t session) const { return session && owner == session; }
    bool Heartbeat(uint64_t now, uint32_t session) {
        if (!Owns(session) || now < heartbeat_ || now - heartbeat_ >= LeaseMs || window == UINT32_MAX)
            return false;
        heartbeat_ = now;
        ++window;
        window_issued_ = now;
        window_valid_ = guard.motion.online && !guard.motion.held && !guard.motion.clock_fault && !guard.spray.clock_fault && !guard.bubbles.clock_fault && !guard.ignition.clock_fault;
        return true;
    }
    bool Release(uint64_t now, uint32_t session) {
        if (!Owns(session)) return false;
        owner = 0;
        StopWeb(now);
        return true;
    }
    int VoiceClaim(uint64_t now, int rpc, AudioActionGuard::Target target) {
        const unsigned lanes = (target == AudioActionGuard::FrenzyMode || target == AudioActionGuard::PlanMode) ? AudioActionGuard::All : target;
        return wifi && voice && !shutdown && !frenzy_until && !plan_active && !(web_targets_ & lanes) ? guard.Claim(now, rpc, target) : 0;
    }
    const char* WebAction(uint64_t now, uint32_t session, uint32_t seq, uint32_t command_window,
                          AudioActionGuard::Target target, int move_ms, int water_ms, const char* direction, int bubbles_ms = 0, int ignition_ms = 0) {
        const char* error = Consume(now, session, seq, command_window, WindowMs);
        if (error) return error;
        return StartWeb(now, target, move_ms, water_ms, direction, bubbles_ms, ignition_ms);
    }
    const char* FrenzyStart(uint64_t now, uint32_t session, uint32_t seq, uint32_t command_window, int duration) {
        const char* error = Consume(now, session, seq, command_window, WindowMs);
        if (error) return error;
        if (plan_active) { Stop(now); return "voice_preempted"; }
        if (frenzy_until) {
            if (!frenzy_web_) { Stop(now); return "voice_preempted"; }
            return "not_ready_or_busy";
        }
        const char* result = guard.Frenzy(now, duration);
        if (!std::strcmp(result, "accepted")) {
            frenzy_started_ = now; frenzy_until = now + duration;
            frenzy_duration_ms = duration; frenzy_web_ = true;
            web_targets_ = AudioActionGuard::All;
        }
        return result;
    }
    const char* VoiceFrenzy(uint64_t now, int ticket, int duration) {
        if (!wifi || !voice || shutdown || frenzy_until || plan_active || web_targets_) return "not_ready_or_busy";
        const char* result = guard.VoiceFrenzy(now, ticket, duration);
        if (!std::strcmp(result, "accepted")) {
            frenzy_started_ = now; frenzy_until = now + duration;
            frenzy_duration_ms = duration; frenzy_web_ = false;
        }
        return result;
    }
    const char* VoicePlan(uint64_t now, int ticket, const ActionPlan& plan) {
        if (!plan.Valid()) return "invalid_plan";
        if (!wifi || !voice || shutdown || frenzy_until || plan_active || web_targets_) return "not_ready_or_busy";
        const char* result = guard.ClaimPlan(now, ticket);
        if (std::strcmp(result, "accepted")) return result;
        plan_ = plan;
        plan_step = 1; plan_count = plan.count; plan_active = true;
        guard.CancelPending();
        return StartPlanStep(now) ? "accepted" : "not_ready_or_busy";
    }
    const char* DriveStart(uint64_t now, uint32_t session, uint32_t seq, uint32_t command_window,
                           const char* direction, int water_ms) {
        const char* error = Consume(now, session, seq, command_window, DriveLeaseMs);
        if (error) return error;
        const char* result = StartWeb(now, water_ms ? AudioActionGuard::Both : AudioActionGuard::MoveOnly,
                                             DriveLeaseMs, water_ms, direction);
        if (!std::strcmp(result, "accepted")) {
            drive_id = seq; drive_renewal = 1;
            drive_started_ = now; drive_until_ = now + DriveLeaseMs;
        }
        return result;
    }
    const char* DriveRenew(uint64_t now, uint32_t session, uint32_t id, uint32_t renewal) {
        if (!Owns(session)) return "session_expired";
        if (!id || id != drive_id || !renewal || renewal != drive_renewal || renewal == UINT32_MAX)
            return "drive_cancelled";
        if (now >= drive_until_ || !guard.RenewWebMove(now, DriveLeaseMs)) {
            StopWeb(now); return "drive_cancelled";
        }
        ++drive_renewal; // A response is required before the next renewal. Duplicates cannot extend motion.
        drive_until_ = now + DriveLeaseMs;
        heartbeat_ = now; // Renew ownership, but never refresh an old action window.
        return "renewed";
    }
    const char* DriveStop(uint64_t now, uint32_t session, uint32_t id) {
        if (!Owns(session)) return "session_expired";
        if (!id) return "invalid_request";
        // Tombstone even an unseen start: release may overtake a delayed pointer-down request.
        if (id > sequence_) sequence_ = id;
        if (drive_id && id >= drive_id) {
            guard.StopMove(now);
            web_targets_ &= ~AudioActionGuard::MoveOnly;
            drive_id = drive_renewal = 0;
        }
        return "ok";
    }
    const char* EffectStart(uint64_t now, uint32_t session, uint32_t seq, uint32_t command_window,
                            AudioActionGuard::Target target) {
        if (!EffectTarget(target)) return "invalid_request";
        const char* error = Consume(now, session, seq, command_window, DriveLeaseMs);
        if (error) return error;
        const char* result = StartWeb(now, target, 0, target == AudioActionGuard::WaterOnly ? DriveLeaseMs : 0,
                                     nullptr, target == AudioActionGuard::BubblesOnly ? DriveLeaseMs : 0);
        if (!std::strcmp(result, "accepted")) Hold(target) = {seq, 1, now, now + DriveLeaseMs};
        return result;
    }
    const char* EffectRenew(uint64_t now, uint32_t session, AudioActionGuard::Target target,
                            uint32_t id, uint32_t renewal) {
        if (!EffectTarget(target)) return "invalid_request";
        if (!Owns(session)) return "session_expired";
        auto& h = Hold(target);
        if (!id || h.id != id || !renewal || h.renewal != renewal || renewal == UINT32_MAX)
            return "hold_cancelled";
        if (now >= h.until || !guard.RenewWebEffect(now, target, DriveLeaseMs)) {
            StopEffect(now, target); return "hold_cancelled";
        }
        ++h.renewal; h.until = now + DriveLeaseMs; heartbeat_ = now;
        return "renewed";
    }
    const char* EffectStop(uint64_t now, uint32_t session, AudioActionGuard::Target target, uint32_t id) {
        if (!EffectTarget(target)) return "invalid_request";
        if (!Owns(session)) return "session_expired";
        if (!id) return "invalid_request";
        if (id > sequence_) sequence_ = id; // A release can arrive before its start.
        if (Hold(target).id && id >= Hold(target).id) StopEffect(now, target);
        return "ok";
    }
    const char* MoveSource() const { return !guard.Moving() ? "none" : (web_targets_ & AudioActionGuard::MoveOnly) ? "web" : "voice"; }
    const char* WaterSource() const { return !guard.Watering() ? "none" : (web_targets_ & AudioActionGuard::WaterOnly) ? "web" : "voice"; }
    const char* BubblesSource() const { return !guard.Bubbling() ? "none" : (web_targets_ & AudioActionGuard::BubblesOnly) ? "web" : "voice"; }
    const char* IgnitionSource() const { return !guard.Igniting() ? "none" : (web_targets_ & AudioActionGuard::IgnitionOnly) ? "web" : "voice"; }
private:
    ActionPlan plan_;
    uint64_t plan_deadlines_[4] = {};
    uint64_t plan_last_tick_ = 0;
    bool StartPlanStep(uint64_t now) {
        const auto& step = plan_.steps[plan_step - 1];
        const int durations[] = {step.move_ms, step.water_ms, step.bubbles_ms, step.ignition_ms};
        const AudioActionGuard::Target targets[] = {AudioActionGuard::MoveOnly, AudioActionGuard::WaterOnly,
                                                   AudioActionGuard::BubblesOnly, AudioActionGuard::IgnitionOnly};
        for (unsigned i = 0; i < 4; ++i) {
            plan_deadlines_[i] = 0;
            if (!durations[i]) continue;
            if (now > UINT64_MAX - static_cast<unsigned>(durations[i]) ||
                std::strcmp(guard.WebRequest(now, targets[i], step.move_ms, step.water_ms,
                                             step.direction, step.bubbles_ms, step.ignition_ms), "accepted")) {
                Stop(now); return false;
            }
            plan_deadlines_[i] = now + static_cast<unsigned>(durations[i]);
        }
        plan_last_tick_ = now;
        plan_result = "running";
        return true;
    }
    void TickPlan(uint64_t now, bool output_fault) {
        if (!plan_active) return;
        if (!wifi || !voice || shutdown || output_fault || now < plan_last_tick_ ||
            guard.motion.held || guard.motion.clock_fault || guard.spray.clock_fault ||
            guard.bubbles.clock_fault || guard.ignition.clock_fault) { Stop(now); return; }
        plan_last_tick_ = now;
        const water_policy* lanes[] = {&guard.motion, &guard.spray, &guard.bubbles, &guard.ignition};
        bool active = false, cooling = false;
        for (unsigned i = 0; i < 4; ++i) {
            if (plan_deadlines_[i] > now && !lanes[i]->active) { Stop(now); return; }
            active |= lanes[i]->active;
            cooling |= now < lanes[i]->cooldown_until;
        }
        if (active) return;
        if (plan_step == plan_count) { plan_active = false; plan_result = "completed"; return; }
        plan_result = "waiting";
        if (cooling) return;
        ++plan_step;
        StartPlanStep(now);
    }
    unsigned web_targets_ = 0;
    static bool EffectTarget(AudioActionGuard::Target t) {
        return t == AudioActionGuard::WaterOnly || t == AudioActionGuard::BubblesOnly;
    }
    EffectHold& Hold(AudioActionGuard::Target t) {
        return t == AudioActionGuard::WaterOnly ? water_hold : bubbles_hold;
    }
    void StopEffect(uint64_t now, AudioActionGuard::Target t) {
        if (t == AudioActionGuard::WaterOnly) guard.StopWater(now); else guard.StopBubbles(now);
        web_targets_ &= ~t;
        Hold(t) = {};
    }
    void StopWeb(uint64_t now) {
        if (web_targets_ & AudioActionGuard::MoveOnly) guard.StopMove(now);
        if (web_targets_ & AudioActionGuard::WaterOnly) guard.StopWater(now);
        if (web_targets_ & AudioActionGuard::BubblesOnly) guard.StopBubbles(now);
        if (web_targets_ & AudioActionGuard::IgnitionOnly) guard.StopIgnition(now);
        web_targets_ = 0;
        drive_id = drive_renewal = 0;
        water_hold = {}; bubbles_hold = {};
        if (frenzy_web_) frenzy_until = 0;
        window_valid_ = false;
    }
    const char* StartWeb(uint64_t now, AudioActionGuard::Target target, int move_ms, int water_ms, const char* direction, int bubbles_ms = 0, int ignition_ms = 0) {
        if (plan_active) { Stop(now); return "voice_preempted"; }
        if (frenzy_until) {
            if (!frenzy_web_) { Stop(now); return "voice_preempted"; }
            return "not_ready_or_busy";
        }
        if (const char* error = AudioActionGuard::Validate(target, move_ms, water_ms, direction, bubbles_ms, ignition_ms)) return error;
        // Cancel only conflicting queued voice work. Never resume it after web control ends.
        guard.CancelPending(target);
        bool preempted = false;
        if ((target & AudioActionGuard::MoveOnly) && guard.Moving() && !(web_targets_ & AudioActionGuard::MoveOnly)) {
            guard.StopMove(now); preempted = true;
        }
        if ((target & AudioActionGuard::WaterOnly) && guard.Watering() && !(web_targets_ & AudioActionGuard::WaterOnly)) {
            guard.StopWater(now); preempted = true;
        }
        if (target == AudioActionGuard::BubblesOnly && guard.Bubbling() && !(web_targets_ & AudioActionGuard::BubblesOnly)) {
            guard.StopBubbles(now); preempted = true;
        }
        if (target == AudioActionGuard::IgnitionOnly && guard.Igniting() && !(web_targets_ & AudioActionGuard::IgnitionOnly)) {
            guard.StopIgnition(now); preempted = true;
        }
        // Keep the configured operation interval; the user must press again after cooling, never queue a restart.
        if (preempted) return "voice_preempted";
        const char* result = guard.WebRequest(now, target, move_ms, water_ms, direction, bubbles_ms, ignition_ms);
        if (!std::strcmp(result, "accepted")) web_targets_ |= target;
        return result;
    }
    const char* Consume(uint64_t now, uint32_t session, uint32_t seq, uint32_t command_window, uint64_t max_age) {
        if (!Owns(session)) return "session_expired";
        if (!seq || seq <= sequence_) return "duplicate_request";
        sequence_ = seq; // Failed requests are consumed too; never retry an action.
        if (!window_valid_ || command_window != window || now < window_issued_ || now - window_issued_ >= max_age)
            return "stale_request";
        window_valid_ = false; // One command per device-issued window, including rejected commands.
        return nullptr;
    }
    uint64_t frenzy_started_ = 0;
    uint64_t heartbeat_ = 0, window_issued_ = 0, drive_until_ = 0, drive_started_ = 0;
    uint32_t generation_ = 0, sequence_ = 0;
    bool pressed_ = false, window_valid_ = false, frenzy_web_ = false;
};
