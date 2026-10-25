#pragma once
#include <driver/gpio.h>
#include <driver/ledc.h>

// Serialized by the adapter's priority-inheriting mutex, never a spinlock:
// LEDC driver APIs may acquire their own RTOS locks.
class AudioActionOutputs {
public:
    static constexpr gpio_num_t WaterPin = GPIO_NUM_18;
    static constexpr unsigned Duty = 154; // ~60%, 8 bit, same as the tested bench.
    bool fault = false;
    bool Init() {
        uint64_t mask = 1ULL << WaterPin;
        for (const auto& b : bridges) {
            mask |= (1ULL << b.enable) | (1ULL << b.in1) | (1ULL << b.in2);
            if (!Check(gpio_set_level(b.enable, 0)) || !Check(gpio_set_level(b.in1, 0)) ||
                !Check(gpio_set_level(b.in2, 0))) return false;
        }
        if (!Check(gpio_set_level(WaterPin, 0))) return false;
        gpio_config_t pins{};
        pins.pin_bit_mask = mask; pins.mode = GPIO_MODE_OUTPUT;
        pins.pull_down_en = GPIO_PULLDOWN_ENABLE;
        if (!Check(gpio_config(&pins))) return false;
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
    bool Apply(bool water, int left, int right) {
        if (fault) { EmergencyOff(); return false; }
        if ((water && (left || right)) || (left != 0 && left != 60 && left != -60) ||
            (right != 0 && right != 60 && right != -60)) return Check(-1);
        if (water == water_on && left == applied_left && right == applied_right && applied) return true;
        // Disable BOTH bridges and water before altering any direction.
        bool ok = gpio_set_level(WaterPin, 0) == ESP_OK;
        for (const auto& b : bridges) ok = (ledc_stop(LEDC_LOW_SPEED_MODE, b.channel, 0) == ESP_OK) && ok;
        if (!ok) return Check(-1);
        const int values[] = {left, right};
        for (unsigned i = 0; i < 2; ++i) {
            const auto& b = bridges[i];
            if (!Check(gpio_set_level(b.in1, values[i] > 0)) ||
                !Check(gpio_set_level(b.in2, values[i] < 0))) return false;
            if (values[i] && !Check(ledc_set_duty(LEDC_LOW_SPEED_MODE, b.channel, Duty))) return false;
        }
        for (unsigned i = 0; i < 2; ++i)
            if (values[i] && !Check(ledc_update_duty(LEDC_LOW_SPEED_MODE, bridges[i].channel))) return false;
        if (!Check(gpio_set_level(WaterPin, water))) return false;
        water_on = water; applied_left = left; applied_right = right; applied = true;
        return true;
    }
private:
    struct Bridge { gpio_num_t enable, in1, in2; ledc_channel_t channel; };
    static constexpr Bridge bridges[] = {
        {GPIO_NUM_8, GPIO_NUM_9, GPIO_NUM_10, LEDC_CHANNEL_2},  // A / left candidate
        {GPIO_NUM_11, GPIO_NUM_12, GPIO_NUM_13, LEDC_CHANNEL_3}, // B / right candidate
    };
    unsigned ready_mask = 0;
    bool water_on = false, applied = false;
    int applied_left = 0, applied_right = 0;
    bool Check(esp_err_t error) {
        if (error == ESP_OK) return true;
        fault = true; EmergencyOff(); return false;
    }
    void EmergencyOff() {
        // Best effort after an API error: try every output, then reclaim enables
        // as GPIO low. A latched fault prevents any later PWM reactivation.
        (void)gpio_set_level(WaterPin, 0);
        for (unsigned i = 0; i < 2; ++i)
            if (ready_mask & (1u << i)) (void)ledc_stop(LEDC_LOW_SPEED_MODE, bridges[i].channel, 0);
        for (const auto& b : bridges) {
            (void)gpio_set_level(b.enable, 0);
            (void)gpio_set_direction(b.enable, GPIO_MODE_OUTPUT);
            (void)gpio_set_level(b.in1, 0);
            (void)gpio_set_level(b.in2, 0);
        }
    }
};
