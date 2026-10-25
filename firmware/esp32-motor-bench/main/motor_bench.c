#include <stdio.h>
#include "bench_policy.h"
#include "driver/gpio.h"
#include "driver/ledc.h"
#include "driver/uart.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

enum { STOP_GPIO = GPIO_NUM_0, POLL_MS = 5, RELEASE_MS = 30,
       PWM_HZ = 1000, PWM_DUTY = 154, BRIDGE_COUNT = 2 }; /* ~60%, 8 bits */
static const struct {
    int enable, input1, input2;
    ledc_channel_t channel;
} bridges[BRIDGE_COUNT] = {
    {GPIO_NUM_4, GPIO_NUM_5, GPIO_NUM_6, LEDC_CHANNEL_0},
    {GPIO_NUM_7, GPIO_NUM_8, GPIO_NUM_9, LEDC_CHANNEL_1},
};
static unsigned pwm_ready_mask;

static const char *target_name(unsigned channels)
{
    switch (channels) {
    case BENCH_CHANNEL_A: return "A";
    case BENCH_CHANNEL_B: return "B";
    case BENCH_CHANNEL_BOTH: return "AB";
    default: return "NONE";
    }
}

static uint64_t now_ms(void)
{
    return (uint64_t)esp_timer_get_time() / 1000;
}

static void all_off(void)
{
    /* Try both PWM stops, then reclaim both enables even if an API fails. */
    for (unsigned i = 0; i < BRIDGE_COUNT; ++i) {
        if (pwm_ready_mask & (1u << i))
            (void)ledc_stop(LEDC_LOW_SPEED_MODE, bridges[i].channel, 0);
    }
    for (unsigned i = 0; i < BRIDGE_COUNT; ++i) {
        (void)gpio_set_level(bridges[i].enable, 0);
        (void)gpio_set_direction(bridges[i].enable, GPIO_MODE_OUTPUT);
    }
    for (unsigned i = 0; i < BRIDGE_COUNT; ++i) {
        (void)gpio_set_level(bridges[i].input1, 0);
        (void)gpio_set_level(bridges[i].input2, 0);
    }
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
    esp_err_t first_error = ESP_OK;
    for (unsigned i = 0; i < BRIDGE_COUNT; ++i) {
        esp_err_t result = ledc_stop(LEDC_LOW_SPEED_MODE, bridges[i].channel, 0);
        if (first_error == ESP_OK) first_error = result;
    }
    require_ok(first_error);
    for (unsigned i = 0; i < BRIDGE_COUNT; ++i) {
        require_ok(gpio_set_level(bridges[i].input1, 0));
        require_ok(gpio_set_level(bridges[i].input2, 0));
    }
}

static void pwm_start(unsigned channels, bool reverse_a, bool reverse_b)
{
    /* Both bridges stay disabled until every selected direction has settled. */
    pwm_off();
    for (unsigned i = 0; i < BRIDGE_COUNT; ++i) {
        if (!(channels & (1u << i))) continue;
        bool reverse = i == 0 ? reverse_a : reverse_b;
        require_ok(gpio_set_level(bridges[i].input1, !reverse));
        require_ok(gpio_set_level(bridges[i].input2, reverse));
        require_ok(ledc_set_duty(LEDC_LOW_SPEED_MODE, bridges[i].channel, PWM_DUTY));
    }
    for (unsigned i = 0; i < BRIDGE_COUNT; ++i) {
        if (channels & (1u << i))
            require_ok(ledc_update_duty(LEDC_LOW_SPEED_MODE, bridges[i].channel));
    }
}

void app_main(void)
{
    uint64_t output_mask = 0;
    for (unsigned i = 0; i < BRIDGE_COUNT; ++i) {
        require_ok(gpio_set_level(bridges[i].enable, 0));
        require_ok(gpio_set_level(bridges[i].input1, 0));
        require_ok(gpio_set_level(bridges[i].input2, 0));
        output_mask |= (UINT64_C(1) << bridges[i].enable) |
                       (UINT64_C(1) << bridges[i].input1) |
                       (UINT64_C(1) << bridges[i].input2);
    }
    const gpio_config_t outputs = {
        .pin_bit_mask = output_mask,
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
    for (unsigned i = 0; i < BRIDGE_COUNT; ++i) {
        const ledc_channel_config_t channel = {
            .gpio_num = bridges[i].enable, .speed_mode = LEDC_LOW_SPEED_MODE,
            .channel = bridges[i].channel, .timer_sel = LEDC_TIMER_0, .duty = 0,
        };
        require_ok(ledc_channel_config(&channel));
        pwm_ready_mask |= 1u << i;
    }
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
    bool previous_held = true;
    printf("BENCH READY 0.3.2-l298n-dual-10s A=4/5/6 B=7/8/9 PWM=1000Hz/60%% pulse=%ums\n"
           "Driver power LAST ON / FIRST OFF. Keys: 1=A, 2=B, 3=AB; a=arm(3s), f/r=same direction, x=A+/B-, y=A-/B+, s=stop both.\n"
           "BOOT stops both; target=NONE at boot; no auto-repeat. Wait >=3s AND shafts stopped between pulses.\n",
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
            /* Recheck stop/deadline after UART work, before energizing the bridge. */
            now = now_ms();
            if (gpio_get_level(STOP_GPIO) == 0) stop_release_after = now + RELEASE_MS;
            held = now < stop_release_after;
            bench_tick(&state, now, held);
            if (state.active) pwm_start(state.channels, state.reverse, state.reverse_b);
            else pwm_off();
        }
        if (!state.active && (count > 0 || was_active || was_armed != state.armed ||
                              serial_fault || held != previous_held)) {
            printf("BENCH %s outputs=OFF target=%s%s\n", state.armed ? "ARMED (send f/r within 3s)" : "DISARMED",
                   target_name(state.channels), held ? " BOOT held" : "");
        }
        previous_held = held;
        require_ok(esp_task_wdt_reset());
        vTaskDelay(pdMS_TO_TICKS(POLL_MS));
    }
}
