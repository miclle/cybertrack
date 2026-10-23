#include <inttypes.h>
#include <stdint.h>

#include "cybertrack/control.h"
#include "cybertrack/inputs.h"
#include "driver/gpio.h"
#include "esp_app_desc.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_memory_utils.h"
#include "esp_psram.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "board_check";
enum { TEST_BYTES = 6 * 1024 * 1024, EXPECTED_PSRAM_BYTES = 8 * 1024 * 1024 };
enum { STOP_GPIO = GPIO_NUM_0, POLL_MS = 10, RELEASE_MS = 30 };

static uint64_t now_ms(void)
{
    return (uint64_t)esp_timer_get_time() / 1000;
}

static bool outputs_off(const ct_controller *controller)
{
    return controller->output.left_level == 0 && controller->output.right_level == 0 &&
           !controller->output.water && !controller->output.bubbles;
}

static uint32_t pattern(size_t index, unsigned pass)
{
    const uint32_t fixed[] = {0, UINT32_MAX, UINT32_C(0xaaaaaaaa), UINT32_C(0x55555555)};
    if (pass < 4) {
        return fixed[pass];
    }
    /* Odd multiplier gives distinct values across word addresses; pass 5 inverts. */
    uint32_t value = (uint32_t)index * UINT32_C(2654435761) ^ UINT32_C(0x6d2b79f5);
    return pass == 4 ? value : ~value;
}

static bool check_psram(void)
{
    size_t size = esp_psram_get_size();
    ESP_LOGI(TAG, "PSRAM initialized=%d detected_bytes=%u", esp_psram_is_initialized(), (unsigned)size);
    if (!esp_psram_is_initialized() || size != EXPECTED_PSRAM_BYTES) {
        return false;
    }
    volatile uint32_t *memory = heap_caps_malloc(TEST_BYTES, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (memory == NULL || !esp_ptr_external_ram((const void *)memory)) {
        heap_caps_free((void *)memory);
        ESP_LOGE(TAG, "PSRAM allocation failed or not external");
        return false;
    }
    ESP_LOGI(TAG, "PSRAM test_bytes=%u patterns=6", TEST_BYTES);
    const size_t words = TEST_BYTES / sizeof(*memory);
    for (unsigned pass = 0; pass < 6; ++pass) {
        /* Full region writes precede reads; 6 MiB exceeds the data cache. */
        for (size_t i = 0; i < words; ++i) {
            memory[i] = pattern(i, pass);
            if ((i & 0x3fff) == 0) {
                vTaskDelay(1);
            }
        }
        for (size_t i = 0; i < words; ++i) {
            uint32_t actual = memory[i];
            uint32_t expected = pattern(i, pass);
            if (actual != expected) {
                ESP_LOGE(TAG, "PSRAM FAIL pass=%u word=%u expected=%08" PRIx32 " actual=%08" PRIx32,
                         pass, (unsigned)i, expected, actual);
                heap_caps_free((void *)memory);
                return false;
            }
            if ((i & 0x3fff) == 0) {
                vTaskDelay(1);
            }
        }
        ESP_LOGI(TAG, "PSRAM pattern=%u PASS", pass);
    }
    heap_caps_free((void *)memory);
    bool intact = heap_caps_check_integrity_all(true);
    ESP_LOGI(TAG, "PSRAM heap_integrity=%s", intact ? "PASS" : "FAIL");
    return intact;
}

void app_main(void)
{
    const esp_app_desc_t *app = esp_app_get_description();
    ESP_LOGI(TAG, "CyberTrack no-load boot version=%s idf=%s reset_reason=%d",
             app->version, app->idf_ver, esp_reset_reason());
    /* This image has no actuator GPIO/PWM, network, or enable path. */
    ct_controller controller;
    ct_init(&controller, (ct_limits){0}, now_ms());
    ESP_LOGI(TAG, "CONTROL state=BOOT capabilities=0 logical_outputs_off=%d", outputs_off(&controller));
    if (!check_psram()) {
        ct_set_fault(&controller, true);
        ESP_LOGE(TAG, "VALIDATION FAIL; capabilities remain zero");
        return;
    }
    const gpio_config_t stop_gpio = {
        .pin_bit_mask = UINT64_C(1) << STOP_GPIO,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ct_input_filter filter;
    if (gpio_config(&stop_gpio) != ESP_OK ||
        !ct_inputs_init(&filter, RELEASE_MS, RELEASE_MS,
                        (ct_local_inputs){.stop = gpio_get_level(STOP_GPIO) == 0}, now_ms())) {
        ct_set_fault(&controller, true);
        ESP_LOGE(TAG, "INPUT FAIL; capabilities remain zero");
        return;
    }
    ct_local_inputs inputs;
    if (!ct_inputs_read(&filter, &inputs)) {
        ct_set_fault(&controller, true);
        ESP_LOGE(TAG, "INPUT FAIL; capabilities remain zero");
        return;
    }
    ct_set_stop(&controller, inputs.stop);
    if (ct_boot_complete(&controller) != CT_OK || !outputs_off(&controller)) {
        ct_set_fault(&controller, true);
        ESP_LOGE(TAG, "VALIDATION FAIL; capabilities remain zero");
        return;
    }
    ESP_LOGI(TAG, "VALIDATION PASS state=%s capabilities=0 logical_outputs_off=1",
             controller.state == CT_DISARMED ? "DISARMED" : "FAULT");
    ESP_LOGI(TAG, "BOOT_STOP READY gpio=0 active_low=1 poll_ms=%u release_debounce_ms=%u held=%d",
             POLL_MS, RELEASE_MS, inputs.stop);
    bool previous_stop = inputs.stop;
    unsigned presses = 0;
    unsigned ticks = 0;
    int64_t previous_poll_us = esp_timer_get_time();
    int64_t max_poll_gap_us = 0;
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(POLL_MS));
        int64_t observed_us = esp_timer_get_time();
        int64_t gap_us = observed_us - previous_poll_us;
        previous_poll_us = observed_us;
        if (gap_us > max_poll_gap_us) max_poll_gap_us = gap_us;
        bool raw_stop = gpio_get_level(STOP_GPIO) == 0;
        if (!ct_inputs_observe(&filter, (ct_local_inputs){.stop = raw_stop}, now_ms()) ||
            !ct_inputs_read(&filter, &inputs)) {
            ct_set_fault(&controller, true);
            ESP_LOGE(TAG, "INPUT FAIL; capabilities remain zero");
            return;
        }
        /* Stop assertion precedes the normal control tick; release never enables. */
        ct_set_stop(&controller, inputs.stop);
        int64_t applied_us = esp_timer_get_time();
        if (ct_tick(&controller, now_ms()) != CT_OK ||
            (controller.state != CT_DISARMED &&
             !(controller.state == CT_FAULT && controller.fault == CT_STOPPED)) ||
            !outputs_off(&controller)) {
            ct_set_fault(&controller, true);
            ESP_LOGE(TAG, "CONTROL FAIL; capabilities remain zero");
            return;
        }
        if (inputs.stop != previous_stop) {
            if (inputs.stop) ++presses;
            ESP_LOGI(TAG, "BOOT_STOP %s presses=%u raw_low=%d held=%d state=FAULT fault=STOPPED logical_outputs_off=1 observed_to_apply_us=%" PRId64,
                     inputs.stop ? "PRESSED" : "RELEASED", presses, raw_stop, inputs.stop,
                     applied_us - observed_us);
            previous_stop = inputs.stop;
        }
        if (++ticks % 100 == 0) {
            ESP_LOGI(TAG, "HEARTBEAT ticks=%u state=%s held=%d presses=%u logical_outputs_off=1 max_poll_gap_us=%" PRId64,
                     ticks, controller.state == CT_DISARMED ? "DISARMED" : "FAULT",
                     inputs.stop, presses, max_poll_gap_us);
        }
    }
}
