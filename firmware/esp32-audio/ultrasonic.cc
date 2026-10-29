#include "ultrasonic.h"
#include <driver/gpio.h>
#include <driver/rmt_rx.h>
#include <esp_log.h>
#include <esp_rom_sys.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>

namespace {
constexpr gpio_num_t TrigPin = GPIO_NUM_1;
constexpr gpio_num_t EchoPin = GPIO_NUM_2;
constexpr size_t SymbolCapacity = 48;
portMUX_TYPE reading_lock = portMUX_INITIALIZER_UNLOCKED;
ultrasonic::Reading latest;
StaticQueue_t done_storage;
uint8_t done_bytes[sizeof(size_t)];
QueueHandle_t done_queue;

void Publish(const ultrasonic::Reading& reading) {
    portENTER_CRITICAL(&reading_lock);
    latest = reading;
    portEXIT_CRITICAL(&reading_lock);
}
bool ReceiveDone(rmt_channel_handle_t, const rmt_rx_done_event_data_t* event, void*) {
    BaseType_t wake = pdFALSE;
    // The fixed buffer belongs to the task and is not rearmed until consumed.
    xQueueSendFromISR(done_queue, &event->num_symbols, &wake);
    return wake == pdTRUE;
}

void DistanceTask(void*) {
    rmt_channel_handle_t rx = nullptr;
    bool enabled = false;
    auto check = [](esp_err_t error) {
        if (error == ESP_OK) return true;
        ESP_LOGE("CT_RANGE", "Driver error: %s", esp_err_to_name(error));
        return false;
    };
    // Sensor failures are telemetry failures, never action-driver faults.
    // No action mutex is held while configuring, capturing or waiting.
    const auto run = [&]() {
        if (!check(gpio_set_level(TrigPin, 0))) return;
        gpio_config_t trig{};
        trig.pin_bit_mask = 1ULL << TrigPin;
        trig.mode = GPIO_MODE_OUTPUT;
        trig.pull_down_en = GPIO_PULLDOWN_ENABLE;
        if (!check(gpio_config(&trig))) return;
        rmt_rx_channel_config_t config{};
        config.gpio_num = EchoPin;
        config.clk_src = RMT_CLK_SRC_DEFAULT;
        config.resolution_hz = 1000000;
        config.mem_block_symbols = SymbolCapacity;
        if (!check(rmt_new_rx_channel(&config, &rx)) ||
            !check(gpio_set_pull_mode(EchoPin, GPIO_PULLDOWN_ONLY))) return;
        rmt_rx_event_callbacks_t callbacks{};
        callbacks.on_recv_done = ReceiveDone;
        if (!check(rmt_rx_register_event_callbacks(rx, &callbacks, nullptr)) ||
            !check(rmt_enable(rx))) return;
        enabled = true;
        rmt_receive_config_t capture{};
        capture.signal_range_min_ns = 2000;
        // Terminate on 25 ms of unchanged level, covering the ~23.3 ms
        // return at 4 m. Completion can include both pulse and trailing idle.
        capture.signal_range_max_ns = 25000000;
        rmt_symbol_word_t symbols[SymbolCapacity]{};
        vTaskDelay(pdMS_TO_TICKS(100)); // Sensor startup settling time.
        for (;;) {
            uint64_t trigger_ms = esp_timer_get_time() / 1000;
            if (gpio_get_level(EchoPin)) {
                Publish({ultrasonic::Error::EchoHigh, 0, 0, trigger_ms, true});
            } else {
                if (!check(rmt_receive(rx, symbols, sizeof(symbols), &capture))) return;
                if (!check(gpio_set_level(TrigPin, 1))) return;
                esp_rom_delay_us(12);
                if (!check(gpio_set_level(TrigPin, 0))) return;
                trigger_ms = esp_timer_get_time() / 1000;
                size_t count = 0;
                // Bounded task wait, not a polling/busy loop. A missing driver
                // completion stops this task instead of racing an old callback
                // against a new reception. Ordinary no-echo still completes.
                if (xQueueReceive(done_queue, &count, pdMS_TO_TICKS(80)) != pdTRUE) {
                    ESP_LOGE("CT_RANGE", "Capture completion timed out");
                    return;
                }
                ultrasonic::EchoDecoder decoder;
                bool end = false;
                for (size_t i = 0; i < count && i < SymbolCapacity && !end; ++i) {
                    if (!symbols[i].duration0) break;
                    decoder.Feed(symbols[i].level0, symbols[i].duration0);
                    if (!symbols[i].duration1) end = true;
                    else decoder.Feed(symbols[i].level1, symbols[i].duration1);
                }
                Publish(decoder.Finish(trigger_ms, gpio_get_level(EchoPin), count >= SymbolCapacity));
            }
            // Leave >=100 ms between actual triggers even after scheduler stalls;
            // do not use a periodic catch-up loop that could emit bursts.
            const uint64_t elapsed_ms = esp_timer_get_time() / 1000 - trigger_ms;
            const auto delay_ms = elapsed_ms < ultrasonic::SamplePeriodMs ? ultrasonic::SamplePeriodMs - elapsed_ms + 1 : 1;
            vTaskDelay(pdMS_TO_TICKS(delay_ms));
        }
    };
    run();
    gpio_set_level(TrigPin, 0);
    if (enabled) rmt_disable(rx);
    if (rx) rmt_del_channel(rx);
    Publish({ultrasonic::Error::Driver});
    vTaskDelete(nullptr);
}
} // namespace

ultrasonic::Reading CyberTrackDistanceSnapshot() {
    portENTER_CRITICAL(&reading_lock);
    const auto copy = latest;
    portEXIT_CRITICAL(&reading_lock);
    return copy;
}
void InitializeCyberTrackUltrasonic() {
    done_queue = xQueueCreateStatic(1, sizeof(size_t), done_bytes, &done_storage);
    if (xTaskCreate(DistanceTask, "ultrasonic", 4096, nullptr, 2, nullptr) != pdPASS) {
        Publish({ultrasonic::Error::Driver});
        ESP_LOGE("CT_RANGE", "Cannot create distance task");
    }
}
