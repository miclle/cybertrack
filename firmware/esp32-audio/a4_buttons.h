#pragma once
#include "a4_io.h"
#include "button_types.h"

// The upstream button library handles debounce, click, hold and release.
template<unsigned Bit> button_handle_t A4Button() {
    static button_driver_t driver{};
    driver.get_key_level = [](button_driver_t*) -> uint8_t {
        return a4_io::Healthy() && !(a4_io::inputs.load() & (1U << Bit));
    };
    driver.del = [](button_driver_t*) { return ESP_OK; };
    button_config_t config{};
    button_handle_t handle = nullptr;
    ESP_ERROR_CHECK(iot_button_create(&config, &driver, &handle));
    return handle;
}
