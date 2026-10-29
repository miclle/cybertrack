#pragma once
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#include <functional>
using esp_err_t = int;
constexpr int ESP_ERR_TIMEOUT = 0x107, ESP_ERR_NO_MEM = 0x101;
constexpr int ESP_OK = 0, GPIO_NUM_1 = 1, GPIO_NUM_2 = 2, GPIO_MODE_OUTPUT = 1;
constexpr int GPIO_PULLDOWN_ENABLE = 1, GPIO_PULLDOWN_ONLY = 1, RMT_CLK_SRC_DEFAULT = 0;
using gpio_num_t = int;
struct gpio_config_t { uint64_t pin_bit_mask = 0; int mode = 0, pull_down_en = 0; };
struct rmt_symbol_word_t { unsigned duration0, level0, duration1, level1; };
struct rmt_rx_done_event_data_t { size_t num_symbols; };
using rmt_channel_handle_t = void*;
struct rmt_rx_channel_config_t { int gpio_num, clk_src; unsigned resolution_hz; size_t mem_block_symbols; };
struct rmt_receive_config_t { unsigned signal_range_min_ns, signal_range_max_ns; };
struct rmt_rx_event_callbacks_t { bool (*on_recv_done)(rmt_channel_handle_t, const rmt_rx_done_event_data_t*, void*); };
using BaseType_t = int;
constexpr int pdFALSE = 0, pdTRUE = 1, pdPASS = 1;
using portMUX_TYPE = int;
constexpr int portMUX_INITIALIZER_UNLOCKED = 0;
inline void portENTER_CRITICAL(int*) {}
inline void portEXIT_CRITICAL(int*) {}
struct StaticQueue_t {};
using QueueHandle_t = void*;
inline unsigned pdMS_TO_TICKS(unsigned ms) { return ms; }
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGI(...) ((void)0)
inline const char* esp_err_to_name(int) { return "mock_error"; }
namespace mock {
struct Done {};
inline uint64_t us = 0;
inline std::string fail;
inline int fail_remaining = -1, timeout_remaining = 0;
inline unsigned allocations = 0, deletions = 0, live_channels = 0, resets = 0;
inline bool late_completion = false;
inline std::vector<unsigned> delay_values;
inline std::vector<uint64_t> trigger_times;
inline std::function<void(unsigned)> on_delay;
inline bool initially_high = false, final_high = false, captured = false, enabled = false, deleted = false;
inline bool task_ok = true, completion = true;
inline unsigned triggers = 0, pulses = 0, delays = 0, cycles = 1, reads = 0;
inline int trig_level = 0;
inline std::vector<rmt_symbol_word_t> frame;
inline rmt_rx_event_callbacks_t callback;
inline void (*task)(void*) = nullptr;
inline size_t count = 0;
inline bool queued = false;
inline int Error(const char* name) {
    if (fail != name || !fail_remaining) return 0;
    if (fail_remaining > 0) --fail_remaining;
    return -1;
}
}
inline QueueHandle_t xQueueCreateStatic(int n, size_t size, uint8_t*, StaticQueue_t*) {
    assert(n == 1 && size == sizeof(size_t)); mock::queued = false; return &mock::count;
}
inline int xQueueSendFromISR(QueueHandle_t, const size_t* count, int* wake) {
    assert(!mock::queued); mock::count = *count; mock::queued = true; *wake = pdTRUE; return pdTRUE;
}
inline int xQueueReceive(QueueHandle_t, size_t* count, unsigned wait) {
    assert(wait == 80);
    if (!mock::completion || mock::timeout_remaining > 0) {
        if (mock::timeout_remaining > 0) --mock::timeout_remaining;
        mock::us += 80000; return pdFALSE;
    }
    mock::us += 50000;
    rmt_rx_done_event_data_t event{mock::frame.size()};
    mock::callback.on_recv_done(nullptr, &event, nullptr);
    assert(mock::queued); *count = mock::count; mock::queued = false; return pdTRUE;
}
inline int xQueueReset(QueueHandle_t) {
    assert(!mock::enabled && !mock::live_channels); mock::queued = false; ++mock::resets; return pdTRUE;
}
inline int xTaskCreatePinnedToCore(void (*task)(void*), const char*, unsigned stack, void*, int priority, void*, int core) {
    assert(stack >= 4096 && priority == 2 && core == 1); mock::task = task; return mock::task_ok ? pdPASS : 0;
}
inline void vTaskDelay(unsigned ms) {
    assert(ms > 0); mock::delay_values.push_back(ms);
    if (mock::on_delay) mock::on_delay(ms);
    mock::us += ms * 1000;
    if (++mock::delays > mock::cycles) throw mock::Done{};
}
inline void vTaskDelete(void*) { throw mock::Done{}; }
inline int64_t esp_timer_get_time() { return mock::us; }
inline void esp_rom_delay_us(unsigned us) { assert(us == 12); mock::us += us; ++mock::pulses; }
inline int gpio_set_level(int pin, int value) {
    assert(pin == GPIO_NUM_1); mock::trig_level = value;
    if (value) { ++mock::triggers; mock::trigger_times.push_back(mock::us); }
    return mock::Error(value ? "trig_high" : "trig_low");
}
inline int gpio_config(const gpio_config_t* config) {
    assert(config->pin_bit_mask == (1ULL << GPIO_NUM_1)); return mock::Error("gpio_config");
}
inline int gpio_get_level(int pin) {
    assert(pin == GPIO_NUM_2); ++mock::reads;
    return mock::captured ? mock::final_high : mock::initially_high;
}
inline int gpio_set_pull_mode(int pin, int mode) {
    assert(pin == GPIO_NUM_2 && mode == GPIO_PULLDOWN_ONLY); return mock::Error("pull");
}
inline int rmt_new_rx_channel(const rmt_rx_channel_config_t* config, rmt_channel_handle_t* rx) {
    assert(config->gpio_num == GPIO_NUM_2 && config->resolution_hz == 1000000 && config->mem_block_symbols == 48);
    if (mock::Error("new_rx")) return -1;
    assert(!mock::live_channels); ++mock::allocations; ++mock::live_channels;
    mock::deleted = false; *rx = &mock::callback; return 0;
}
inline int rmt_rx_register_event_callbacks(rmt_channel_handle_t, const rmt_rx_event_callbacks_t* callback, void*) {
    mock::callback = *callback; return mock::Error("callback");
}
inline int rmt_enable(rmt_channel_handle_t) {
    if (mock::Error("enable")) return -1;
    mock::enabled = true; return 0;
}
inline int rmt_receive(rmt_channel_handle_t, void* buffer, size_t size, const rmt_receive_config_t* config) {
    assert(mock::enabled && !mock::queued);
    assert(config->signal_range_min_ns == 2000 && config->signal_range_max_ns == 25000000);
    assert(size == 48 * sizeof(rmt_symbol_word_t));
    if (mock::Error("receive")) return -1;
    std::memcpy(buffer, mock::frame.data(), mock::frame.size() * sizeof(rmt_symbol_word_t));
    mock::captured = true; return 0;
}
inline int rmt_disable(rmt_channel_handle_t) {
    if (mock::Error("disable")) return -1;
    if (mock::late_completion) {
        rmt_rx_done_event_data_t event{47};
        mock::callback.on_recv_done(nullptr, &event, nullptr); // Old capture completes just before shutdown.
    }
    mock::enabled = false; mock::captured = false; return 0;
}
inline int rmt_del_channel(rmt_channel_handle_t) {
    assert(!mock::enabled);
    if (mock::Error("delete")) return -1;
    assert(mock::live_channels == 1); --mock::live_channels; ++mock::deletions;
    mock::deleted = true; return 0;
}
