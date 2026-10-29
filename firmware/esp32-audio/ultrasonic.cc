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
    // Kept alive even if cleanup fails: an old receiver must never write into
    // a dead stack or a new attempt's buffer. This task and its ISR share a core.
    rmt_symbol_word_t symbols[SymbolCapacity]{};
    ultrasonic::DriverStatus status;
    unsigned backoff_ms = 1000;
    const auto publish = [&](ultrasonic::Reading reading) {
        reading.driver = status;
        Publish(reading);
    };
    const auto check = [&](const char* stage, esp_err_t error) {
        if (error == ESP_OK) return true;
        status.last_failure = stage;
        status.error_code = error;
        status.failed_at_ms = esp_timer_get_time() / 1000;
        if (status.failures != UINT32_MAX) ++status.failures;
        status.recovering = true;
        status.retry_delay_ms = backoff_ms;
        publish({ultrasonic::Error::Driver});
        ESP_LOGE("CT_RANGE", "Driver failure stage=%s code=%d restart=%u retry_ms=%u",
                 stage, error, status.restarts, backoff_ms);
        return false;
    };
    const auto latch_cleanup_failure = [&]() {
        // Do not allocate another channel or recycle the queue/buffer after an
        // unsuccessful shutdown. Other device functions continue independently.
        status.recovering = false;
        status.retry_delay_ms = 0;
        publish({ultrasonic::Error::Driver});
        for (;;) vTaskDelay(pdMS_TO_TICKS(1000));
    };
    for (;;) {
        rmt_channel_handle_t rx = nullptr;
        bool enabled = false;
        const auto run = [&]() {
            if (!check("trig_low", gpio_set_level(TrigPin, 0))) return;
            gpio_config_t trig{};
            trig.pin_bit_mask = 1ULL << TrigPin;
            trig.mode = GPIO_MODE_OUTPUT;
            trig.pull_down_en = GPIO_PULLDOWN_ENABLE;
            if (!check("trig_config", gpio_config(&trig))) return;
            // Cold-start allowance, not a measured module readiness guarantee.
            if (!status.restarts) vTaskDelay(pdMS_TO_TICKS(1000));
            rmt_rx_channel_config_t config{};
            config.gpio_num = EchoPin;
            config.clk_src = RMT_CLK_SRC_DEFAULT;
            config.resolution_hz = 1000000;
            config.mem_block_symbols = SymbolCapacity;
            if (!check("rx_create", rmt_new_rx_channel(&config, &rx)) ||
                !check("echo_pull", gpio_set_pull_mode(EchoPin, GPIO_PULLDOWN_ONLY))) return;
            rmt_rx_event_callbacks_t callbacks{};
            callbacks.on_recv_done = ReceiveDone;
            if (!check("rx_callback", rmt_rx_register_event_callbacks(rx, &callbacks, nullptr)) ||
                !check("rx_enable", rmt_enable(rx))) return;
            enabled = true;
            rmt_receive_config_t capture{};
            capture.signal_range_min_ns = 2000;
            capture.signal_range_max_ns = 25000000;
            for (;;) {
                uint64_t trigger_ms = esp_timer_get_time() / 1000;
                if (gpio_get_level(EchoPin)) {
                    publish({ultrasonic::Error::EchoHigh, 0, 0, trigger_ms, true});
                } else {
                    if (!check("rx_receive", rmt_receive(rx, symbols, sizeof(symbols), &capture))) return;
                    if (!check("trig_high", gpio_set_level(TrigPin, 1))) return;
                    esp_rom_delay_us(12);
                    if (!check("trig_end", gpio_set_level(TrigPin, 0))) return;
                    trigger_ms = esp_timer_get_time() / 1000;
                    size_t count = 0;
                    if (xQueueReceive(done_queue, &count, pdMS_TO_TICKS(80)) != pdTRUE) {
                        check("rx_timeout", ESP_ERR_TIMEOUT);
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
                    auto reading = decoder.Finish(trigger_ms, gpio_get_level(EchoPin), count >= SymbolCapacity);
                    if (status.recovering) ESP_LOGI("CT_RANGE", "Receiver recovered restart=%u sample=%s",
                                                  status.restarts, ultrasonic::ErrorName(reading.error));
                    status.recovering = false;
                    status.retry_delay_ms = 0;
                    if (reading.error == ultrasonic::Error::None) backoff_ms = 1000;
                    publish(reading);
                }
                const uint64_t elapsed_ms = esp_timer_get_time() / 1000 - trigger_ms;
                const auto delay_ms = elapsed_ms < ultrasonic::SamplePeriodMs ? ultrasonic::SamplePeriodMs - elapsed_ms + 1 : 1;
                vTaskDelay(pdMS_TO_TICKS(delay_ms));
            }
        };
        run();
        const bool trig_off = check("trig_cleanup", gpio_set_level(TrigPin, 0));
        if (enabled && !check("rx_disable", rmt_disable(rx))) latch_cleanup_failure();
        if (rx && !check("rx_delete", rmt_del_channel(rx))) latch_cleanup_failure();
        // The pinned task resumes only after its ISR returns; disable/delete
        // remove the old interrupt source before clearing a late completion.
        xQueueReset(done_queue);
        if (!trig_off) latch_cleanup_failure();
        vTaskDelay(pdMS_TO_TICKS(backoff_ms));
        status.retry_delay_ms = 0;
        if (status.restarts != UINT32_MAX) ++status.restarts;
        backoff_ms = backoff_ms < 8000 ? backoff_ms * 2 : 8000;
        publish({ultrasonic::Error::Driver});
    }
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
    if (xTaskCreatePinnedToCore(DistanceTask, "ultrasonic", 4096, nullptr, 2, nullptr, 1) != pdPASS) {
        ultrasonic::Reading reading{ultrasonic::Error::Driver};
        reading.driver.last_failure = "task_create";
        reading.driver.error_code = ESP_ERR_NO_MEM;
        reading.driver.failed_at_ms = esp_timer_get_time() / 1000;
        reading.driver.failures = 1;
        Publish(reading);
        ESP_LOGE("CT_RANGE", "Cannot create distance task");
    }
}
