#include <stdio.h>
#include "bench_policy.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

enum { ENABLE_GPIO = GPIO_NUM_4, STOP_GPIO = GPIO_NUM_0,
       POLL_MS = 5, RELEASE_MS = 30 };

static uint64_t now_ms(void)
{
    return (uint64_t)esp_timer_get_time() / 1000;
}

static void all_off(void)
{
    (void)gpio_set_level(ENABLE_GPIO, 0);
    (void)gpio_set_direction(ENABLE_GPIO, GPIO_MODE_OUTPUT);
}

static void require_ok(esp_err_t result)
{
    if (result == ESP_OK) return;
    all_off();
    printf("MOS ERROR %s; outputs disabled; disconnect load power before reset.\n",
           esp_err_to_name(result));
    /* Remain off rather than auto-restarting the bench. */
    for (;;) {
        (void)esp_task_wdt_reset();
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

static void output_off(void)
{
    require_ok(gpio_set_level(ENABLE_GPIO, 0));
}

void app_main(void)
{
    require_ok(gpio_set_level(ENABLE_GPIO, 0));
    const gpio_config_t outputs = {
        .pin_bit_mask = UINT64_C(1) << ENABLE_GPIO,
        .mode = GPIO_MODE_OUTPUT, .pull_down_en = GPIO_PULLDOWN_ENABLE,
    };
    require_ok(gpio_config(&outputs));
    const gpio_config_t stop = {
        .pin_bit_mask = UINT64_C(1) << STOP_GPIO,
        .mode = GPIO_MODE_INPUT, .pull_up_en = GPIO_PULLUP_ENABLE,
    };
    require_ok(gpio_config(&stop));
    output_off();
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
    printf("MOS READY 0.1.1 GPIO4=TRIGGER active=HIGH pulse=%ums\n"
           "Load power LAST ON / FIRST OFF. Keys: a=arm(3s), g=one pulse, s=stop.\n"
           "BOOT stops; no auto-repeat. Wait >=1s between pulses.\n",
           (unsigned)BENCH_PULSE_MS);
    for (;;) {
        uint64_t now = now_ms();
        if (gpio_get_level(STOP_GPIO) == 0) stop_release_after = now + RELEASE_MS;
        bool held = now < stop_release_after;
        bool was_active = state.active;
        bool was_armed = state.armed;
        bench_tick(&state, now, held);
        /* Apply deadline / BOOT stop before inspecting UART or printing. */
        if (was_active && !state.active) output_off();

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
            output_off();
            require_ok(uart_flush_input(UART_NUM_0));
        } else if (buffered != 0) {
            count = uart_read_bytes(UART_NUM_0, bytes, sizeof(bytes), 0);
            if (count < 0) {
                bench_stop(&state, now);
            } else {
                bench_receive(&state, now, held, bytes, (size_t)count);
            }
        }
        if (was_active && !state.active) output_off();
        if (!was_active && state.active) {
            /* No PWM and no logging while energized. */
            require_ok(gpio_set_level(ENABLE_GPIO, 1));
        }
        if (!state.active && (count > 0 || was_active || was_armed != state.armed || serial_fault)) {
            printf("MOS %s outputs=OFF%s\n", state.armed ? "ARMED (send g within 3s)" : "DISARMED",
                   held ? " BOOT held" : "");
        }
        require_ok(esp_task_wdt_reset());
        vTaskDelay(pdMS_TO_TICKS(POLL_MS));
    }
}
