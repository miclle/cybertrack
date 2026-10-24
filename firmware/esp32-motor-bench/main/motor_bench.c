#include <stdio.h>
#include "bench_policy.h"
#include "driver/gpio.h"
#include "driver/ledc.h"
#include "driver/uart.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

enum { ENABLE_GPIO = GPIO_NUM_4, DIRECTION_GPIO = GPIO_NUM_5,
       STOP_GPIO = GPIO_NUM_0, POLL_MS = 5, RELEASE_MS = 30,
       PWM_HZ = 1000, PWM_DUTY = 102 }; /* 102 / 256 ~= 40%, 8 bits */
static bool pwm_ready;

static uint64_t now_ms(void)
{
    return (uint64_t)esp_timer_get_time() / 1000;
}

static void all_off(void)
{
    if (pwm_ready) (void)ledc_stop(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, 0);
    /* Reclaim the GPIO as well, including when LEDC initialization failed. */
    (void)gpio_set_level(ENABLE_GPIO, 0);
    (void)gpio_set_direction(ENABLE_GPIO, GPIO_MODE_OUTPUT);
    (void)gpio_set_level(DIRECTION_GPIO, 0);
}

static void require_ok(esp_err_t result)
{
    if (result == ESP_OK) return;
    all_off();
    printf("BENCH ERROR %s; outputs disabled; disconnect driver power before reset.\n",
           esp_err_to_name(result));
    /* Remain off rather than auto-restarting the bench. */
    for (;;) {
        (void)esp_task_wdt_reset();
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

static void pwm_off(void)
{
    require_ok(ledc_stop(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, 0));
    require_ok(gpio_set_level(DIRECTION_GPIO, 0));
}

void app_main(void)
{
    require_ok(gpio_set_level(ENABLE_GPIO, 0));
    require_ok(gpio_set_level(DIRECTION_GPIO, 0));
    const gpio_config_t outputs = {
        .pin_bit_mask = (UINT64_C(1) << ENABLE_GPIO) | (UINT64_C(1) << DIRECTION_GPIO),
        .mode = GPIO_MODE_OUTPUT, .pull_down_en = GPIO_PULLDOWN_ENABLE,
    };
    require_ok(gpio_config(&outputs));
    const gpio_config_t stop = {
        .pin_bit_mask = UINT64_C(1) << STOP_GPIO,
        .mode = GPIO_MODE_INPUT, .pull_up_en = GPIO_PULLUP_ENABLE,
    };
    require_ok(gpio_config(&stop));
    const ledc_timer_config_t timer = {
        .speed_mode = LEDC_LOW_SPEED_MODE, .duty_resolution = LEDC_TIMER_8_BIT,
        .timer_num = LEDC_TIMER_0, .freq_hz = PWM_HZ, .clk_cfg = LEDC_AUTO_CLK,
    };
    require_ok(ledc_timer_config(&timer));
    const ledc_channel_config_t channel = {
        .gpio_num = ENABLE_GPIO, .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_0, .timer_sel = LEDC_TIMER_0, .duty = 0,
    };
    require_ok(ledc_channel_config(&channel));
    pwm_ready = true;
    pwm_off();
    const uart_config_t serial = {
        .baud_rate = 115200, .data_bits = UART_DATA_8_BITS, .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1, .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    require_ok(uart_param_config(UART_NUM_0, &serial));
    QueueHandle_t events;
    require_ok(uart_driver_install(UART_NUM_0, 512, 0, 16, &events, 0));
    require_ok(uart_flush_input(UART_NUM_0));
    require_ok(esp_task_wdt_add(NULL));
    bench_policy state = {0};
    uint64_t stop_release_after = now_ms() + RELEASE_MS;
    printf("BENCH READY 0.1.2 GPIO4=E1 GPIO5=M1 PWM=1000Hz/40%% pulse=%ums\n"
           "Driver power LAST ON / FIRST OFF. Keys: a=arm(3s), f/r=one pulse, s=stop.\n"
           "BOOT stops; no auto-repeat. Wait >=1s AND shaft stopped between pulses.\n",
           (unsigned)BENCH_PULSE_MS);
    for (;;) {
        uint64_t now = now_ms();
        if (gpio_get_level(STOP_GPIO) == 0) stop_release_after = now + RELEASE_MS;
        bool held = now < stop_release_after;
        bool was_active = state.active;
        bool was_armed = state.armed;
        bench_tick(&state, now, held);
        /* Apply deadline / BOOT stop before inspecting UART or printing. */
        if (was_active && !state.active) pwm_off();

        bool serial_fault = false;
        uart_event_t event;
        for (unsigned i = 0; i < 16 && xQueueReceive(events, &event, 0) == pdTRUE; ++i) {
            if (event.type != UART_DATA) serial_fault = true;
        }
        size_t buffered = 0;
        require_ok(uart_get_buffered_data_len(UART_NUM_0, &buffered));
        unsigned char bytes[64];
        int count = 0;
        bool boundary = held || (was_active && !state.active) ||
                        (was_armed && !state.armed) || serial_fault || buffered > sizeof(bytes);
        if (boundary) {
            bench_stop(&state, now);
            pwm_off();
            require_ok(uart_flush_input(UART_NUM_0));
        } else if (buffered != 0) {
            count = uart_read_bytes(UART_NUM_0, bytes, sizeof(bytes), 0);
            if (count < 0) {
                bench_stop(&state, now);
            } else {
                bench_receive(&state, now, held, bytes, (size_t)count);
            }
        }
        if (was_active && !state.active) pwm_off();
        if (!was_active && state.active) {
            /* Direction changes only with PWM stopped; no logging while energized. */
            require_ok(gpio_set_level(DIRECTION_GPIO, state.reverse));
            require_ok(ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, PWM_DUTY));
            require_ok(ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0));
        }
        if (!state.active && (count > 0 || was_active || was_armed != state.armed || serial_fault)) {
            printf("BENCH %s outputs=OFF%s\n", state.armed ? "ARMED (send f/r within 3s)" : "DISARMED",
                   held ? " BOOT held" : "");
        }
        require_ok(esp_task_wdt_reset());
        vTaskDelay(pdMS_TO_TICKS(POLL_MS));
    }
}
