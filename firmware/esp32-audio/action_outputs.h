#pragma once
#include <driver/gpio.h>
#include <driver/ledc.h>
#include <climits>

// Serialized by the adapter's priority-inheriting mutex, never a spinlock:
// LEDC driver APIs may acquire their own RTOS locks.
class AudioActionOutputs {
public:
    static constexpr gpio_num_t WaterPin = GPIO_NUM_18;
    static constexpr gpio_num_t BubblesPin = GPIO_NUM_17; // Board-config free; physical wiring pending.
    static constexpr gpio_num_t IgnitionPin = GPIO_NUM_21; // One MOS for both modules; wiring pending.
    static constexpr unsigned Duty = 255; // Full 8-bit PWM is the default.
    static unsigned SpeedDuty(int value) { return ((value < 0 ? -value : value) * Duty + 50) / 100; }
    bool fault = false;
    // Digital pad observations, not voltage/current or water-flow feedback.
    // Sampled after successful output application; counters saturate on long holds.
    struct WaterPadTrace {
        unsigned high = 0, low = 0, motor_high = 0, motor_low = 0;
        int first = -1, last = -1, off = -1;
        static void Increment(unsigned& count) { if (count != UINT_MAX) ++count; }
        void Sample(int level, bool moving) {
            if (first < 0) first = level;
            last = level;
            Increment(level ? high : low);
            if (moving) Increment(level ? motor_high : motor_low);
        }
    } water_pad;
    int WaterPadLevel() const { return water_input_ready ? gpio_get_level(WaterPin) : -1; }
    bool Init() {
        uint64_t mask = (1ULL << WaterPin) | (1ULL << BubblesPin) | (1ULL << IgnitionPin);
        for (const auto& b : bridges) {
            mask |= (1ULL << b.enable) | (1ULL << b.in1) | (1ULL << b.in2);
            if (!Check(gpio_set_level(b.enable, 0)) || !Check(gpio_set_level(b.in1, 0)) ||
                !Check(gpio_set_level(b.in2, 0))) return false;
        }
        if (!Check(gpio_set_level(WaterPin, 0)) || !Check(gpio_set_level(BubblesPin, 0)) || !Check(gpio_set_level(IgnitionPin, 0))) return false;
        gpio_config_t pins{};
        pins.pin_bit_mask = mask; pins.mode = GPIO_MODE_OUTPUT;
        pins.pull_down_en = GPIO_PULLDOWN_ENABLE;
        if (!Check(gpio_config(&pins))) return false;
        // Preserve output mode and routing. gpio_get_level otherwise always reads 0.
        if (!Check(gpio_input_enable(WaterPin))) return false;
        water_input_ready = true;
        ledc_timer_config_t timer{};
        timer.speed_mode = LEDC_LOW_SPEED_MODE; timer.duty_resolution = LEDC_TIMER_8_BIT;
        timer.timer_num = LEDC_TIMER_2; timer.freq_hz = 1000; timer.clk_cfg = LEDC_AUTO_CLK;
        if (!Check(ledc_timer_config(&timer))) return false;
        for (unsigned i = 0; i < 2; ++i) {
            ledc_channel_config_t channel{};
            channel.gpio_num = bridges[i].enable; channel.speed_mode = LEDC_LOW_SPEED_MODE;
            channel.channel = bridges[i].channel; channel.timer_sel = LEDC_TIMER_2; channel.duty = 0;
            // Include a partially configured channel in fault cleanup.
            ready_mask |= 1u << i;
            if (!Check(ledc_channel_config(&channel))) return false;
        }
        return Apply(false, 0, 0);
    }
    bool Apply(bool water, int left, int right, bool bubbles = false, bool ignition = false) {
        if (fault) { EmergencyOff(); return false; }
        if (left < -100 || left > 100 || right < -100 || right > 100 ||
            (left != 0 && left > -60 && left < 60) || (right != 0 && right > -60 && right < 60)) return Check(-1);
        // Change only requested lanes; stopping any one must not pulse the others.
        if ((!applied || ignition != ignition_on) && !ignition && !Check(gpio_set_level(IgnitionPin, 0))) return false;
        // Touch only the changing lane: starting/stopping water must not pulse
        // motor enables, and motor transitions must not interrupt water.
        if (!applied || left != applied_left || right != applied_right) {
            const int values[] = {left, right}, previous[] = {applied_left, applied_right};
            auto sign = [](int n) { return (n > 0) - (n < 0); };
            const bool direction_change = !applied || sign(left) != sign(applied_left) || sign(right) != sign(applied_right);
            // Disable both bridges before direction changes. Same-direction speed changes
            // update duty in place and never pulse motor enables or effect lanes.
            if (direction_change) {
                bool ok = true;
                for (const auto& b : bridges) ok = (ledc_stop(LEDC_LOW_SPEED_MODE, b.channel, 0) == ESP_OK) && ok;
                if (!ok) return Check(-1);
            }
            for (unsigned i = 0; i < 2; ++i) {
                const auto& b = bridges[i];
                if (direction_change && (!Check(gpio_set_level(b.in1, values[i] > 0)) ||
                    !Check(gpio_set_level(b.in2, values[i] < 0)))) return false;
                if (values[i] && (direction_change || values[i] != previous[i]) &&
                    !Check(ledc_set_duty(LEDC_LOW_SPEED_MODE, b.channel, SpeedDuty(values[i])))) return false;
            }
            for (unsigned i = 0; i < 2; ++i)
                if (values[i] && (direction_change || values[i] != previous[i]) && !Check(ledc_update_duty(LEDC_LOW_SPEED_MODE, bridges[i].channel))) return false;
        }
        if ((!applied || water != water_on) && !Check(gpio_set_level(WaterPin, water))) return false;
        if ((!applied || bubbles != bubbles_on) && !Check(gpio_set_level(BubblesPin, bubbles))) return false;
        if ((!applied || ignition != ignition_on) && ignition && !Check(gpio_set_level(IgnitionPin, 1))) return false;
        if (water) {
            if (!water_on) water_pad = {};
            water_pad.Sample(WaterPadLevel(), left != 0 || right != 0);
        } else {
            water_pad.off = WaterPadLevel();
        }
        ignition_on = ignition;
        bubbles_on = bubbles;
        water_on = water; applied_left = left; applied_right = right; applied = true;
        return true;
    }
private:
    struct Bridge { gpio_num_t enable, in1, in2; ledc_channel_t channel; };
    // Logical left/right order. Assembly feedback: forward/backward work,
    // but turns are reversed with the former A/left, B/right assignment.
    static constexpr Bridge bridges[] = {
        {GPIO_NUM_11, GPIO_NUM_12, GPIO_NUM_13, LEDC_CHANNEL_3}, // B / left
        {GPIO_NUM_8, GPIO_NUM_9, GPIO_NUM_10, LEDC_CHANNEL_2},  // A / right
    };
    unsigned ready_mask = 0;
    bool water_input_ready = false;
    bool water_on = false, bubbles_on = false, ignition_on = false, applied = false;
    int applied_left = 0, applied_right = 0;
    bool Check(esp_err_t error) {
        if (error == ESP_OK) return true;
        fault = true; EmergencyOff(); return false;
    }
    void EmergencyOff() {
        // Best effort after an API error: try every output, then reclaim enables
        // as GPIO low. A latched fault prevents any later PWM reactivation.
        (void)gpio_set_level(IgnitionPin, 0);
        (void)gpio_set_level(WaterPin, 0);
        (void)gpio_set_level(BubblesPin, 0);
        for (unsigned i = 0; i < 2; ++i)
            if (ready_mask & (1u << i)) (void)ledc_stop(LEDC_LOW_SPEED_MODE, bridges[i].channel, 0);
        for (const auto& b : bridges) {
            (void)gpio_set_level(b.enable, 0);
            (void)gpio_set_direction(b.enable, GPIO_MODE_OUTPUT);
            (void)gpio_set_level(b.in1, 0);
            (void)gpio_set_level(b.in2, 0);
        }
        water_pad.off = WaterPadLevel();
    }
};
