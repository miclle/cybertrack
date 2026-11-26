// Exercise the production A4 output driver, admission and rearm task against
// modeled U10/U27 and TCA9539 registers. All time advances are explicit.
#include "action_outputs.h"
#include "a4_interlock.h"
#include "control_sessions.h"
#include "proximity_guard.h"
#include <array>
#include <cassert>
#include <vector>

AudioActionOutputs outputs;
ControlSessions sessions;
auto& guard = sessions.guard;
ProximityGuard proximity;
constexpr int arm_feedback = 38, arm_clock = 45, GPIO_NUM_14 = 14, stop_pin = 0;
bool actuator_armed = false;
A4Interlock interlock;

uint64_t now_ms = 0;
uint64_t Now() { return now_ms; }
int64_t esp_timer_get_time() { return now_ms * 1000; }

std::array<int, 49> pads{};
std::array<unsigned, 4> duty{}, pwm{};
std::array<uint8_t, 8> regs{0, 0, 0xff, 0xff, 0, 0, 0xff, 0xff};
std::vector<uint64_t> clocks;
bool contact = true, vm_good = false, driver_a_ok = true, driver_b_ok = true;
bool powered = false, permitted = false, boot_pressed = false, nack = false;
uint8_t pressed_keys = 0;
bool fault_during_write = false;

void hardware_clear() {
    if (!contact) powered = false;
    if (!powered || !vm_good || !driver_a_ok || !driver_b_ok) permitted = false;
}
void raw_off() {
    assert(!pwm[2] && !pwm[3] && !pads[14] && !pads[17] && !pads[18]);
}
int gpio_get_level(int pin) {
    if (pin == arm_feedback) return permitted;
    if (pin == stop_pin) return !boot_pressed;
    assert(pin == 18);
    return pads[pin];
}
esp_err_t gpio_set_level(int pin, uint32_t value) {
    assert(pin == arm_clock || pin == 14 || pin == 17 || pin == 18 || pin == 8 || pin == 11);
    if (pin == arm_clock && value) {
        raw_off();
        assert(regs[2] == 0 && regs[6] == 0xf0 && !boot_pressed && !outputs.fault);
        assert(clocks.empty() || now_ms >= clocks.back() + 100);
        clocks.push_back(now_ms);
        permitted = powered && contact && vm_good && driver_a_ok && driver_b_ok;
        powered = contact;
    }
    pads[pin] = value;
    return ESP_OK;
}
esp_err_t gpio_config(const gpio_config_t* config) {
    assert(config->pin_bit_mask == ((1ULL<<8) | (1ULL<<11) | (1ULL<<17) | (1ULL<<18)));
    return ESP_OK;
}
esp_err_t gpio_set_direction(int pin, int) { assert(pin == 8 || pin == 11); return ESP_OK; }
esp_err_t gpio_input_enable(int pin) { assert(pin == 18); return ESP_OK; }
esp_err_t ledc_timer_config(const ledc_timer_config_t*) { return ESP_OK; }
esp_err_t ledc_channel_config(const ledc_channel_config_t* config) {
    assert((config->gpio_num == 8 && config->channel == 2) || (config->gpio_num == 11 && config->channel == 3));
    return ESP_OK;
}
esp_err_t ledc_stop(int, int channel, uint32_t) { pwm[channel] = 0; return ESP_OK; }
esp_err_t ledc_set_duty(int, int channel, uint32_t value) { duty[channel] = value; return ESP_OK; }
esp_err_t ledc_update_duty(int, int channel) {
    assert(permitted && regs[6] == 0xf0);
    pwm[channel] = duty[channel];
    return ESP_OK;
}
esp_err_t i2c_master_get_bus_handle(int id, void** bus) { assert(id == 0); *bus = &regs; return ESP_OK; }
esp_err_t i2c_master_bus_add_device(void* bus, const i2c_device_config_t* config, void** device) {
    assert(bus == &regs && config->device_address == 0x74 && config->scl_speed_hz == 400000);
    *device = bus;
    return ESP_OK;
}
esp_err_t i2c_master_transmit(void* device, const uint8_t* data, size_t size, int timeout) {
    assert(device == &regs && size == 2 && timeout == 20);
    if (nack) return ESP_FAIL;
    if (data[0] == 2) assert(!pwm[2] && !pwm[3]);
    if (data[0] == 6) assert(regs[2] == 0);
    regs.at(data[0]) = data[1];
    if (fault_during_write && data[0] == 2 && data[1]) {
        driver_b_ok = false;
        hardware_clear();
        driver_b_ok = true;
        fault_during_write = false;
    }
    return ESP_OK;
}
esp_err_t i2c_master_transmit_receive(void* device, const uint8_t* reg, size_t tx, uint8_t* value, size_t rx, int timeout) {
    assert(device == &regs && tx == 1 && rx == 1 && timeout == 20);
    if (nack) return ESP_FAIL;
    *value = *reg == 0 ? static_cast<uint8_t>((0xf0 & ~pressed_keys) | (regs[2] & 15)) : regs.at(*reg);
    return ESP_OK;
}

ultrasonic::Reading CyberTrackDistanceSnapshot() { return {}; }
void CyberTrackProximityAlert(ProximityGuard::Alert, bool) {}
void ApplyLocked(uint64_t now) {
    if (!outputs.Apply(guard.Watering(), guard.Moving() ? guard.left : 0,
                       guard.Moving() ? guard.right : 0, guard.Bubbling())) sessions.Stop(now);
}
#include "proximity_tick.inc"
void tick(unsigned elapsed = 5, bool poll = true) {
    now_ms += elapsed;
    if (poll) a4_io::Poll();
#include "safety_tick.inc"
}

int main(int argc, char** argv) {
    assert(outputs.Init() && !permitted && regs[7] == 0xff);
    sessions.WifiLink(now_ms, true);
    sessions.VoiceLink(now_ms, true);
    tick(99); assert(clocks.empty());
    tick(); assert(powered && !permitted);
    tick(200); assert(!permitted && !guard.motion.online); // Slow 12 V rise.
    vm_good = true;
    tick(99); assert(!permitted);
    tick(); tick(); assert(permitted && !guard.motion.online);
    tick(); assert(guard.motion.online);
    pressed_keys = 1U << 4;
    tick(20); assert(!(a4_io::inputs.load() & pressed_keys));
    for (int cause = 0; cause < 4; ++cause) {
        tick(2000);
        auto owner = sessions.Acquire(now_ms);
        assert(sessions.Heartbeat(now_ms, owner));
        assert(!std::strcmp(sessions.DriveStart(now_ms, owner, 1, sessions.window, "forward", 500), "accepted"));
        auto old_hold = sessions.drive_id;
        sessions.AdvanceVoiceTurn(true);
        auto old_turn = sessions.voice_turn;
        tick(); assert(pwm[2] && pwm[3] && regs[2] == 5 && pads[18]);
        driver_a_ok = cause != 0; driver_b_ok = cause != 1;
        vm_good = cause != 2; contact = cause != 3;
        hardware_clear(); assert(!permitted && pwm[2] && pwm[3]);
        tick(); raw_off();
        assert(!sessions.Owns(owner) && !sessions.VoiceTurnReady(old_turn) && regs[2] == 0);
        tick(150); assert(!permitted);  // Fault still active at a rearm edge.
        driver_a_ok = driver_b_ok = vm_good = contact = true;
        boot_pressed = true; tick(200); assert(!permitted);
        boot_pressed = false; tick();
        tick(100); tick(); tick();
        assert(permitted && actuator_armed); raw_off();
        assert(std::strcmp(sessions.DriveRenew(now_ms, owner, old_hold, 1), "renewed"));
    }
    // Trip and clear entirely between CPU samples while a voice sequence is queued.
    tick(2000);
    sessions.AdvanceVoiceTurn(true);
    ActionPlan plan{};
    plan.count = 2;
    plan.steps[0].water_ms = 1000;
    plan.steps[1].move_ms = 500;
    plan.steps[1].direction = "forward";
    auto ticket = sessions.VoiceClaim(now_ms, 42, AudioActionGuard::PlanMode);
    assert(!std::strcmp(sessions.VoicePlan(now_ms, ticket, plan), "accepted"));
    tick(); assert(guard.Watering() && sessions.plan_active);
    driver_a_ok = false; hardware_clear(); driver_a_ok = true;
    assert(!permitted);
    tick(); raw_off(); assert(!sessions.plan_active);
    tick(110); tick(); tick(2000); raw_off();
    fault_during_write = true;
    assert(!outputs.Apply(true, 100, 100) && !outputs.fault && !permitted && regs[2] == 0);
    raw_off();
    tick(); tick(100); tick(); tick();
    // Verify independent direction bits at the driver boundary.
    assert(outputs.Apply(false, 100, -60) && regs[2] == 6);
    assert(outputs.Apply(false, -60, 100) && regs[2] == 9);
    assert(outputs.Apply(false, 0, 0) && regs[2] == 0);
    auto owner = sessions.Acquire(now_ms);
    assert(sessions.Heartbeat(now_ms, owner));
    assert(!std::strcmp(sessions.DriveStart(now_ms, owner, 1, sessions.window, "forward", 0), "accepted"));
    tick(); assert(pwm[2] && pwm[3]);
    if (argc > 1 && !std::strcmp(argv[1], "reset")) regs[6] = 0xff;
    else if (argc > 1 && !std::strcmp(argv[1], "mismatch")) regs[2] ^= 1;
    else if (argc > 1 && !std::strcmp(argv[1], "stalled")) { tick(101, false); }
    else nack = true;
    tick(20); assert(outputs.fault && !sessions.Owns(owner)); raw_off();
    auto edges = clocks.size();
    nack = false; tick(2000); assert(clocks.size() == edges); raw_off();
}
