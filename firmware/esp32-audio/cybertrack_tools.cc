#include "cybertrack_tools.h"
#include "control_sessions.h"
#include "web_server.h"
#include "action_outputs.h"
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/queue.h>
#include <algorithm>
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
ControlSessions sessions;
AudioActionGuard& guard = sessions.guard;
AudioActionOutputs outputs;
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
    sessions.Tick(now, gpio_get_level(stop_pin) == 0, outputs.fault);
}
struct OffEvent {
    const char* channel;
    const char* reason;
    uint64_t elapsed;
    unsigned starts;
    bool moving, watering;
};
StaticQueue_t event_queue_storage;
uint8_t event_queue_bytes[16 * sizeof(OffEvent)];
QueueHandle_t event_queue = xQueueCreateStatic(16, sizeof(OffEvent), event_queue_bytes, &event_queue_storage);
unsigned dropped_events = 0;
bool applied_move = false, applied_water = false;
uint64_t move_started = 0, water_started = 0;
void OffRecord(const char* channel, uint64_t started, uint64_t now, const water_policy& policy) {
    OffEvent event{channel, outputs.fault ? "output_fault" : policy.held ? "BOOT" :
        !policy.online ? "link_lost" : policy.clock_fault ? "clock_fault" : policy.stopped ? "stop" : "deadline",
        now - started, guard.Starts(), guard.Moving(), guard.Watering()};
    if (xQueueSend(event_queue, &event, 0) != pdTRUE) ++dropped_events;
}
void ApplyLocked(uint64_t now) {
    if (!outputs.Apply(guard.Watering(), guard.Moving() ? guard.left : 0,
                       guard.Moving() ? guard.right : 0)) guard.Stop(now);
    const bool moving = guard.Moving(), watering = guard.Watering();
    if (moving && !applied_move) move_started = now;
    if (watering && !applied_water) water_started = now;
    if (!moving && applied_move) OffRecord("move", move_started, now, guard.motion);
    if (!watering && applied_water) OffRecord("water", water_started, now, guard.spray);
    applied_move = moving; applied_water = watering;
}
void LogTask(void*) {
    OffEvent event{};
    for (;;) if (xQueueReceive(event_queue, &event, portMAX_DELAY) == pdTRUE) {
        auto elapsed = Decimal(event.elapsed);
        ESP_LOGI("CT_AUDIO", "ACTION_OFF channel=%s reason=%s software_on_ms=%s move=%s water=%s starts=%u",
                 event.channel, event.reason, elapsed.c_str(), event.moving ? "ON" : "OFF",
                 event.watering ? "ON" : "OFF", event.starts);
    }
}
void SafetyTask(void*) {
    ESP_ERROR_CHECK(esp_task_wdt_add(nullptr));
    for (;;) {
        xSemaphoreTake(lock, portMAX_DELAY);
        auto now = Now(); TickLocked(now); ApplyLocked(now);
        xSemaphoreGive(lock);
        // No serial, display, network or allocation here, even when one lane
        // stops while the other stays active. Logging uses a nonblocking queue.
        ESP_ERROR_CHECK(esp_task_wdt_reset());
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}
std::string Reply(const char* operation, int ticket = 0, int duration = 0, const char* direction = nullptr, int water_duration = 0,
                  uint32_t web_session = 0, const WebCommand* command = nullptr) {
    // Reserve before accepting an action.
    std::string result; result.reserve(1400);
    xSemaphoreTake(lock, portMAX_DELAY);
    auto now = Now(); TickLocked(now);
    const char* outcome = "ok";
    if (web_session && !sessions.Owns(web_session)) {
        outcome = "session_expired";
    } else if (web_session && !strcmp(operation, "get_status")) {
        if (!sessions.Heartbeat(now, web_session)) outcome = "session_expired";
    } else if (!strcmp(operation, "stop")) {
        sessions.Stop(now);
    } else if (web_session && !strcmp(operation, "release")) {
        sessions.Release(now, web_session);
    } else if (command) {
        if (!strcmp(operation, "drive_start"))
            outcome = sessions.DriveStart(now, web_session, command->sequence, command->window, direction, water_duration);
        else if (!strcmp(operation, "drive_renew"))
            outcome = sessions.DriveRenew(now, web_session, command->hold_id, command->renewal);
        else if (!strcmp(operation, "drive_stop"))
            outcome = sessions.DriveStop(now, web_session, command->hold_id);
        else
            outcome = sessions.WebAction(now, web_session, command->sequence, command->window,
                                         command->target, duration, water_duration, direction);

    } else if (!strcmp(operation, "water")) {
        outcome = guard.Water(now, ticket, duration);
    } else if (!strcmp(operation, "move")) {
        outcome = guard.Move(now, ticket, duration, direction);
    } else if (!strcmp(operation, "move_and_water")) {
        outcome = guard.MoveAndWater(now, ticket, duration, water_duration, direction);
    }
    // Apply before replying. Stop/BOOT/link and this path share one mutex.
    now = Now(); TickLocked(now);
    const bool requested_active = !strcmp(operation, "drive_start") ? guard.Moving() && (!water_duration || guard.Watering()) :
        (!strcmp(operation, "move") || !strcmp(operation, "drive_renew")) ? guard.Moving() :
        !strcmp(operation, "water") ? guard.Watering() : guard.Moving() && guard.Watering();
    if ((!strcmp(outcome, "accepted") || !strcmp(outcome, "renewed")) && !requested_active) {
        if (!strcmp(operation, "move_and_water") || !strcmp(operation, "drive_start")) sessions.Stop(now);
        outcome = "cancelled_before_output";
    }
    ApplyLocked(now);
    if (outputs.fault) outcome = "output_fault";
    const bool watering = guard.Watering(), moving = guard.Moving();
    const int left = moving ? guard.left : 0, right = moving ? guard.right : 0;
    const char* move_direction = moving ? guard.direction : "none";
    const bool fault = outputs.fault, clock_fault = guard.motion.clock_fault || guard.spray.clock_fault;
    const bool stopped = guard.motion.stopped && guard.spray.stopped;
    const unsigned starts = guard.Starts(), seq = ++sequence, lost = dropped_events;
    const unsigned last_duration = guard.last_duration_ms;
    const unsigned move_duration = guard.move_duration_ms, water_ms = guard.water_duration_ms;
    const unsigned move_remaining = AudioActionGuard::Remaining(guard.motion, now);
    const unsigned water_remaining = AudioActionGuard::Remaining(guard.spray, now);
    const unsigned window = sessions.window;
    const char* owner = sessions.owner ? (sessions.voice ? "shared" : "web") : sessions.voice ? "voice" : "none";
    const char* move_source = sessions.MoveSource();
    const char* water_source = sessions.WaterSource();
    const unsigned move_cooldown = guard.motion.cooldown_until > now ? guard.motion.cooldown_until - now : 0;
    const unsigned water_cooldown = guard.spray.cooldown_until > now ? guard.spray.cooldown_until - now : 0;
    const bool held = guard.motion.held;
    const unsigned drive_id = sessions.drive_id, drive_renewal = sessions.drive_renewal;
    xSemaphoreGive(lock);
    const auto uptime = Decimal(now);
    const char* state = (fault || clock_fault) ? "FAULT" : (moving || watering) ? "ACTIVE" : stopped ? "STOPPED" : "DISARMED";
    const char* reason = fault ? "output_fault" : clock_fault ? "clock_fault" : stopped ? "stopped" : "none";
    char json[2200];
    std::snprintf(json, sizeof(json),
        "{\"device_id\":\"%s\",\"boot_id\":\"%s\",\"request_sequence\":%u,\"operation\":\"%s\","
        "\"result\":\"%s\",\"state\":\"%s\",\"fault\":\"%s\",\"uptime_ms\":%s,"
        "\"logical_outputs\":{\"left\":%d,\"right\":%d,\"water\":%s,\"bubbles\":false},"
        "\"capabilities\":{\"move\":true,\"water\":true,\"move_and_water\":true,\"bubbles\":false},"
        "\"local_authorization_required\":false,\"starts_this_boot\":%u,\"max_duration_ms\":30000,\"last_duration_ms\":%u,\"remaining_ms\":%u,"
        "\"move_last_duration_ms\":%u,\"water_last_duration_ms\":%u,\"move_remaining_ms\":%u,\"water_remaining_ms\":%u,"
        "\"move_max_duration_ms\":3000,\"move_direction\":\"%s\",\"log_events_dropped\":%u,"
        "\"control_owner\":\"%s\",\"window\":%u,\"move_cooldown_ms\":%u,\"water_cooldown_ms\":%u,\"boot_held\":%s,"
        "\"move_source\":\"%s\",\"water_source\":\"%s\",\"drive_hold_id\":%u,\"drive_renewal\":%u,\"drive_lease_ms\":600,"
        "\"actuator_backend\":\"concurrent_motor_water_bench\",\"physical_feedback\":false,\"source\":\"cybertrack_audio_board\"}",
        device_id.c_str(), boot_id.c_str(), seq, operation, outcome, state, reason, uptime.c_str(),
        left, right, watering ? "true" : "false", starts, last_duration, std::max(move_remaining, water_remaining),
        move_duration, water_ms, move_remaining, water_remaining, move_direction, lost,
        owner, window, move_cooldown, water_cooldown, held ? "true" : "false", move_source, water_source, drive_id, drive_renewal);
    result.assign(json);
    if (!web_session || (strcmp(operation, "get_status") && strcmp(operation, "drive_renew")))
        ESP_LOGI("CT_AUDIO", "RESULT %s", result.c_str());
    return result;
}
}

int CyberTrackActionClaim(int rpc_id, const char* operation) {
    xSemaphoreTake(lock, portMAX_DELAY);
    auto now = Now(); TickLocked(now);
    const auto target = !strcmp(operation, "self.tank.move") ? AudioActionGuard::MoveOnly :
        !strcmp(operation, "self.tank.water") ? AudioActionGuard::WaterOnly : AudioActionGuard::Both;
    int ticket = sessions.VoiceClaim(now, rpc_id, target);
    xSemaphoreGive(lock);
    return ticket;
}
void CyberTrackActionStop() {
    xSemaphoreTake(lock, portMAX_DELAY);
    sessions.Stop(Now());
    if (initialized) ApplyLocked(Now());
    xSemaphoreGive(lock);
}
void CyberTrackActionLink(bool online) {
    xSemaphoreTake(lock, portMAX_DELAY);
    sessions.VoiceLink(Now(), online);
    if (initialized) { TickLocked(Now()); ApplyLocked(Now()); }
    xSemaphoreGive(lock);
}
void CyberTrackWifiLink(bool online) {
    xSemaphoreTake(lock, portMAX_DELAY);
    sessions.WifiLink(Now(), online);
    if (initialized) { TickLocked(Now()); ApplyLocked(Now()); }
    xSemaphoreGive(lock);
}
void CyberTrackShutdown() {
    xSemaphoreTake(lock, portMAX_DELAY);
    sessions.Shutdown(Now());
    if (initialized) ApplyLocked(Now());
    xSemaphoreGive(lock);
}
uint32_t CyberTrackWebAcquire() {
    xSemaphoreTake(lock, portMAX_DELAY);
    auto now = Now(); TickLocked(now);
    auto session = outputs.fault ? 0 : sessions.Acquire(now);
    TickLocked(now); ApplyLocked(now);
    xSemaphoreGive(lock);
    return session;
}
std::string CyberTrackWebCall(uint32_t session, const char* operation, const WebCommand* command) {
    if (!session) return "{\"result\":\"session_expired\"}";
    return Reply(operation, 0, command ? command->move_ms : 0,
                 command ? command->direction : nullptr, command ? command->water_ms : 0, session, command);
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
        [](void*, esp_event_base_t, int32_t, void*) { CyberTrackWifiLink(false); }, nullptr));
    if (xTaskCreate(LogTask, "action_log", 4096, nullptr, 1, nullptr) != pdPASS) {
        CyberTrackActionStop(); ESP_ERROR_CHECK(ESP_ERR_NO_MEM);
    }
    if (xTaskCreate(SafetyTask, "audio_actions", 4096, nullptr, 10, nullptr) != pdPASS) {
        CyberTrackActionStop(); ESP_ERROR_CHECK(ESP_ERR_NO_MEM);
    }
    InitializeCyberTrackWeb();
    auto& server = McpServer::GetInstance();
    server.AddTool("self.tank.get_status",
        "查询CyberTrack电机与水枪状态。网页与语音可同时使用，move_source/water_source 表示各通道动作来源；网页指令优先，全部停止始终有效。只有逻辑状态，没有轮速或水流反馈。",
        PropertyList(), [](const PropertyList&) -> ReturnValue { return Reply("get_status"); });
    server.AddTool("self.tank.stop",
        "立即停止两台电机和水枪并取消全部排队动作，不关闭语音和屏幕。",
        PropertyList(), [](const PropertyList&) -> ReturnValue { return Reply("stop"); });
    server.AddTool("self.tank.water",
        "用户明确要求喷水时直接调用，无需按键授权。duration_ms按用户时长换算为整数毫秒，范围1到30000；超过30秒只执行30秒并说明，明确要求喷水但未说时长时传1000。到期自动关闭，BOOT可提前停止。不得连续、延长或失败自动重试。可与行走同时执行、分别计时。同路正在执行时拒绝，结束后至少等待200毫秒，不排队补做。成功仅表示控制请求已接受。",
        PropertyList({Property("duration_ms", kPropertyTypeInteger, 1, 30000)}),
        [](const PropertyList& p) -> ReturnValue {
            return Reply("water", p["_ct_ticket"].value<int>(), p["duration_ms"].value<int>());
        });
    server.AddTool("self.tank.move",
        "仅在明确要求行走或转向时调用。direction只能为forward前进、backward后退、left向左原地转、right向右原地转。duration_ms为1到3000的整数毫秒；未说时长默认1000，超过三秒只请求3000并说明，不分段补足。不支持角度或距离精确控制。固定约60%速度，可与喷水同时执行、分别计时；同路运行中不续时或换向，行走结束后至少等待200毫秒。不得续时、自动重试或排队补做。BOOT或停止工具同时停止所有动作。回执不是实际移动反馈。",
        PropertyList({Property("direction", kPropertyTypeString), Property("duration_ms", kPropertyTypeInteger, 1, 3000)}),
        [](const PropertyList& p) -> ReturnValue {
            return Reply("move", p["_ct_ticket"].value<int>(), p["duration_ms"].value<int>(),
                         p["direction"].value<std::string>().c_str());
        });
    server.AddTool("self.tank.move_and_water",
        "用户明确要求边走边喷或同时转向喷水时调用，一次同时启动两路。direction为forward/backward/left/right，move_duration_ms为1到3000，water_duration_ms为1到30000；未指定时长各默认1000，分别限制上限不分段。两路必须均空闲且冷却结束，否则整项拒绝不部分启动。分别计时，到期只停止对应动作，BOOT或停止关闭两路。不保证精确距离、角度或实际动作反馈。",
        PropertyList({Property("direction", kPropertyTypeString), Property("move_duration_ms", kPropertyTypeInteger, 1, 3000),
                      Property("water_duration_ms", kPropertyTypeInteger, 1, 30000)}),
        [](const PropertyList& p) -> ReturnValue {
            return Reply("move_and_water", p["_ct_ticket"].value<int>(), p["move_duration_ms"].value<int>(),
                         p["direction"].value<std::string>().c_str(), p["water_duration_ms"].value<int>());
        });
    ESP_LOGI("CT_AUDIO", "READY tools=status,stop,water,move,move_and_water concurrent=true motor_A=8/9/10 motor_B=11/12/13 GPIO18=LOW BOOT=stop_all move_max_ms=3000 water_max_ms=30000");
}
