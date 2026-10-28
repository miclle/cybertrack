#pragma once
#include <cstdint>
using esp_err_t = int;
using gpio_num_t = int;
using ledc_channel_t = int;
constexpr int ESP_OK=0, GPIO_MODE_OUTPUT=1, GPIO_PULLDOWN_ENABLE=1;
constexpr int GPIO_NUM_8=8, GPIO_NUM_9=9, GPIO_NUM_10=10, GPIO_NUM_11=11,
              GPIO_NUM_12=12, GPIO_NUM_13=13, GPIO_NUM_18=18, GPIO_NUM_17=17, GPIO_NUM_21=21;
constexpr int LEDC_LOW_SPEED_MODE=0, LEDC_TIMER_8_BIT=8, LEDC_TIMER_2=2,
              LEDC_CHANNEL_2=2, LEDC_CHANNEL_3=3, LEDC_AUTO_CLK=0;
struct gpio_config_t { uint64_t pin_bit_mask; int mode, pull_down_en; };
struct ledc_timer_config_t { int speed_mode, duty_resolution, timer_num, freq_hz, clk_cfg; };
struct ledc_channel_config_t { int gpio_num, speed_mode, channel, timer_sel, duty; };
esp_err_t gpio_set_level(gpio_num_t, uint32_t);
esp_err_t gpio_set_direction(gpio_num_t, int);
esp_err_t gpio_config(const gpio_config_t*);
esp_err_t gpio_input_enable(gpio_num_t);
int gpio_get_level(gpio_num_t);
esp_err_t ledc_timer_config(const ledc_timer_config_t*);
esp_err_t ledc_channel_config(const ledc_channel_config_t*);
esp_err_t ledc_stop(int, ledc_channel_t, uint32_t);
esp_err_t ledc_set_duty(int, ledc_channel_t, uint32_t);
esp_err_t ledc_update_duty(int, ledc_channel_t);
