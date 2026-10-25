#ifndef BENCH_IDF_STUB_H
#define BENCH_IDF_STUB_H
/* Minimal host boundary for exercising the real motor_bench.c task. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef int esp_err_t;
typedef int ledc_channel_t;
typedef void *QueueHandle_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define GPIO_NUM_0 0
#define GPIO_NUM_4 4
#define GPIO_NUM_5 5
#define GPIO_NUM_6 6
#define GPIO_NUM_7 7
#define GPIO_NUM_8 8
#define GPIO_NUM_9 9
#define GPIO_MODE_OUTPUT 1
#define GPIO_MODE_INPUT 2
#define GPIO_PULLDOWN_ENABLE 1
#define GPIO_PULLUP_ENABLE 1
#define LEDC_LOW_SPEED_MODE 0
#define LEDC_CHANNEL_0 0
#define LEDC_CHANNEL_1 1
#define LEDC_TIMER_0 0
#define LEDC_TIMER_8_BIT 8
#define LEDC_AUTO_CLK 0
#define UART_NUM_0 0
#define UART_DATA_8_BITS 8
#define UART_PARITY_DISABLE 0
#define UART_STOP_BITS_1 1
#define UART_HW_FLOWCTRL_DISABLE 0
#define UART_SCLK_DEFAULT 0
#define UART_DATA 0
#define UART_FIFO_OVF 1
#define pdTRUE 1
#define pdMS_TO_TICKS(ms) (ms)
typedef struct { uint64_t pin_bit_mask; int mode, pull_down_en, pull_up_en; } gpio_config_t;
typedef struct { int speed_mode, duty_resolution, timer_num, freq_hz, clk_cfg; } ledc_timer_config_t;
typedef struct { int gpio_num, speed_mode, channel, timer_sel, duty; } ledc_channel_config_t;
typedef struct { int baud_rate, data_bits, parity, stop_bits, flow_ctrl, source_clk; } uart_config_t;
typedef struct { int type; } uart_event_t;
esp_err_t gpio_set_level(int pin, uint32_t level);
esp_err_t gpio_set_direction(int pin, int mode);
esp_err_t gpio_config(const gpio_config_t *config);
int gpio_get_level(int pin);
esp_err_t ledc_stop(int mode, int channel, uint32_t idle_level);
esp_err_t ledc_timer_config(const ledc_timer_config_t *config);
esp_err_t ledc_channel_config(const ledc_channel_config_t *config);
esp_err_t ledc_set_duty(int mode, int channel, uint32_t duty);
esp_err_t ledc_update_duty(int mode, int channel);
esp_err_t uart_param_config(int port, const uart_config_t *config);
esp_err_t uart_driver_install(int port, int rx, int tx, int event_count, QueueHandle_t *queue, int flags);
esp_err_t uart_flush_input(int port);
esp_err_t uart_get_buffered_data_len(int port, size_t *size);
int uart_read_bytes(int port, void *buffer, uint32_t size, uint32_t ticks);
int xQueueReceive(QueueHandle_t queue, void *event, uint32_t ticks);
esp_err_t esp_task_wdt_add(void *task);
esp_err_t esp_task_wdt_reset(void);
int64_t esp_timer_get_time(void);
const char *esp_err_to_name(esp_err_t error);
void vTaskDelay(uint32_t ticks);
#endif
