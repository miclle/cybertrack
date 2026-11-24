// Run the production safety-task iteration with a model of U10's asynchronous clear.
#include "control_sessions.h"
#include "proximity_guard.h"
#include <cassert>

using G = AudioActionGuard;
ControlSessions sessions;
auto& guard = sessions.guard;
ProximityGuard proximity;
struct { bool fault = false; } outputs;
constexpr int arm_feedback = 38, arm_clock = 45, GPIO_NUM_14 = 14, stop_pin = 0, ESP_OK = 0;
bool actuator_armed = false, latch = false, run_contact = false;
bool active_pads = false, aux = false;
uint64_t tick_ms = 0;
uint64_t Now() { return tick_ms; }
int gpio_get_level(int pin) { return pin == arm_feedback ? latch : 1; }
int gpio_set_level(int pin, int level) {
    if (pin == GPIO_NUM_14) aux = level;
    if (pin == arm_clock && level) {
        assert(!active_pads && !aux);
        latch = run_contact;
    }
    return ESP_OK;
}
ultrasonic::Reading CyberTrackDistanceSnapshot() { return {}; }
void CyberTrackProximityAlert(ProximityGuard::Alert, bool) {}
void ApplyLocked(uint64_t) { active_pads = guard.Moving() || guard.Watering() || guard.Bubbling(); }
#include "proximity_tick.inc"
#include "off_reason.inc"
void safety_tick() {
    tick_ms += 5;
#include "safety_tick.inc"
}

int main() {
    sessions.WifiLink(0, true);
    sessions.VoiceLink(0, true);
    safety_tick();
    assert(!latch && !guard.motion.online);
    run_contact = true;
    safety_tick();
    safety_tick();
    assert(actuator_armed && guard.motion.online);
    auto owner = sessions.Acquire(tick_ms);
    assert(sessions.Heartbeat(tick_ms, owner));
    sessions.AdvanceVoiceTurn(true);
    auto turn = sessions.voice_turn;
    auto ticket = sessions.VoiceClaim(tick_ms, 2, G::BubblesOnly);
    assert(ticket > 0 && sessions.VoiceTurnReady(turn));
    assert(!std::strcmp(guard.MoveAndWater(tick_ms, sessions.VoiceClaim(tick_ms, 3, G::Both),
                                          1000, 1000, "forward"), "accepted"));
    safety_tick();
    assert(latch && active_pads);

    // Both contact transitions occur between samples. U10 retains the trip.
    run_contact = false;
    latch = false;
    run_contact = true;
    assert(!latch && active_pads);
    safety_tick();
    assert(latch && !active_pads && !sessions.Owns(owner) && !sessions.VoiceTurnReady(turn));
    assert(!std::strcmp(OffReason("move", guard.motion), "actuator_disarmed"));
    assert(!std::strcmp(OffReason("water", guard.spray), "actuator_disarmed"));
    safety_tick();
    assert(actuator_armed && !active_pads);
    assert(std::strcmp(guard.Bubbles(tick_ms, ticket, 1000), "accepted"));
    assert(!std::strcmp(guard.Bubbles(tick_ms, sessions.VoiceClaim(tick_ms, 4, G::BubblesOnly),
                                     1000), "accepted"));
    latch = false;
    outputs.fault = true;
    safety_tick();
    assert(!latch && !active_pads);
    assert(!std::strcmp(OffReason("bubbles", guard.bubbles), "output_fault"));
    outputs.fault = false;
    safety_tick();
    safety_tick();
    sessions.WifiLink(tick_ms, false);
    safety_tick();
    assert(actuator_armed && !std::strcmp(OffReason("move", guard.motion), "link_lost"));
}
