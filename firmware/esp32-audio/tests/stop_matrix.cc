// Controlled-clock adapter for the stop-v1 field matrix. No board I/O.
#include "control_sessions.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <string>

using G = AudioActionGuard;
int main(int argc, char** argv) {
    if (argc != 5) return 2;
    const std::string event = argv[1], source = argv[2], phase = argv[3];
    const unsigned offset = std::stoul(argv[4]);
    const bool sequence = event == "cancel" || event == "source_disconnect" || event == "sequence_control" || event == "sequence_web_blackout";
    const unsigned trigger = offset + (phase == "waiting" ? 1000 : 0);
    const unsigned reconnect = trigger + 2500;
    ControlSessions s;
    s.WifiLink(0, true);
    s.VoiceLink(0, true);
    s.Tick(0, false);
    auto owner = s.Acquire(0);
    assert(owner && s.Heartbeat(0, owner));
    if (sequence) {
        ActionPlan plan;
        plan.count = 2;
        plan.steps[0] = {"forward", 1000, 0, 1000, 0};
        plan.steps[1] = {"none", 0, 0, 4000, 0};
        if (source == "web") {
            ShowDraft::Command edit;
            edit.plan = plan;
            assert(!std::strcmp(s.WebDraft(0, owner, 1, s.window, edit), "draft_saved"));
            assert(s.Heartbeat(0, owner));
            assert(!std::strcmp(s.WebConfirm(0, owner, 2, s.window, s.draft.revision), "accepted"));
        } else {
            assert(!std::strcmp(s.VoicePlan(0, s.VoiceClaim(0, 1, G::PlanMode), plan), "accepted"));
        }
    } else if (event == "pointer_release") {
        const auto result = source == "move" ? s.DriveStart(0, owner, 1, s.window, "forward", 0)
            : s.EffectStart(0, owner, 1, s.window, source == "water" ? G::WaterOnly : G::BubblesOnly);
        assert(!std::strcmp(result, "accepted"));
    } else {
        assert(!std::strcmp(s.WebAction(0, owner, 1, s.window, G::MoveOnly, 6000, 0, "forward"), "accepted"));
        assert(!std::strcmp(s.guard.Bubbles(0, s.VoiceClaim(0, 1, G::BubblesOnly), 5000), "accepted"));
    }

    bool web_connected = true;
    for (unsigned now = 0; now <= reconnect + 6000; now += 5) {
        if (now == trigger) {
            if (event == "global_stop" || event == "cancel") s.Stop(now);
            else if (event == "voice_disconnect" || (event == "source_disconnect" && source == "voice")) s.VoiceLink(now, false);
            else if (event == "wifi_disconnect") { web_connected = false; s.WifiLink(now, false); }
            else if (event == "web_network_loss" || event == "sequence_web_blackout") web_connected = false; // No release packet.
            else if (event == "page_hidden" || (event == "source_disconnect" && source == "web")) {
                web_connected = false;
                assert(s.Release(now, owner)); // Page's release was delivered.
            } else if (event == "pointer_release") {
                const auto result = source == "move" ? s.DriveStop(now, owner, 1)
                    : s.EffectStop(now, owner, source == "water" ? G::WaterOnly : G::BubblesOnly, 1);
                assert(!std::strcmp(result, "ok"));
            } else if (event != "boot" && event != "sequence_control") return 2;
        }
        if (now == reconnect) {
            if (!s.wifi) s.WifiLink(now, true);
            if (!s.voice) s.VoiceLink(now, true);
            if (!s.owner) owner = s.Acquire(now);
            web_connected = true;
            assert(owner && s.Heartbeat(now, owner));
        }
        s.Tick(now, event == "boot" && now >= trigger && now < trigger + 50);
        if (web_connected && now % 200 == 0) assert(s.Heartbeat(now, owner));
        std::printf("%u %s %s %s %d %s %u %u %d %d %d\n", now, s.MoveSource(), s.WaterSource(), s.BubblesSource(),
                    s.plan_active, s.plan_result, s.guard.Starts(), s.owner, s.guard.Igniting(), s.wifi, s.voice);
    }
}
