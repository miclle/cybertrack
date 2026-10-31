#pragma once
#include "action_guard.h"
#include "action_plan.h"
#include "show_draft.h"

// All methods run under the adapter mutex, including the 5 ms deadline tick.
// One expiring web session coexists with voice; active web lanes have priority.
class ControlSessions {
public:
    static constexpr uint64_t LeaseMs = 2000, WindowMs = 1500;
    static constexpr unsigned DriveLeaseMs = 600;
    struct EffectHold { uint32_t id = 0, renewal = 0; uint64_t started = 0, until = 0; };
    EffectHold water_hold, bubbles_hold;
    AudioActionGuard guard;
    ShowDraft draft;
    int web_speed_percent = 100;
    bool auto_avoidance_enabled = false; // Device-wide, reset only by reboot; shared with voice.
    bool plan_active = false;
    unsigned plan_step = 0, plan_count = 0;
    const char* plan_result = "idle";
    bool wifi = false, voice = false, shutdown = false;
    int voice_turn = 0;
    bool voice_turn_open = false, voice_turn_failed = false;
    bool voice_draft_unquantified = false;
    bool voice_action_unspecified = false;
    uint32_t owner = 0, window = 0;
    uint32_t drive_id = 0, drive_renewal = 0;
    uint64_t frenzy_until = 0;
    unsigned frenzy_duration_ms = 0;
    const char* FrenzySource() const { return !frenzy_until ? "none" : frenzy_web_ ? "web" : "voice"; }

    void Tick(uint64_t now, bool pressed, bool output_fault = false) {
        draft.Tick(now);
        if (output_fault) draft.Clear();
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
        if (guard.motion.clock_fault || guard.spray.clock_fault || guard.bubbles.clock_fault || guard.ignition.clock_fault) draft.Clear();
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
    void SetForwardBlocked(uint64_t now, bool blocked) {
        if (blocked && !guard.forward_blocked) guard.CancelPending(AudioActionGuard::MoveOnly);
        guard.forward_blocked = blocked;
        if (!blocked || !guard.Moving() || std::strcmp(guard.direction, "forward")) return;
        if (plan_active) { plan_active = false; plan_result = "obstacle_blocked"; }
        guard.StopMove(now);
        web_targets_ &= ~AudioActionGuard::MoveOnly;
        drive_id = drive_renewal = 0;
        window_valid_ = false;
    }
    void Stop(uint64_t now) {
        draft_read_ = false;
        draft.Clear();
        if (plan_active) { plan_active = false; plan_result = "cancelled"; }
        guard.Stop(now);
        web_targets_ = 0;
        window_valid_ = false;
        drive_id = drive_renewal = 0;
        water_hold = {}; bubbles_hold = {};
        frenzy_until = 0;
    }
    void VoiceLink(uint64_t now, bool online) {
        if (online != voice) AdvanceVoiceTurn(false);
        if (online && !voice) guard.NewVoiceSession();
        voice = online;
        if (!online) {
            draft_read_ = false;
            if (!draft.web_owner) draft.Clear();
            if ((plan_active && !plan_web_) || (frenzy_until && !frenzy_web_)) Stop(now);
            guard.CancelPending();
            if (plan_active && plan_web_) return;
            if (!(web_targets_ & AudioActionGuard::MoveOnly)) guard.StopMove(now);
            if (!(web_targets_ & AudioActionGuard::WaterOnly)) guard.StopWater(now);
            if (!(web_targets_ & AudioActionGuard::BubblesOnly)) guard.StopBubbles(now);
            if (!(web_targets_ & AudioActionGuard::IgnitionOnly)) guard.StopIgnition(now);
        }
    }
    void WifiLink(uint64_t now, bool online) {
        if (online != wifi) AdvanceVoiceTurn(false);
        wifi = online;
        if (!online) { voice = false; owner = 0; Stop(now); }
    }
    void Shutdown(uint64_t now) {
        AdvanceVoiceTurn(false);
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
        web_speed_percent = 100;
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
    const char* VoiceClaimError(AudioActionGuard::Target target) const {
        if (target == AudioActionGuard::SpeedMode) {
            if (!wifi) return "speed_rejected_wifi_offline: device Wi-Fi was offline at request time; no action started.";
            if (!voice) return "speed_rejected_voice_offline: device voice control link was offline at request time; no action started.";
            if (shutdown) return "speed_rejected_shutdown: device was shutting down at request time; no action started.";
            if (!guard.Moving()) return "speed_rejected_not_moving: no movement at request time; speed was not changed and no action started.";
        }
        return "Action request duplicate, channel busy or cooling, offline, queue full, or cancelled by web priority";
    }
    void AdvanceVoiceTurn(bool open) {
        const bool advanced = voice_turn < INT_MAX;
        if (advanced) ++voice_turn;
        voice_turn_open = advanced && open && wifi && voice && !shutdown;
        voice_turn_failed = false;
        voice_draft_unquantified = false;
        voice_action_unspecified = false;
        draft_read_ = false;
        guard.CancelPending(); // Keep active lanes and the session RPC replay table.
    }
    bool VoiceTurnReady(int turn) const {
        return turn > 0 && turn == voice_turn && voice_turn_open && !voice_turn_failed;
    }
    const char* VoiceTurnError(int turn) const {
        if (turn != voice_turn || !voice_turn_open) return "voice_input_changed: a new recognized input is required; no action started.";
        return "voice_input_failed: an earlier request in this input failed; no retry or replacement action is allowed; wait for a new user input.";
    }
    void FailVoiceTurn(int turn) {
        if (turn >= 0 && turn == voice_turn && voice_turn_open) {
            voice_turn_failed = true;
            draft_read_ = false;
            guard.CancelPending();
        }
    }
    int VoiceClaim(uint64_t now, int rpc, AudioActionGuard::Target target, int turn = -1) {
        if (turn >= 0 && !VoiceTurnReady(turn)) return 0;
        if (target == AudioActionGuard::SpeedMode)
            return wifi && voice && !shutdown ? guard.Claim(now, rpc, target) : 0;
        const unsigned lanes = (target == AudioActionGuard::FrenzyMode || target == AudioActionGuard::PlanMode) ? AudioActionGuard::All : target;
        return wifi && voice && !shutdown && !frenzy_until && !plan_active && !(web_targets_ & lanes) ? guard.Claim(now, rpc, target) : 0;
    }
    const char* WebAction(uint64_t now, uint32_t session, uint32_t seq, uint32_t command_window,
                          AudioActionGuard::Target target, int move_ms, int water_ms, const char* direction, int bubbles_ms = 0, int ignition_ms = 0) {
        const char* error = Consume(now, session, seq, command_window, WindowMs);
        if (error) return error;
        return StartWeb(now, target, move_ms, water_ms, direction, bubbles_ms, ignition_ms);
    }
    const char* WebAutoAvoidance(uint64_t now, uint32_t session, uint32_t seq, uint32_t command_window, bool enabled) {
        const char* error = Consume(now, session, seq, command_window, WindowMs);
        if (error) return error;
        auto_avoidance_enabled = enabled;
        return "ok";
    }
    const char* WebSpeed(uint64_t now, uint32_t session, uint32_t seq, uint32_t command_window, int speed) {
        const char* error = Consume(now, session, seq, command_window, WindowMs);
        if (error) return error;
        if (speed < 60 || speed > 100) return "invalid_speed";
        web_speed_percent = speed;
        // Only web-owned movement changes. No start, renewal, direction or deadline change.
        if ((web_targets_ & AudioActionGuard::MoveOnly) && guard.Moving()) guard.SetMoveSpeed(speed);
        return "ok";
    }
    const char* FrenzyStart(uint64_t now, uint32_t session, uint32_t seq, uint32_t command_window, int duration) {
        const char* error = Consume(now, session, seq, command_window, WindowMs);
        if (error) return error;
        if (plan_active) { const bool web_plan = plan_web_; Stop(now); return web_plan ? "show_cancelled" : "voice_preempted"; }
        if (frenzy_until) {
            if (!frenzy_web_) { Stop(now); return "voice_preempted"; }
            return "not_ready_or_busy";
        }
        const char* result = guard.Frenzy(now, duration, web_speed_percent);
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
    const char* VoiceSetSpeed(uint64_t now, int ticket, int speed) {
        if (!wifi || !voice || shutdown) return "not_ready_or_busy";
        const char* result = guard.SetSpeed(now, ticket, speed);
        if (!std::strcmp(result, "accepted") && (web_targets_ & AudioActionGuard::MoveOnly))
            web_speed_percent = speed;
        return result;
    }
    const char* VoiceAdjustSpeed(uint64_t now, int ticket, int delta) {
        if (!wifi || !voice || shutdown) return "not_ready_or_busy";
        const char* result = guard.AdjustSpeed(now, ticket, delta);
        if (!std::strcmp(result, "accepted") && (web_targets_ & AudioActionGuard::MoveOnly))
            web_speed_percent = guard.left < 0 ? -guard.left : guard.left;
        return result;
    }
    const char* VoicePlan(uint64_t now, int ticket, const ActionPlan& plan) {
        if (!plan.Valid()) return "invalid_plan";
        if (!wifi || !voice || shutdown || frenzy_until || plan_active || web_targets_) return "not_ready_or_busy";
        const char* result = guard.ClaimPlan(now, ticket);
        if (std::strcmp(result, "accepted")) return result;
        draft.Clear();
        plan_web_ = false;
        plan_ = plan;
        plan_step = 1; plan_count = plan.count; plan_active = true;
        guard.CancelPending();
        return StartPlanStep(now) ? "accepted" : plan_result;
    }
    const char* WebDraft(uint64_t now, uint32_t session, uint32_t seq, uint32_t command_window, const ShowDraft::Command& edit) {
        if (const char* error = Consume(now, session, seq, command_window, WindowMs)) return error;
        if (plan_active || frenzy_until || !guard.PlanReady(now)) return "not_ready_or_busy";
        return draft.Apply(now, edit, session);
    }
    void ObserveVoiceDraft(uint64_t now) {
        draft_read_ = wifi && voice && !shutdown;
        draft_read_at_ = now;
        draft_serial_ = draft.revision;
        draft_visible_ = draft.CurrentRevision();
    }
    const char* VoiceDraft(uint64_t now, int ticket, const ShowDraft::Command& edit) {
        if (!wifi || !voice || shutdown || plan_active || frenzy_until || web_targets_) return "not_ready_or_busy";
        const char* result = guard.ClaimPlan(now, ticket);
        if (std::strcmp(result, "accepted")) return result;
        const bool fresh = draft_read_ && now >= draft_read_at_ && now - draft_read_at_ < 30000 &&
            draft_serial_ == draft.revision && draft_visible_ == draft.CurrentRevision();
        draft_read_ = false;
        if (!fresh || edit.revision != draft_visible_) return "draft_changed";
        return draft.Apply(now, edit, 0);
    }
    const char* WebConfirm(uint64_t now, uint32_t session, uint32_t seq, uint32_t command_window, uint32_t revision) {
        if (const char* error = Consume(now, session, seq, command_window, WindowMs)) return error;
        ActionPlan confirmed;
        if (const char* error = draft.Take(now, revision, confirmed)) return error;
        if (plan_active || frenzy_until || !guard.PlanReady(now)) return "not_ready_or_busy";
        plan_ = confirmed;
        plan_web_ = true;
        plan_step = 1; plan_count = confirmed.count; plan_active = true;
        guard.CancelPending();
        return StartPlanStep(now) ? "accepted" : plan_result;
    }
    bool PlanStepActive() const {
        if (!plan_active || !plan_step || plan_step > plan_count) return false;
        const auto& step = plan_.steps[plan_step - 1];
        return (!step.move_ms || guard.Moving()) && (!step.water_ms || guard.Watering()) &&
               (!step.bubbles_ms || guard.Bubbling()) && (!step.ignition_ms || guard.Igniting());
    }
    const char* PlanSource() const { return !plan_active ? "none" : plan_web_ ? "web" : "voice"; }
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
    const char* MoveSource() const { return !guard.Moving() ? "none" : ((plan_active && plan_web_) || (web_targets_ & AudioActionGuard::MoveOnly)) ? "web" : "voice"; }
    const char* WaterSource() const { return !guard.Watering() ? "none" : ((plan_active && plan_web_) || (web_targets_ & AudioActionGuard::WaterOnly)) ? "web" : "voice"; }
    const char* BubblesSource() const { return !guard.Bubbling() ? "none" : ((plan_active && plan_web_) || (web_targets_ & AudioActionGuard::BubblesOnly)) ? "web" : "voice"; }
    const char* IgnitionSource() const { return !guard.Igniting() ? "none" : ((plan_active && plan_web_) || (web_targets_ & AudioActionGuard::IgnitionOnly)) ? "web" : "voice"; }
private:
    bool draft_read_ = false;
    uint64_t draft_read_at_ = 0;
    uint32_t draft_serial_ = 0, draft_visible_ = 0;
    ActionPlan plan_;
    bool plan_web_ = false;
    uint64_t plan_deadlines_[4] = {};
    uint64_t plan_last_tick_ = 0;
    bool StartPlanStep(uint64_t now) {
        const auto& step = plan_.steps[plan_step - 1];
        if (step.move_ms && guard.BlocksForward(step.direction)) {
            plan_active = false; plan_result = "obstacle_blocked"; return false;
        }
        const int durations[] = {step.move_ms, step.water_ms, step.bubbles_ms, step.ignition_ms};
        const AudioActionGuard::Target targets[] = {AudioActionGuard::MoveOnly, AudioActionGuard::WaterOnly,
                                                   AudioActionGuard::BubblesOnly, AudioActionGuard::IgnitionOnly};
        for (unsigned i = 0; i < 4; ++i) {
            plan_deadlines_[i] = 0;
            if (!durations[i]) continue;
            if (now > UINT64_MAX - static_cast<unsigned>(durations[i]) ||
                std::strcmp(guard.WebRequest(now, targets[i], step.move_ms, step.water_ms,
                                             step.direction, step.bubbles_ms, step.ignition_ms, step.speed_percent), "accepted")) {
                Stop(now); plan_result = "not_ready_or_busy"; return false;
            }
            if (plan_web_) web_targets_ |= targets[i];
            plan_deadlines_[i] = now + static_cast<unsigned>(durations[i]);
        }
        plan_last_tick_ = now;
        plan_result = "running";
        return true;
    }
    void TickPlan(uint64_t now, bool output_fault) {
        if (!plan_active) return;
        if (!wifi || (plan_web_ ? !owner : !voice) || shutdown || output_fault || now < plan_last_tick_ ||
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
        if (draft.web_owner) draft.Clear();
        if (plan_active && plan_web_) { Stop(now); return; }
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
        if ((target & AudioActionGuard::MoveOnly) && guard.BlocksForward(direction)) return "obstacle_blocked";
        if (plan_active) { const bool web_plan = plan_web_; Stop(now); return web_plan ? "show_cancelled" : "voice_preempted"; }
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
        const char* result = guard.WebRequest(now, target, move_ms, water_ms, direction, bubbles_ms, ignition_ms, web_speed_percent);
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
