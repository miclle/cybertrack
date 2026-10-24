#include "cybertrack_tools.h"
#include "water_guard.h"
#include "mcp_server.h"
#include "system_info.h"
#include <cstring>
#include <charconv>
#include <cstdio>
#include <esp_timer.h>
#include <esp_random.h>
#include <esp_log.h>
#include <esp_event.h>
#include <esp_wifi.h>
#include <esp_task_wdt.h>
#include <driver/gpio.h>

namespace {
constexpr gpio_num_t output_pin = GPIO_NUM_18;
constexpr gpio_num_t stop_pin = GPIO_NUM_0;
portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
AudioWaterGuard guard;
bool link_online = false;
bool initialized = false;
bool output_fault = false;
unsigned sequence = 0;
std::string device_id, boot_id;
uint64_t Now() { return esp_timer_get_time() / 1000; }
std::string Decimal(uint64_t n) {
    char b[20]; auto r = std::to_chars(b, b + sizeof(b), n);
    return std::string(b, r.ptr);
}
void Token(char (&token)[33]) {
    unsigned char bytes[16]; esp_fill_random(bytes, sizeof(bytes));
    static const char hex[] = "0123456789abcdef";
    for (unsigned i = 0; i < 16; ++i) { token[2*i] = hex[bytes[i] >> 4]; token[2*i+1] = hex[bytes[i] & 15]; }
    token[32] = 0;
}
void TickLocked(uint64_t now) {
    guard.Tick(now, link_online && !output_fault, gpio_get_level(stop_pin) == 0);
}
void SafetyTask(void*) {
    ESP_ERROR_CHECK(esp_task_wdt_add(nullptr));
    bool was_on = false;
    uint64_t started = 0;
    for (;;) {
        portENTER_CRITICAL(&lock);
        auto now = Now();
        TickLocked(now);
        bool active = guard.policy.active;
        if (gpio_set_level(output_pin, active ? 1 : 0) != ESP_OK) {
            output_fault = true; guard.Stop(now); active = false;
            (void)gpio_set_level(output_pin, 0);
        }
        const auto snap = guard.policy;
        portEXIT_CRITICAL(&lock);
        if (active && !was_on) started = now;
        // No serial, display, network, or allocation in the active-output path.
        if (!active && was_on) {
            auto elapsed = Decimal(now - started);
            ESP_LOGI("CT_AUDIO", "WATER_OFF reason=%s software_on_ms=%s outputs=OFF starts=%u",
                     snap.held ? "BOOT" : !snap.online ? "link_lost" : snap.stopped ? "stop" : "deadline",
                     elapsed.c_str(), snap.starts);
        }
        was_on = active;
        ESP_ERROR_CHECK(esp_task_wdt_reset());
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}
std::string Reply(const char* operation, int ticket = 0, int duration = 0) {
    // Reserve before accepting an action.
    std::string result; result.reserve(1400);
    portENTER_CRITICAL(&lock);
    auto now = Now(); TickLocked(now);
    const char* outcome = "ok";
    if (!strcmp(operation, "stop")) {
        guard.Stop(now); (void)gpio_set_level(output_pin, 0);
    } else if (!strcmp(operation, "water")) {
        outcome = guard.Request(now, ticket, duration);
    }
    auto snap = guard.policy;
    const bool fault = output_fault;
    portEXIT_CRITICAL(&lock);
    const auto uptime = Decimal(now);
    const char* state = snap.active ? "ACTIVE" : (fault || snap.clock_fault) ? "FAULT" : snap.stopped ? "STOPPED" : "DISARMED";
    const char* reason = fault ? "output_fault" : snap.clock_fault ? "clock_fault" : snap.stopped ? "stopped" : "none";
    char json[1400];
    std::snprintf(json, sizeof(json),
        "{\"device_id\":\"%s\",\"boot_id\":\"%s\",\"request_sequence\":%u,\"operation\":\"%s\","
        "\"result\":\"%s\",\"state\":\"%s\",\"fault\":\"%s\",\"uptime_ms\":%s,"
        "\"logical_outputs\":{\"left\":0,\"right\":0,\"water\":%s,\"bubbles\":false},"
        "\"capabilities\":{\"move\":false,\"water\":true,\"bubbles\":false},"
        "\"local_authorization_required\":false,\"starts_this_boot\":%u,\"max_duration_ms\":5000,"
        "\"actuator_backend\":\"bounded_water_bench\",\"physical_feedback\":false,\"source\":\"cybertrack_audio_board\"}",
        device_id.c_str(), boot_id.c_str(), ++sequence, operation, outcome, state, reason, uptime.c_str(),
        snap.active ? "true" : "false", snap.starts);
    result.assign(json);
    ESP_LOGI("CT_AUDIO", "RESULT %s", result.c_str());
    return result;
}
}

int CyberTrackWaterClaim(int rpc_id) {
    portENTER_CRITICAL(&lock);
    auto now = Now(); TickLocked(now);
    int ticket = guard.Claim(now, rpc_id);
    portEXIT_CRITICAL(&lock);
    return ticket;
}
void CyberTrackWaterStop() {
    portENTER_CRITICAL(&lock);
    guard.Stop(Now());
    if (initialized) (void)gpio_set_level(output_pin, 0);
    portEXIT_CRITICAL(&lock);
}
void CyberTrackWaterLink(bool online) {
    portENTER_CRITICAL(&lock);
    link_online = online;
    if (initialized) TickLocked(Now());
    if (!online) {
        guard.Stop(Now());
        if (initialized) (void)gpio_set_level(output_pin, 0);
    }
    portEXIT_CRITICAL(&lock);
}
void InitializeCyberTrackTools() {
    (void)gpio_set_level(output_pin, 0);
    gpio_config_t output{}; output.pin_bit_mask = 1ULL << output_pin;
    output.mode = GPIO_MODE_OUTPUT; output.pull_down_en = GPIO_PULLDOWN_ENABLE;
    ESP_ERROR_CHECK(gpio_config(&output));
    ESP_ERROR_CHECK(gpio_set_level(output_pin, 0));
    gpio_config_t input{}; input.pin_bit_mask = 1ULL << stop_pin;
    input.mode = GPIO_MODE_INPUT; input.pull_up_en = GPIO_PULLUP_ENABLE;
    ESP_ERROR_CHECK(gpio_config(&input));
    initialized = true;
    device_id = SystemInfo::GetMacAddress();
    char token[33]; Token(token); boot_id.assign(token,16);
    // Wi-Fi loss cancels immediately, even before a socket disconnect is reported.
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, WIFI_EVENT_STA_DISCONNECTED,
        [](void*, esp_event_base_t, int32_t, void*) { CyberTrackWaterLink(false); }, nullptr));
    if (xTaskCreate(SafetyTask, "audio_water", 4096, nullptr, 10, nullptr) != pdPASS) {
        CyberTrackWaterStop(); ESP_ERROR_CHECK(ESP_ERR_NO_MEM);
    }
    auto& server = McpServer::GetInstance();
    server.AddTool("self.tank.get_status",
        "查询CyberTrack当前输出状态。只报告回执中的状态，没有水流反馈。",
        PropertyList(), [](const PropertyList&) -> ReturnValue { return Reply("get_status"); });
    server.AddTool("self.tank.stop",
        "立即关闭水枪输出并取消排队动作，不关闭语音和屏幕。",
        PropertyList(), [](const PropertyList&) -> ReturnValue { return Reply("stop"); });
    server.AddTool("self.tank.water",
        "用户明确要求喷水时直接调用，无需按键授权。duration_ms必须为5000；自动关闭，BOOT可提前停止。不得连续、延长或失败自动重试。成功仅表示控制输出已启动。",
        PropertyList({Property("duration_ms", kPropertyTypeInteger, 5000, 5000)}),
        [](const PropertyList& p) -> ReturnValue {
            return Reply("water", p["_ct_ticket"].value<int>(), p["duration_ms"].value<int>());
        });
    ESP_LOGI("CT_AUDIO", "READY tools=status,stop,water GPIO18=LOW BOOT=stop_only direct_voice=true max_ms=5000");
}
