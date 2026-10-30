#pragma once
#include "action_plan.h"

// Fixed-memory proposal only. No method in this type can start an output.
class ShowDraft {
public:
    static constexpr uint64_t LifetimeMs = 300000;
    enum Edit { Replace, ReplaceStep, RemoveStep, Cancel };
    struct Command {
        Edit edit = Replace;
        uint32_t revision = 0;
        unsigned step = 0; // One-based for single-step editing.
        ActionPlan plan;
    };
    bool active = false;
    uint32_t revision = 0, web_owner = 0;
    uint64_t updated_at = 0;
    ActionPlan plan;
    static bool Valid(const ActionPlan& value) {
        if (!value.Valid()) return false;
        for (unsigned i = 0; i < value.count; ++i)
            if (value.steps[i].water_ms || value.steps[i].ignition_ms) return false;
        return true;
    }
    void Clear() { active = false; plan = {}; web_owner = 0; }
    void Tick(uint64_t now) {
        if (active && (now < updated_at || now - updated_at >= LifetimeMs)) Clear();
    }
    uint32_t CurrentRevision() const { return active ? revision : 0; }
    uint64_t Remaining(uint64_t now) const {
        return active && now >= updated_at && now - updated_at < LifetimeMs ? LifetimeMs - (now - updated_at) : 0;
    }
    const char* Apply(uint64_t now, const Command& command, uint32_t owner) {
        Tick(now);
        if (command.revision != CurrentRevision()) return "draft_changed";
        if (command.edit == Cancel) { Clear(); return "draft_cancelled"; }
        ActionPlan next = command.plan;
        if (command.edit != Replace) {
            if (!active || command.step < 1 || command.step > plan.count) return "invalid_step";
            next = plan;
            if (command.edit == ReplaceStep) {
                if (command.plan.count != 1) return "invalid_plan";
                next.steps[command.step - 1] = command.plan.steps[0];
            } else if (command.edit == RemoveStep) {
                for (unsigned i = command.step; i < next.count; ++i) next.steps[i - 1] = next.steps[i];
                --next.count;
            } else return "invalid_request";
        }
        if (!Valid(next)) return "invalid_plan";
        if (revision == INT_MAX) return "draft_exhausted";
        plan = next; active = true; ++revision; updated_at = now; web_owner = owner;
        return "draft_saved";
    }
    const char* Take(uint64_t now, uint32_t expected, ActionPlan& result) {
        Tick(now);
        if (!active || !expected || expected != revision) return "draft_changed";
        result = plan;
        Clear(); // A matching confirmation consumes the draft even if execution is rejected.
        return nullptr;
    }
};
