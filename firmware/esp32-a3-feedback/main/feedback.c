#include <inttypes.h>
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "a3-feedback";
static i2c_master_dev_handle_t encoder, imu;

static i2c_master_dev_handle_t device(i2c_master_bus_handle_t bus, uint16_t address) {
    i2c_master_dev_handle_t handle;
    i2c_device_config_t config = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7, .device_address = address, .scl_speed_hz = 100000
    };
    ESP_ERROR_CHECK(i2c_master_bus_add_device(bus, &config, &handle));
    return handle;
}

static uint32_t unpack32(const uint8_t *p) {
    return p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static int16_t unpack16(const uint8_t *p) {
    return (int16_t)((uint16_t)p[0] | (uint16_t)p[1] << 8);
}

static uint8_t crc8(const uint8_t *p, size_t length) {
    uint8_t value = 0;
    for (size_t i = 0; i < length; ++i) {
        value ^= p[i];
        for (unsigned bit = 0; bit < 8; ++bit)
            value = (uint8_t)((value << 1) ^ ((value & 0x80u) ? 0x07 : 0));
    }
    return value;
}

static void read_encoder(void) {
    uint8_t frame[17];
    esp_err_t rc = i2c_master_receive(encoder, frame, sizeof(frame), 30);
    if (rc != ESP_OK) {
        ESP_LOGW(TAG, "counter read: %s", esp_err_to_name(rc));
        return;
    }
    if (frame[0] != 'C' || frame[1] != 'T' || frame[2] != 1 || crc8(frame, 16) != frame[16]) {
        ESP_LOGW(TAG, "invalid counter frame");
        return;
    }
    ESP_LOGI(TAG, "counter uptime=%" PRIu32 " ms A=%" PRId32 " B=%" PRId32 " reset=%u",
             unpack32(frame + 4), (int32_t)unpack32(frame + 8),
             (int32_t)unpack32(frame + 12), frame[3]);
}

static esp_err_t reg_read(uint8_t reg, uint8_t *bytes, size_t len) {
    return i2c_master_transmit_receive(imu, &reg, 1, bytes, len, 30);
}

static esp_err_t start_imu(void) {
    uint8_t id;
    esp_err_t rc = reg_read(0x0f, &id, 1);
    if (rc != ESP_OK) return rc;
    if (id != 0x6c) return ESP_ERR_INVALID_RESPONSE;
    // CTRL3_C: block updates during bursts and increment addresses.
    // CTRL1_XL and CTRL2_G: 104 Hz, +/-2 g and +/-250 degrees/s.
    const uint8_t writes[][2] = {{0x12, 0x44}, {0x10, 0x40}, {0x11, 0x40}};
    for (unsigned i = 0; i < sizeof(writes) / sizeof(writes[0]); ++i) {
        rc = i2c_master_transmit(imu, writes[i], sizeof(writes[i]), 30);
        if (rc != ESP_OK) return rc;
    }
    return ESP_OK;
}

static esp_err_t read_imu(void) {
    uint8_t status, axes[12];
    esp_err_t rc = reg_read(0x1e, &status, 1);
    if (rc != ESP_OK || (status & 3) != 3) return rc;
    rc = reg_read(0x22, axes, sizeof(axes));
    if (rc == ESP_OK) {
        ESP_LOGI(TAG, "gyro xyz=%d,%d,%d accel xyz=%d,%d,%d (raw)",
                 unpack16(axes), unpack16(axes + 2), unpack16(axes + 4),
                 unpack16(axes + 6), unpack16(axes + 8), unpack16(axes + 10));
    }
    return rc;
}

void app_main(void) {
    const gpio_num_t enables[] = {8, 11, 14, 17, 18, 45};
    for (unsigned i = 0; i < sizeof(enables) / sizeof(enables[0]); ++i) {
        ESP_ERROR_CHECK(gpio_set_level(enables[i], 0));
        ESP_ERROR_CHECK(gpio_set_direction(enables[i], GPIO_MODE_OUTPUT));
    }
    i2c_master_bus_handle_t bus;
    i2c_master_bus_config_t config = {
        .i2c_port = I2C_NUM_0, .sda_io_num = 41, .scl_io_num = 42,
        .clk_source = I2C_CLK_SRC_DEFAULT, .glitch_ignore_cnt = 7
    };
    ESP_ERROR_CHECK(i2c_new_master_bus(&config, &bus));
    encoder = device(bus, 0x32);
    imu = device(bus, 0x6a);
    bool initialized = false;
    for (;;) {
        read_encoder();
        esp_err_t rc = initialized ? read_imu() : start_imu();
        initialized = rc == ESP_OK;
        if (!initialized) ESP_LOGW(TAG, "IMU: %s", esp_err_to_name(rc));
        vTaskDelay(pdMS_TO_TICKS(200));
    }
}
