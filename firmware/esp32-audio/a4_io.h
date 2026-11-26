#pragma once

#include <atomic>
#include <driver/i2c_master.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

// U12 shares the display bus. Only the serialized action adapter writes port 0.
// The button timer reads a snapshot and never performs a bus transaction.
namespace a4_io {
inline i2c_master_dev_handle_t device = nullptr;
inline std::atomic<uint8_t> inputs{0xff};
inline StaticSemaphore_t mutex_storage;
inline SemaphoreHandle_t mutex = nullptr;
inline uint8_t direction = 0; // protected by mutex after Init()
inline std::atomic<uint32_t> last_good_ms{0};
inline std::atomic<bool> failed{false};
// An OLED frame takes about 12 ms at 400 kHz. Use finite bus and lock waits.
constexpr int TimeoutMs = 20;
inline uint32_t Millis() { return static_cast<uint32_t>(esp_timer_get_time() / 1000); }
inline bool Healthy() {
    const uint32_t sample = last_good_ms.load();
    return !failed.load() && Millis() - sample < 100;
}
constexpr uint8_t Input0 = 0, Output0 = 2, Polarity0 = 4, Config0 = 6;

inline esp_err_t Write(uint8_t reg, uint8_t value) {
    uint8_t data[]{reg, value};
    return i2c_master_transmit(device, data, sizeof(data), TimeoutMs);
}
inline esp_err_t Read(uint8_t reg, uint8_t& value) {
    return i2c_master_transmit_receive(device, &reg, 1, &value, 1, TimeoutMs);
}
inline esp_err_t Verify() {
    uint8_t config, latch, pins;
    if (!device || Read(Config0, config) != ESP_OK || config != 0xf0 ||
        Read(Output0, latch) != ESP_OK || (latch & 15) != direction ||
        Read(Input0, pins) != ESP_OK || (pins & 15) != direction) {
        failed.store(true);
        inputs.store(0xff);
        return ESP_FAIL;
    }
    inputs.store(pins);
    last_good_ms.store(Millis());
    return ESP_OK;
}
inline esp_err_t Init() {
    mutex = xSemaphoreCreateMutexStatic(&mutex_storage);
    i2c_master_bus_handle_t bus;
    i2c_device_config_t dev{};
    dev.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    dev.device_address = 0x74;
    dev.scl_speed_hz = 400000;
    if (!mutex || i2c_master_get_bus_handle(0, &bus) != ESP_OK ||
        i2c_master_bus_add_device(bus, &dev, &device) != ESP_OK) return ESP_FAIL;
    // Port 1 inputs leave the camera on its external safe-state resistors.
    // Preload the direction latch before enabling its four outputs.
    if (Write(Config0 + 1, 0xff) != ESP_OK || Write(Output0, 0) != ESP_OK ||
        Write(Polarity0, 0) != ESP_OK || Write(Config0, 0xf0) != ESP_OK) return ESP_FAIL;
    return Verify();
}
// Polling never holds the action mutex. If it stalls, the safety task can
// still stop direct PWM and effects once the last verified sample expires.
inline void Poll() {
    if (xSemaphoreTake(mutex, pdMS_TO_TICKS(TimeoutMs)) == pdTRUE) {
        Verify();
        xSemaphoreGive(mutex);
    }
}
inline esp_err_t Set(int left, int right) {
    if (xSemaphoreTake(mutex, pdMS_TO_TICKS(TimeoutMs)) != pdTRUE) return ESP_FAIL;
    if (failed.load()) {
        xSemaphoreGive(mutex);
        return ESP_FAIL;
    }
    // P00/P01 select A forward/reverse; P02/P03 select B forward/reverse.
    const uint8_t a = (right > 0) | ((right < 0) << 1);
    const uint8_t b = (left > 0) | ((left < 0) << 1);
    direction = a | (b << 2);
    esp_err_t result = Write(Output0, direction);
    if (result == ESP_OK) result = Verify();
    if (result != ESP_OK) failed.store(true);
    xSemaphoreGive(mutex);
    return result;
}
} // namespace a4_io
