#include "cybertrack_tools.h"
#include "action_guard.h"
#include "action_outputs.h"
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
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
constexpr gpio_num_t stop_pin = GPIO_NUM_0;
StaticSemaphore_t lock_storage;
SemaphoreHandle_t lock = xSemaphoreCreateMutexStatic(&lock_storage);
AudioActionGuard guard;
AudioActionOutputs outputs;
bool link_online = false;
bool initialized = false;
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
    guard.Tick(now, link_online && !outputs.fault, gpio_get_level(stop_pin) == 0);
}
void SafetyTask(void*) {
    ESP_ERROR_CHECK(esp_task_wdt_add(nullptr));
    bool was_on = false;
    uint64_t started = 0;
    for (;;) {
        xSemaphoreTake(lock, portMAX_DELAY);
        auto now = Now();
        TickLocked(now);
        if (!outputs.Apply(guard.Watering(), guard.Moving() ? guard.left : 0,
                           guard.Moving() ? guard.right : 0)) guard.Stop(now);
        bool active = guard.bounded.policy.active;
        const auto snap = guard.bounded.policy;
        xSemaphoreGive(lock);
        if (active && !was_on) started = now;
        // No serial, display, network, or allocation in the active-output path.
        if (!active && was_on) {
            auto elapsed = Decimal(now - started);
            ESP_LOGI("CT_AUDIO", "ACTION_OFF reason=%s software_on_ms=%s outputs=OFF starts=%u",
                     snap.held ? "BOOT" : !snap.online ? "link_lost" : snap.stopped ? "stop" : "deadline",
                     elapsed.c_str(), snap.starts);
        }
        was_on = active;
        ESP_ERROR_CHECK(esp_task_wdt_reset());
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}
std::string Reply(const char* operation, int ticket = 0, int duration = 0, const char* direction = nullptr) {
    // Reserve before accepting an action.
    std::string result; result.reserve(1400);
    xSemaphoreTake(lock, portMAX_DELAY);
    auto now = Now(); TickLocked(now);
    const char* outcome = "ok";
    if (!strcmp(operation, "stop")) {
        guard.Stop(now);
    } else if (!strcmp(operation, "water")) {
        outcome = guard.Water(now, ticket, duration);
    } else if (!strcmp(operation, "move")) {
        outcome = guard.Move(now, ticket, duration, direction);
    }
    // Apply before replying. Stop/BOOT/link and this path share one mutex.
    now = Now(); TickLocked(now);
    if (!strcmp(outcome, "accepted") && !guard.bounded.policy.active)
        outcome = "cancelled_before_output";
    if (!outputs.Apply(guard.Watering(), guard.Moving() ? guard.left : 0,
                       guard.Moving() ? guard.right : 0)) {
        guard.Stop(Now()); outcome = "output_fault";
    }
    const bool watering = guard.Watering(), moving = guard.Moving();
    const int left = moving ? guard.left : 0, right = moving ? guard.right : 0;
    const char* move_direction = moving ? guard.direction : "none";
    auto snap = guard.bounded.policy;
    const bool fault = outputs.fault;
    const unsigned last_duration = guard.bounded.last_duration_ms;
    const unsigned remaining = snap.active && snap.ends_at > now ? snap.ends_at - now : 0;
    xSemaphoreGive(lock);
    const auto uptime = Decimal(now);
    const char* state = snap.active ? "ACTIVE" : (fault || snap.clock_fault) ? "FAULT" : snap.stopped ? "STOPPED" : "DISARMED";
    const char* reason = fault ? "output_fault" : snap.clock_fault ? "clock_fault" : snap.stopped ? "stopped" : "none";
    char json[1400];
    std::snprintf(json, sizeof(json),
        "{\"device_id\":\"%s\",\"boot_id\":\"%s\",\"request_sequence\":%u,\"operation\":\"%s\","
        "\"result\":\"%s\",\"state\":\"%s\",\"fault\":\"%s\",\"uptime_ms\":%s,"
        "\"logical_outputs\":{\"left\":%d,\"right\":%d,\"water\":%s,\"bubbles\":false},"
        "\"capabilities\":{\"move\":true,\"water\":true,\"bubbles\":false},"
        "\"local_authorization_required\":false,\"starts_this_boot\":%u,\"max_duration_ms\":30000,\"last_duration_ms\":%u,\"remaining_ms\":%u,"
        "\"move_max_duration_ms\":3000,\"move_direction\":\"%s\",\"actuator_backend\":\"bounded_motor_water_bench\",\"physical_feedback\":false,\"source\":\"cybertrack_audio_board\"}",
        device_id.c_str(), boot_id.c_str(), ++sequence, operation, outcome, state, reason, uptime.c_str(),
        left, right, watering ? "true" : "false", snap.starts, last_duration, remaining, move_direction);
    result.assign(json);
    ESP_LOGI("CT_AUDIO", "RESULT %s", result.c_str());
    return result;
}
}

int CyberTrackActionClaim(int rpc_id) {
    xSemaphoreTake(lock, portMAX_DELAY);
    auto now = Now(); TickLocked(now);
    int ticket = guard.Claim(now, rpc_id);
    xSemaphoreGive(lock);
    return ticket;
}
void CyberTrackActionStop() {
    xSemaphoreTake(lock, portMAX_DELAY);
    guard.Stop(Now());
    if (initialized) (void)outputs.Apply(false, 0, 0);
    xSemaphoreGive(lock);
}
void CyberTrackActionLink(bool online) {
    xSemaphoreTake(lock, portMAX_DELAY);
    link_online = online;
    if (initialized) TickLocked(Now());
    if (!online) {
        guard.Stop(Now());
        if (initialized) (void)outputs.Apply(false, 0, 0);
    }
    xSemaphoreGive(lock);
}
void InitializeCyberTrackTools() {
    // Initialization errors latch an unavailable backend; never reboot into a retry.
    (void)outputs.Init();
    gpio_config_t input{}; input.pin_bit_mask = 1ULL << stop_pin;
    input.mode = GPIO_MODE_INPUT; input.pull_up_en = GPIO_PULLUP_ENABLE;
    ESP_ERROR_CHECK(gpio_config(&input));
    initialized = true;
    device_id = SystemInfo::GetMacAddress();
    char token[33]; Token(token); boot_id.assign(token,16);
    // Wi-Fi loss cancels immediately, even before a socket disconnect is reported.
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, WIFI_EVENT_STA_DISCONNECTED,
        [](void*, esp_event_base_t, int32_t, void*) { CyberTrackActionLink(false); }, nullptr));
    if (xTaskCreate(SafetyTask, "audio_actions", 4096, nullptr, 10, nullptr) != pdPASS) {
        CyberTrackActionStop(); ESP_ERROR_CHECK(ESP_ERR_NO_MEM);
    }
    auto& server = McpServer::GetInstance();
    server.AddTool("self.tank.get_status",
        "查询CyberTrack电机与水枪状态。只有逻辑状态，没有轮速或水流反馈。",
        PropertyList(), [](const PropertyList&) -> ReturnValue { return Reply("get_status"); });
    server.AddTool("self.tank.stop",
        "立即停止两台电机和水枪并取消全部排队动作，不关闭语音和屏幕。",
        PropertyList(), [](const PropertyList&) -> ReturnValue { return Reply("stop"); });
    server.AddTool("self.tank.water",
        "用户明确要求喷水时直接调用，无需按键授权。duration_ms按用户时长换算为整数毫秒，范围1到30000；超过30秒只执行30秒并说明，明确要求喷水但未说时长时传1000。到期自动关闭，BOOT可提前停止。不得连续、延长或失败自动重试。与行走互斥，不排队补做。成功仅表示控制请求已接受。",
        PropertyList({Property("duration_ms", kPropertyTypeInteger, 1, 30000)}),
        [](const PropertyList& p) -> ReturnValue {
            return Reply("water", p["_ct_ticket"].value<int>(), p["duration_ms"].value<int>());
        });
    server.AddTool("self.tank.move",
        "仅在明确要求行走或转向时调用。direction只能为forward前进、backward后退、left向左原地转、right向右原地转。duration_ms为1到3000的整数毫秒；未说时长默认1000，超过三秒只请求3000并说明，不分段补足。不支持角度或距离精确控制。固定约60%速度，与喷水互斥，结束后至少等待三秒。不得续时、自动重试或排队补做。BOOT或停止工具同时停止所有动作。回执不是实际移动反馈。",
        PropertyList({Property("direction", kPropertyTypeString), Property("duration_ms", kPropertyTypeInteger, 1, 3000)}),
        [](const PropertyList& p) -> ReturnValue {
            return Reply("move", p["_ct_ticket"].value<int>(), p["duration_ms"].value<int>(),
                         p["direction"].value<std::string>().c_str());
        });
    ESP_LOGI("CT_AUDIO", "READY tools=status,stop,water,move motor_A=8/9/10 motor_B=11/12/13 GPIO18=LOW BOOT=stop_all move_max_ms=3000 water_max_ms=30000");
}
