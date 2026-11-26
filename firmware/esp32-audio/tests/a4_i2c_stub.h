#pragma once
#include "output_stub.h"
#include <cstddef>
constexpr int ESP_FAIL = -1, I2C_ADDR_BIT_LEN_7 = 7;
using i2c_master_bus_handle_t = void*;
using i2c_master_dev_handle_t = void*;
struct i2c_device_config_t { int dev_addr_length, device_address, scl_speed_hz; };
esp_err_t i2c_master_get_bus_handle(int, i2c_master_bus_handle_t*);
esp_err_t i2c_master_bus_add_device(i2c_master_bus_handle_t, const i2c_device_config_t*, i2c_master_dev_handle_t*);
esp_err_t i2c_master_transmit(i2c_master_dev_handle_t, const uint8_t*, size_t, int);
esp_err_t i2c_master_transmit_receive(i2c_master_dev_handle_t, const uint8_t*, size_t, uint8_t*, size_t, int);

int64_t esp_timer_get_time();
using StaticSemaphore_t = bool;
using SemaphoreHandle_t = bool*;
constexpr int pdTRUE = 1;
inline int pdMS_TO_TICKS(int ms) { return ms; }
inline bool* xSemaphoreCreateMutexStatic(bool* taken) { return taken; }
inline int xSemaphoreTake(bool* taken, int) { if (*taken) return 0; *taken = true; return pdTRUE; }
inline void xSemaphoreGive(bool* taken) { *taken = false; }
