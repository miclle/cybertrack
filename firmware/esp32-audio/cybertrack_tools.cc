#include "cybertrack_tools.h"
#include "control_sessions.h"
#include "action_plan_json.h"
#include "recent_command.h"
#include "status_facts.h"
#include "draft_duration_intent.h"
#include "web_server.h"
#include "action_outputs.h"
#include "ultrasonic.h"
#include "proximity_audio.h"
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
ProximityGuard proximity;
AudioActionGuard& guard = sessions.guard;
AudioActionOutputs outputs;
bool initialized = false;
unsigned sequence = 0;
RecentCommand recent_command;
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
    const bool pressed = gpio_get_level(stop_pin) == 0;
    const bool forward = guard.Moving() && !std::strcmp(guard.direction, "forward") &&
                         now >= guard.motion.last_ms && now < guard.motion.ends_at && !pressed && !outputs.fault;
    auto alert = proximity.Update(CyberTrackDistanceSnapshot(), now, forward, sessions.auto_avoidance_enabled);
    // Update the interlock before Tick can start another sequence step/effect.
    sessions.SetForwardBlocked(now, proximity.blocked);
    sessions.Tick(now, pressed, outputs.fault);
    CyberTrackProximityAlert(alert, proximity.beeping);
}
struct OffEvent {
    const char* channel;
    const char* reason;
    uint64_t elapsed;
    unsigned starts;
    bool moving, watering, bubbling, igniting;
    AudioActionOutputs::WaterPadTrace water_pad;
};
StaticQueue_t event_queue_storage;
uint8_t event_queue_bytes[16 * sizeof(OffEvent)];
QueueHandle_t event_queue = xQueueCreateStatic(16, sizeof(OffEvent), event_queue_bytes, &event_queue_storage);
unsigned dropped_events = 0;
bool applied_move = false, applied_water = false, applied_bubbles = false, applied_ignition = false;
uint64_t move_started = 0, water_started = 0, bubbles_started = 0, ignition_started = 0;
void OffRecord(const char* channel, uint64_t started, uint64_t now, const water_policy& policy) {
    OffEvent event{channel, outputs.fault ? "output_fault" : policy.held ? "BOOT" :
        !policy.online ? "link_lost" : policy.clock_fault ? "clock_fault" : (!std::strcmp(channel, "move") && guard.forward_blocked) ? "obstacle" : policy.stopped ? "stop" : "deadline",
        now - started, guard.Starts(), guard.Moving(), guard.Watering(), guard.Bubbling(), guard.Igniting(), outputs.water_pad};
    if (xQueueSend(event_queue, &event, 0) != pdTRUE) ++dropped_events;
}
void ApplyLocked(uint64_t now) {
    if (!outputs.Apply(guard.Watering(), guard.Moving() ? guard.left : 0,
                       guard.Moving() ? guard.right : 0, guard.Bubbling(), guard.Igniting())) sessions.Stop(now);
    const bool moving = guard.Moving(), watering = guard.Watering(), bubbling = guard.Bubbling(), igniting = guard.Igniting();
    if (moving && !applied_move) move_started = now;
    if (watering && !applied_water) water_started = now;
    if (!moving && applied_move) OffRecord("move", move_started, now, guard.motion);
    if (!watering && applied_water) OffRecord("water", water_started, now, guard.spray);
    if (bubbling && !applied_bubbles) bubbles_started = now;
    if (igniting && !applied_ignition) ignition_started = now;
    if (!bubbling && applied_bubbles) OffRecord("bubbles", bubbles_started, now, guard.bubbles);
    if (!igniting && applied_ignition) OffRecord("ignition", ignition_started, now, guard.ignition);
    applied_move = moving; applied_water = watering; applied_bubbles = bubbling; applied_ignition = igniting;
}
void LogTask(void*) {
    OffEvent event{};
    for (;;) if (xQueueReceive(event_queue, &event, portMAX_DELAY) == pdTRUE) {
        auto elapsed = Decimal(event.elapsed);
        ESP_LOGI("CT_AUDIO", "ACTION_OFF channel=%s reason=%s software_on_ms=%s move=%s water=%s bubbles=%s ignition=%s starts=%u",
                 event.channel, event.reason, elapsed.c_str(), event.moving ? "ON" : "OFF",
                 event.watering ? "ON" : "OFF", event.bubbling ? "ON" : "OFF", event.igniting ? "ON" : "OFF", event.starts);
        if (!std::strcmp(event.channel, "water")) {
            const auto& pad = event.water_pad;
            ESP_LOGI("CT_AUDIO", "WATER_PAD pin=18 high_samples=%u low_samples=%u motor_high_samples=%u motor_low_samples=%u first=%d last_on=%d after_off=%d starts=%u",
                     pad.high, pad.low, pad.motor_high, pad.motor_low, pad.first, pad.last, pad.off, event.starts);
        }
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
std::string Reply(int voice_turn, const char* operation, int ticket = 0, int duration = 0, const char* direction = nullptr, int water_duration = 0,
                  uint32_t web_session = 0, const WebCommand* command = nullptr, const ActionPlan* plan = nullptr, int speed_percent = 100, const ShowDraft::Command* edit = nullptr) {
    // A validated stop runs synchronously. Apply it before receipt allocation;
    // a later input or reporting failure must never defer the output shutdown.
    if (!web_session && !strcmp(operation, "stop")) {
        xSemaphoreTake(lock, portMAX_DELAY);
        sessions.Stop(Now());
        ApplyLocked(Now());
        xSemaphoreGive(lock);
    }
    // Reserve before accepting an action.
    std::string result; result.reserve(7000);
    xSemaphoreTake(lock, portMAX_DELAY);
    auto now = Now(); TickLocked(now);
    const char* outcome = "ok";
    if (voice_turn >= 0 && strcmp(operation, "stop") && voice_turn != sessions.voice_turn) {
        outcome = "voice_input_changed";
    } else if (voice_turn >= 0 && strcmp(operation, "stop") && strcmp(operation, "get_status") && !sessions.VoiceTurnReady(voice_turn)) {
        outcome = "voice_input_failed";
    } else if (voice_turn >= 0 && sessions.voice_draft_unquantified && strcmp(operation, "stop") && strcmp(operation, "get_status")) {
        outcome = "draft_duration_unspecified";
    } else if (web_session && !sessions.Owns(web_session)) {
        outcome = "session_expired";
    } else if (web_session && !strcmp(operation, "get_status")) {
        if (!sessions.Heartbeat(now, web_session)) outcome = "session_expired";
    } else if (web_session && !strcmp(operation, "stop")) {
        sessions.Stop(now);
    } else if (web_session && !strcmp(operation, "release")) {
        sessions.Release(now, web_session);
    } else if (command) {
        if (!strcmp(operation, "show_edit"))
            outcome = sessions.WebDraft(now, web_session, command->sequence, command->window, command->draft);
        else if (!strcmp(operation, "show_confirm"))
            outcome = sessions.WebConfirm(now, web_session, command->sequence, command->window, command->draft.revision);
        else if (!strcmp(operation, "set_auto_avoidance"))
            outcome = sessions.WebAutoAvoidance(now, web_session, command->sequence, command->window, command->enabled);
        else if (!strcmp(operation, "set_speed"))
            outcome = sessions.WebSpeed(now, web_session, command->sequence, command->window, command->speed_percent);
        else if (!strcmp(operation, "frenzy"))
            outcome = sessions.FrenzyStart(now, web_session, command->sequence, command->window, command->frenzy_ms);
        else if (!strcmp(operation, "drive_start"))
            outcome = sessions.DriveStart(now, web_session, command->sequence, command->window, direction, water_duration);
        else if (!strcmp(operation, "drive_renew"))
            outcome = sessions.DriveRenew(now, web_session, command->hold_id, command->renewal);
        else if (!strcmp(operation, "drive_stop"))
            outcome = sessions.DriveStop(now, web_session, command->hold_id);
        else if (!strcmp(operation, "water_start") || !strcmp(operation, "bubbles_start"))
            outcome = sessions.EffectStart(now, web_session, command->sequence, command->window, command->target);
        else if (!strcmp(operation, "water_renew") || !strcmp(operation, "bubbles_renew"))
            outcome = sessions.EffectRenew(now, web_session, command->target, command->hold_id, command->renewal);
        else if (!strcmp(operation, "water_stop") || !strcmp(operation, "bubbles_stop"))
            outcome = sessions.EffectStop(now, web_session, command->target, command->hold_id);
        else
            outcome = sessions.WebAction(now, web_session, command->sequence, command->window,
                                         command->target, duration, water_duration, direction, command->bubbles_ms, command->ignition_ms);

    } else if (edit) {
        outcome = sessions.VoiceDraft(now, ticket, *edit);
    } else if (!strcmp(operation, "set_speed")) {
        outcome = sessions.VoiceSetSpeed(now, ticket, duration);
    } else if (!strcmp(operation, "adjust_speed")) {
        outcome = sessions.VoiceAdjustSpeed(now, ticket, duration);
    } else if (plan) {
        outcome = sessions.VoicePlan(now, ticket, *plan);
    } else if (!strcmp(operation, "frenzy")) {
        outcome = sessions.VoiceFrenzy(now, ticket, duration);
    } else if (!strcmp(operation, "water")) {
        outcome = guard.Water(now, ticket, duration);
    } else if (!strcmp(operation, "bubbles")) {
        outcome = guard.Bubbles(now, ticket, duration);
    } else if (!strcmp(operation, "ignition")) {
        outcome = guard.Ignition(now, ticket, duration);
    } else if (!strcmp(operation, "move")) {
        outcome = guard.Move(now, ticket, duration, direction, speed_percent);
    } else if (!strcmp(operation, "move_and_water")) {
        outcome = guard.MoveAndWater(now, ticket, duration, water_duration, direction, speed_percent);
    }
    // Apply before replying. Stop/BOOT/link and this path share one mutex.
    now = Now(); TickLocked(now);
    // Reject an expired first step before applying any output, just like the two-lane tool.
    const bool plan_started = plan && sessions.plan_active && sessions.plan_step == 1 &&
        (!plan->steps[0].move_ms || guard.Moving()) && (!plan->steps[0].water_ms || guard.Watering()) &&
        (!plan->steps[0].bubbles_ms || guard.Bubbling()) && (!plan->steps[0].ignition_ms || guard.Igniting());
    const bool requested_active = !strcmp(operation, "show_confirm") ? sessions.plan_step == 1 && sessions.PlanStepActive() : plan ? plan_started : !strcmp(operation, "frenzy") ? sessions.frenzy_until && guard.Moving() && guard.Watering() && guard.Bubbling() :
        !strcmp(operation, "drive_start") ? guard.Moving() && (!water_duration || guard.Watering()) :
        (!strcmp(operation, "move") || !strcmp(operation, "set_speed") || !strcmp(operation, "adjust_speed") || !strcmp(operation, "drive_renew")) ? guard.Moving() :
        (!strcmp(operation, "water") || !strcmp(operation, "water_start") || !strcmp(operation, "water_renew")) ? guard.Watering() :
        (!strcmp(operation, "bubbles") || !strcmp(operation, "bubbles_start") || !strcmp(operation, "bubbles_renew")) ? guard.Bubbling() :
        !strcmp(operation, "ignition") ? guard.Igniting() : guard.Moving() && guard.Watering();
    if ((!strcmp(outcome, "accepted") || !strcmp(outcome, "renewed")) && !requested_active) {
        if (plan || !strcmp(operation, "show_confirm") || !strcmp(operation, "move_and_water") || !strcmp(operation, "drive_start") || !strcmp(operation, "frenzy")) sessions.Stop(now);
        if (plan || !strcmp(operation, "show_confirm")) sessions.plan_result = "cancelled";
        outcome = "cancelled_before_output";
    }
    ApplyLocked(now);
    if (outputs.fault) outcome = "output_fault";
    if (voice_turn >= 0 && strcmp(outcome, "ok") && strcmp(outcome, "accepted") &&
        strcmp(outcome, "draft_saved") && strcmp(outcome, "draft_cancelled"))
        sessions.FailVoiceTurn(voice_turn);
    const bool watering = guard.Watering(), moving = guard.Moving(), bubbling = guard.Bubbling(), igniting = guard.Igniting();
    const int left = moving ? guard.left : 0, right = moving ? guard.right : 0;
    const char* move_direction = moving ? guard.direction : "none";
    const bool fault = outputs.fault, clock_fault = guard.motion.clock_fault || guard.spray.clock_fault || guard.bubbles.clock_fault || guard.ignition.clock_fault;
    const bool stopped = guard.motion.stopped && guard.spray.stopped && guard.bubbles.stopped && guard.ignition.stopped;
    const unsigned starts = guard.Starts(), seq = ++sequence, lost = dropped_events;
    const unsigned last_duration = guard.last_duration_ms;
    const unsigned move_duration = guard.move_duration_ms, water_ms = guard.water_duration_ms;
    const unsigned move_remaining = AudioActionGuard::Remaining(guard.motion, now);
    const unsigned water_remaining = AudioActionGuard::Remaining(guard.spray, now);
    const unsigned bubbles_ms = guard.bubbles_duration_ms, ignition_ms = guard.ignition_duration_ms;
    const unsigned bubbles_remaining = AudioActionGuard::Remaining(guard.bubbles, now);
    const unsigned ignition_remaining = AudioActionGuard::Remaining(guard.ignition, now);
    const char* bubbles_source = sessions.BubblesSource();
    const char* ignition_source = sessions.IgnitionSource();
    const unsigned bubbles_cooldown = guard.bubbles.cooldown_until > now ? guard.bubbles.cooldown_until - now : 0;
    const unsigned ignition_cooldown = guard.ignition.cooldown_until > now ? guard.ignition.cooldown_until - now : 0;
    const unsigned window = sessions.window;
    const char* owner = sessions.owner ? (sessions.voice ? "shared" : "web") : sessions.voice ? "voice" : "none";
    const char* move_source = sessions.MoveSource();
    const char* water_source = sessions.WaterSource();
    const unsigned move_cooldown = guard.motion.cooldown_until > now ? guard.motion.cooldown_until - now : 0;
    const unsigned water_cooldown = guard.spray.cooldown_until > now ? guard.spray.cooldown_until - now : 0;
    const bool held = guard.motion.held;
    const unsigned drive_id = sessions.drive_id, drive_renewal = sessions.drive_renewal;
    const char* frenzy_source = sessions.FrenzySource();
    const unsigned frenzy_duration = sessions.frenzy_duration_ms;
    const unsigned frenzy_remaining = sessions.frenzy_until > now ? sessions.frenzy_until - now : 0;
    const auto water_hold = sessions.water_hold, bubbles_hold = sessions.bubbles_hold;
    const int web_speed = sessions.web_speed_percent;
    const int move_speed = moving ? (left < 0 ? -left : left) : 0;
    const bool forward_blocked = guard.forward_blocked;
    const bool auto_avoidance_enabled = sessions.auto_avoidance_enabled;
    const bool plan_active = sessions.plan_active;
    const unsigned plan_step = sessions.plan_step, plan_count = sessions.plan_count;
    const char* plan_result = sessions.plan_result;
    recent_command.Record(now, operation, outcome, web_session != 0);
    const auto recent = recent_command;
    if (!web_session && !strcmp(operation, "get_status") && !strcmp(outcome, "ok")) sessions.ObserveVoiceDraft(now);
    const auto draft = sessions.draft;
    const auto plan_source = sessions.PlanSource();
    xSemaphoreGive(lock);
    const auto uptime = Decimal(now);
    const auto recent_age = recent.valid && now >= recent.at ? Decimal(now - recent.at) : "null";
    const char* state = (fault || clock_fault) ? "FAULT" : (moving || watering || bubbling || igniting || plan_active) ? "ACTIVE" : stopped ? "STOPPED" : "DISARMED";
    const char* reason = fault ? "output_fault" : clock_fault ? "clock_fault" : stopped ? "stopped" : "none";
    char json[3600];
    // Snapshot outside the action mutex; status/voice never wait for an echo.
    const auto reading = CyberTrackDistanceSnapshot();
    const auto distance = ultrasonic::Json(reading, Now());
    std::snprintf(json, sizeof(json),
        "{\"device_id\":\"%s\",\"boot_id\":\"%s\",\"request_sequence\":%u,\"operation\":\"%s\","
        "\"result\":\"%s\",\"state\":\"%s\",\"fault\":\"%s\",\"uptime_ms\":%s,"
        "\"logical_outputs\":{\"left\":%d,\"right\":%d,\"water\":%s,\"bubbles\":%s,\"ignition\":%s},"
        "\"capabilities\":{\"show_draft\":true,\"distance\":true,\"forward_protection\":true,\"auto_avoidance\":false,\"speed_control\":true,\"sequence\":true,\"frenzy\":true,\"water_hold\":true,\"bubbles_hold\":true,\"move\":true,\"water\":true,\"move_and_water\":true,\"bubbles\":true,\"ignition\":true},"
        "\"local_authorization_required\":false,\"starts_this_boot\":%u,\"max_duration_ms\":30000,\"last_duration_ms\":%u,\"remaining_ms\":%u,"
        "\"move_last_duration_ms\":%u,\"water_last_duration_ms\":%u,\"move_remaining_ms\":%u,\"water_remaining_ms\":%u,"
        "\"web_speed_percent\":%d,\"move_speed_percent\":%d,\"speed_min_percent\":60,\"speed_max_percent\":100,"
        "\"move_max_duration_ms\":2147483647,\"move_direction\":\"%s\",\"log_events_dropped\":%u,"
        "\"control_owner\":\"%s\",\"window\":%u,\"move_cooldown_ms\":%u,\"water_cooldown_ms\":%u,\"boot_held\":%s,"
        "\"move_source\":\"%s\",\"water_source\":\"%s\",\"drive_hold_id\":%u,\"drive_renewal\":%u,\"drive_lease_ms\":600,"
        "\"water_hold_id\":%u,\"water_renewal\":%u,\"bubbles_hold_id\":%u,\"bubbles_renewal\":%u,\"effect_lease_ms\":600,"
        "\"bubbles_last_duration_ms\":%u,\"ignition_last_duration_ms\":%u,\"bubbles_remaining_ms\":%u,\"ignition_remaining_ms\":%u,"
        "\"bubbles_max_duration_ms\":30000,\"ignition_max_duration_ms\":5000,\"bubbles_cooldown_ms\":%u,\"ignition_cooldown_ms\":%u,"
        "\"bubbles_source\":\"%s\",\"ignition_source\":\"%s\","
        "\"frenzy_remaining_ms\":%u,\"frenzy_last_duration_ms\":%u,\"frenzy_source\":\"%s\",\"frenzy_max_duration_ms\":30000,\"ignition_cooldown_policy\":\"equal_elapsed_on_time\", "
        "\"sequence_active\":%s,\"sequence_step\":%u,\"sequence_steps\":%u,\"sequence_result\":\"%s\",\"sequence_max_steps\":16,"
        "\"proximity\":{\"auto_avoidance_enabled\":%s,\"forward_blocked\":%s,\"warn_below_mm\":500,\"stop_below_mm\":150,\"release_mm\":200},"
        "\"recent_command\":{\"valid\":%s,\"operation\":\"%s\",\"result\":\"%s\",\"source\":\"%s\",\"age_ms\":%s},"
        "\"distance\":%s,\"actuator_backend\":\"concurrent_motor_effects_bench\",\"physical_feedback\":false,\"source\":\"cybertrack_audio_board\"}",
        device_id.c_str(), boot_id.c_str(), seq, operation, outcome, state, reason, uptime.c_str(),
        left, right, watering ? "true" : "false", bubbling ? "true" : "false", igniting ? "true" : "false",
        starts, last_duration, std::max({move_remaining, water_remaining, bubbles_remaining, ignition_remaining}),
        move_duration, water_ms, move_remaining, water_remaining, web_speed, move_speed, move_direction, lost,
        owner, window, move_cooldown, water_cooldown, held ? "true" : "false", move_source, water_source, drive_id, drive_renewal,
        static_cast<unsigned>(water_hold.id), static_cast<unsigned>(water_hold.renewal),
        static_cast<unsigned>(bubbles_hold.id), static_cast<unsigned>(bubbles_hold.renewal),
        bubbles_ms, ignition_ms, bubbles_remaining, ignition_remaining, bubbles_cooldown, ignition_cooldown, bubbles_source, ignition_source, frenzy_remaining, frenzy_duration, frenzy_source, plan_active ? "true" : "false", plan_step, plan_count, plan_result, auto_avoidance_enabled ? "true" : "false", forward_blocked ? "true" : "false", recent.valid ? "true" : "false", recent.operation, recent.result,
        recent.valid ? (recent.web ? "web" : "voice") : "none", recent_age.c_str(), distance.c_str());
    result.assign(json);
    result.pop_back();
    if (!strcmp(outcome, "draft_duration_unspecified"))
        result += ",\"clarification_facts\":\"本轮识别到相对长短表达，但未识别到量化时长。这次没有修改草稿或新启动动作。只问具体改成几秒，不猜半秒或减半，不自动重试、删除、取消或改用动作工具补做。\"";
    if (!strcmp(operation, "get_status")) {
        result += ",\"draft_status_facts\":\"" + std::string(DraftReadFacts(draft.active)) + "\"";
        if (const char* guidance = FaultRecovery(reason))
            result += ",\"fault_recovery\":\"" + std::string(guidance) + "\"";
        auto facts = StatusFacts(reason, forward_blocked, plan_active,
            moving || watering || bubbling || igniting, recent.valid ? recent.result : "");
        if (drive_id) facts += "行走由网页长按控制，无法预知还会走多久。";
        if (water_hold.id) facts += "喷水由网页长按控制，无法预知还会喷多久。";
        if (bubbles_hold.id) facts += "吹泡泡由网页长按控制，无法预知还会持续多久。";
        if (drive_id || water_hold.id || bubbles_hold.id)
            facts += "长按通道的剩余毫秒只供设备检查续租；松手、停止或续租中断才会结束，不能据此播报倒计时。";
        result += ",\"status_facts\":\"" + facts + "\"";
    }
    result += ",\"sequence_source\":\"" + std::string(plan_source) + "\",\"show_draft\":" + ShowDraftJson(draft, now) + "}";
    if (!web_session || (strcmp(operation, "get_status") && strcmp(operation, "drive_renew") && strcmp(operation, "water_renew") && strcmp(operation, "bubbles_renew")))
        ESP_LOGI("CT_AUDIO", "RESULT %s", result.c_str());
    return result;

}
std::string Reply(const char* operation, int ticket = 0, int duration = 0, const char* direction = nullptr, int water_duration = 0,
                  uint32_t web_session = 0, const WebCommand* command = nullptr, const ActionPlan* plan = nullptr, int speed_percent = 100, const ShowDraft::Command* edit = nullptr) {
    // Trusted board/web calls have no remote input token. MCP always passes one.
    return Reply(-1, operation, ticket, duration, direction, water_duration, web_session, command, plan, speed_percent, edit);
}
}

int CyberTrackVoiceTurn() {
    xSemaphoreTake(lock, portMAX_DELAY);
    const int turn = sessions.voice_turn;
    xSemaphoreGive(lock);
    return turn;
}
void CyberTrackVoiceInput(const char* text) {
    if (!text || !*text) return;
    bool content = false;
    for (const char* p = text; *p; ++p) if (*p != ' ' && *p != '\t' && *p != '\r' && *p != '\n') { content = true; break; }
    if (!content) return;
    const bool unquantified = draft_duration::NeedsClarification(text);
    xSemaphoreTake(lock, portMAX_DELAY);
    sessions.AdvanceVoiceTurn(true);
    sessions.voice_draft_unquantified = unquantified;
    xSemaphoreGive(lock);
}
void CyberTrackVoiceFailure(int turn) {
    xSemaphoreTake(lock, portMAX_DELAY);
    sessions.FailVoiceTurn(turn);
    xSemaphoreGive(lock);
}
void CyberTrackVoiceResult(int turn, const char* receipt) {
    auto* object = cJSON_Parse(receipt);
    const auto* result = cJSON_GetObjectItemCaseSensitive(object, "result");
    const bool success = cJSON_IsString(result) && (!strcmp(result->valuestring, "ok") || !strcmp(result->valuestring, "accepted") ||
        !strcmp(result->valuestring, "draft_saved") || !strcmp(result->valuestring, "draft_cancelled"));
    cJSON_Delete(object);
    if (!success) CyberTrackVoiceFailure(turn);
}

int CyberTrackActionClaim(int rpc_id, const char* operation, const char** error, int voice_turn) {
    xSemaphoreTake(lock, portMAX_DELAY);
    auto now = Now(); TickLocked(now);
    const auto target = (!strcmp(operation, "self.tank.adjust_speed") || !strcmp(operation, "self.tank.set_speed")) ? AudioActionGuard::SpeedMode :
        (!strcmp(operation, "self.tank.sequence") || !strcmp(operation, "self.tank.compose")) ? AudioActionGuard::PlanMode :
        !strcmp(operation, "self.tank.frenzy") ? AudioActionGuard::FrenzyMode :
        !strcmp(operation, "self.tank.move") ? AudioActionGuard::MoveOnly :
        !strcmp(operation, "self.tank.water") ? AudioActionGuard::WaterOnly :
        !strcmp(operation, "self.tank.bubbles") ? AudioActionGuard::BubblesOnly :
        !strcmp(operation, "self.tank.ignition") ? AudioActionGuard::IgnitionOnly :
        !strcmp(operation, "self.tank.move_and_water") ? AudioActionGuard::Both : static_cast<AudioActionGuard::Target>(0);
    int ticket = sessions.VoiceClaim(now, rpc_id, target, voice_turn);
    if (error) *error = ticket ? nullptr : (!sessions.wifi || !sessions.voice || sessions.shutdown || voice_turn < 0 || sessions.VoiceTurnReady(voice_turn))
        ? sessions.VoiceClaimError(target) : sessions.VoiceTurnError(voice_turn);
    if (!ticket && voice_turn >= 0) sessions.FailVoiceTurn(voice_turn);
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
    ESP_LOGI("CT_AUDIO", "WATER_PAD_READY pin=18 level=%d output_fault=%s sample=after_apply nominal_tick_ms=5",
             outputs.WaterPadLevel(), outputs.fault ? "true" : "false");
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
    InitializeCyberTrackProximityAudio();
    InitializeCyberTrackUltrasonic();
    InitializeCyberTrackWeb();
    auto& server = McpServer::GetInstance();
    server.AddTool("self.tank.get_status",
        "用status_facts中的设备事实简短回答所问部分。动作方向、速度和剩余时长都是回执采样瞬间的快照。只问方向或速度时不要附加倒计时。明确问还要多久时，先看所问通道是否由网页长按控制。若是，只说明何时结束取决于松手、停止或续租中断，不报秒数；只有定时通道才按对应通道remaining_ms简短说明“刚才查询时还剩约…秒”，不要当作播报时的当前值。查询时未运行就说明当时没有该动作计时。无法保证听完回复时仍在运行；不要轮询或延长动作。不要推测拒绝原因、停止原因、电量或自动恢复。查询CyberTrack状态或前方距离，参数为空。问为什么没动时只查询，不启动或重试。recent_command是本次开机最近一次动作请求回执，含operation/result/source/age_ms；查询不覆盖它，成功续租不覆盖它。它不是最后停机原因或物理反馈，较旧记录不能解释当前现象；valid=false或age_ms=null时不能推断。结合当前boot_held、fault、各通道remaining/cooldown和proximity说明已知状态；not_ready_or_busy不能凭空细分原因。accepted只表示逻辑接受，不能说实际已移动；未知就说明无法确认，不猜电池没电或线路故障。distance.valid=true且error=none时，distance.distance_mm为头部超声波测距毫米值，除以10换算厘米，回答大约多少厘米；valid=false、缺失或过期时只说暂时没有有效距离，不能说前方畅通，不能由云端轮询后自动行走、绕行或推算移动距离。有效距离不足50厘米时发出滴声，越近越密，不受自动避障开关或行走状态影响；至少50厘米或读数无效、过期时不响。proximity.auto_avoidance_enabled为网页自动避障开关，开机默认false、网页与语音共用；仅true时小于15厘米禁止前进，正在前进则停止并响三声；false时不因距离停前进。开关仅由网页设置，关闭不会恢复旧动作。proximity.forward_blocked为前进锁定，恢复至20厘米后允许新指令，不自动恢复。obstacle_blocked表示前进受阻，不重试。动作仍只有逻辑状态，没有轮速或水流反馈。sequence_active/sequence_step/sequence_steps/sequence_result为序列活动、步骤、总步数及状态；waiting是步骤间等待。frenzy_remaining_ms是模式剩余时间。网页与语音可同时用，各通道source表示来源，网页同路优先，全部停止始终有效。",
        PropertyList(), [](const PropertyList& p) -> ReturnValue { return Reply(p["_ct_turn"].value<int>(), "get_status"); });
    server.AddTool("self.tank.stop",
        "明确要求停止、停下、关闭正在运行的动作时立即调用，无需先查询。只是否定要做的动作（例如“不要前进”）且没有要求停止时不调用。立即停止两台电机、水枪、泡泡和点火及狂暴模式并取消全部排队动作，不关闭语音和屏幕。",
        PropertyList(), [](const PropertyList&) -> ReturnValue { return Reply("stop"); });
    server.AddTool("self.tank.water",
        "用户明确要求喷水时直接调用，无需按键授权。最短时长是1毫秒，不是1秒；明确说零点五秒或0.5秒时传500，0.001秒传1。未说时长才默认1000，不能擅自把明确的小数秒改成一秒，也不能声称最短一秒。duration_ms按用户时长换算为整数毫秒，范围1到30000；超过30秒只执行30秒并说明，明确要求喷水但未说时长时传1000。到期自动关闭，BOOT可提前停止。不得连续、延长或失败自动重试。可与行走同时执行、分别计时。同路正在执行时拒绝，结束后至少等待200毫秒，不排队补做。成功仅表示控制请求已接受。",
        PropertyList({Property("duration_ms", kPropertyTypeInteger, 1, 30000)}),
        [](const PropertyList& p) -> ReturnValue {
            return Reply(p["_ct_turn"].value<int>(), "water", p["_ct_ticket"].value<int>(), p["duration_ms"].value<int>());
        });
    server.AddTool("self.tank.bubbles",
        "仅在用户明确要求吹泡泡时调用。用户指定超过三十秒时，必须在本次调用前将duration_ms设为30000，例如六十秒、一分钟或更长都只传30000；绝不能把60000等越界值发给设备。说明上限不能替代传入合法参数。duration_ms是1到30000的整数毫秒；未说时长传1000，超过三十秒只请求30000并说明，不分段。与行走、喷水和点火独立并行；同路不续时、不排队，停止后间隔200毫秒。不自动重试。BOOT和停止工具全停。接受回执不代表实际出泡。",
        PropertyList({Property("duration_ms", kPropertyTypeInteger, 1, 30000)}),
        [](const PropertyList& p) -> ReturnValue {
            return Reply(p["_ct_turn"].value<int>(), "bubbles", p["_ct_ticket"].value<int>(), p["duration_ms"].value<int>());
        });
    server.AddTool("self.tank.ignition",
        "仅在用户明确要求点火或火花效果时调用，不从喷水、泡泡或行走指令推断点火。一个通道同时控制两只模块。duration_ms是1到5000的整数毫秒；未说时长传1000，超过五秒只请求5000并说明，不分段、不循环、不续时、不自动重试。与其他动作独立并行，停止后至少间隔本次实际通电时长（提前停止也按实际时长计算）且必须新指令。BOOT和停止工具全停。接受回执仅为逻辑状态，不代表实际火花或硬件验收。",
        PropertyList({Property("duration_ms", kPropertyTypeInteger, 1, 5000)}),
        [](const PropertyList& p) -> ReturnValue {
            return Reply(p["_ct_turn"].value<int>(), "ignition", p["_ct_ticket"].value<int>(), p["duration_ms"].value<int>());
        });
    server.AddTool("self.tank.frenzy",
        "仅在用户明确要求开启狂暴模式时调用。duration_ms为1到30000的整数毫秒；未说时长默认5000，超过三十秒只请求30000并说明，不分段。模式持续左转、喷水和吹泡泡，点火每次最多一秒、停止后至少间隔实际通电时长；到时全停。四路均就绪才整体启动，运行中不续时、不自动重试或补做。停止工具、BOOT、语音连接关闭或Wi-Fi断开取消。否定句、状态询问及含糊效果请求不启动。按frenzy_last_duration_ms确认时长，不代表实际动作反馈。",
        PropertyList({Property("duration_ms", kPropertyTypeInteger, 1, 30000)}),
        [](const PropertyList& p) -> ReturnValue {
            return Reply(p["_ct_turn"].value<int>(), "frenzy", p["_ct_ticket"].value<int>(), p["duration_ms"].value<int>());
        });
    server.AddTool("self.tank.move",
        "仅在明确要求行走或转向时调用。direction只能为forward前进、backward后退、left向左原地转、right向右原地转。duration_ms按指定时长换算为整数毫秒，范围1到2147483647（协议整数范围），没有三秒业务上限；未说时长时，100%速度（含省略速度）的left/right默认880，其他情况1000；明确指定时长优先。全速前进/后退/左转/右转均传speed_percent=100及对应direction。不支持角度或距离精确控制。speed_percent为可选整数60到100，默认100；速度60表示60%，百分比控制PWM而非实测轮速。可与喷水同时执行、分别计时；同路运行中不续时或换向，行走结束后至少等待200毫秒。不得续时、自动重试或排队补做。BOOT或停止工具同时停止所有动作。回执不是实际移动反馈。",
        PropertyList({Property("direction", kPropertyTypeString), Property("duration_ms", kPropertyTypeInteger, 1, 2147483647), Property("speed_percent", kPropertyTypeInteger, 100, 60, 100)}),
        [](const PropertyList& p) -> ReturnValue {
            return Reply(p["_ct_turn"].value<int>(), "move", p["_ct_ticket"].value<int>(), p["duration_ms"].value<int>(),
                         p["direction"].value<std::string>().c_str(), 0, 0, nullptr, nullptr, p["speed_percent"].value<int>());
        });
    server.AddTool("self.tank.move_and_water",
        "用户明确要求边走边喷或同时转向喷水时调用，一次同时启动两路。direction为forward/backward/left/right，move_duration_ms为1到2147483647，water_duration_ms为1到30000。可选speed_percent为60到100整数，默认100，只控制行走PWM，速度60指60%。只给一个时长且要求同时或在行走时喷水，两路共享该时长；都未说时，100%速度（含省略速度）的left/right行走默认880，其他行走及喷水默认1000。喷水仍最多30000，不分段；行走按指定时长执行。两路必须均空闲且冷却结束，否则整项拒绝不部分启动。分别计时，到期只停止对应动作，BOOT或停止关闭两路。不保证精确距离、角度或实际动作反馈。",
        PropertyList({Property("direction", kPropertyTypeString), Property("move_duration_ms", kPropertyTypeInteger, 1, 2147483647),
                      Property("water_duration_ms", kPropertyTypeInteger, 1, 30000), Property("speed_percent", kPropertyTypeInteger, 100, 60, 100)}),
        [](const PropertyList& p) -> ReturnValue {
            return Reply(p["_ct_turn"].value<int>(), "move_and_water", p["_ct_ticket"].value<int>(), p["move_duration_ms"].value<int>(),
                         p["direction"].value<std::string>().c_str(), p["water_duration_ms"].value<int>(), 0, nullptr, nullptr, p["speed_percent"].value<int>());
        });
    server.AddTool("self.tank.set_speed",
        "单说“全速”“最快”“最大速度”“调到全速”，直接调用本工具一次，speed_percent=100。不要先查询状态、追问或播报计划。由本次回执判断，接受后静默。拒绝时只解释错误明确给出的事实：speed_rejected_not_moving表示请求时未移动，speed_rejected_wifi_offline表示设备Wi-Fi离线，speed_rejected_voice_offline表示语音控制链路离线，speed_rejected_shutdown表示正在关机。离线不能解释为没有移动；通用错误只说这次没确认成功。拒绝后不建议试动、不启动、不重试。带方向的“全速前进”等另按行走规则处理。用户说减速到60%、加速到80%、速度调到70、调到全速时调用，唯一参数speed_percent为60到100整数，全速=100。有明确目标数值时用本工具，不用adjust_speed多次拼接，不调用move重新启动。不改变方向、截止时间、长按租期或其他动作，序列仅改当前步骤；网页移动同步滑块。停止或步骤等待时拒绝，不启动、不重试。accepted后静默；低于60或高于100的请求先说明范围并让用户选择，不擅自执行其他速度。",
        PropertyList({Property("speed_percent", kPropertyTypeInteger, 60, 100)}),
        [](const PropertyList& p) -> ReturnValue {
            return Reply(p["_ct_turn"].value<int>(), "set_speed", p["_ct_ticket"].value<int>(), p["speed_percent"].value<int>());
        });
    server.AddTool("self.tank.adjust_speed",
        "仅在用户明确要求正在移动的机器人加速/加快速度/快一点或减速/减慢速度/慢一点时调用。delta_percent只能为10或-10，分别增加或减少10个百分点，固件将结果限制在60到100。每句一次，不循环调用。只调整当前行走或转向（含网页移动、序列当前步骤、狂暴模式），不启动移动、不改方向、不续时，也不改序列后续步骤；停止或等待步骤时拒绝，不能改用move启动或重试。accepted后静默，失败简短说明；move_speed_percent为设置值，不是实际轮速。",
        PropertyList({Property("delta_percent", kPropertyTypeInteger, -10, 10)}),
        [](const PropertyList& p) -> ReturnValue {
            return Reply(p["_ct_turn"].value<int>(), "adjust_speed", p["_ct_ticket"].value<int>(), p["delta_percent"].value<int>());
        });
    server.AddTool("self.tank.compose",
        "查询get_status只读取现状，绝不创建或保存草稿。用户明确要求新建或修改表演时，查完版本必须实际调用本工具，拿到本次result=draft_saved和新revision后才能说已保存；没有保存回执时说明尚未保存，不能凭计划或旧草稿宣称完成。取消也必须先实际查询，再调用cancel并收到draft_cancelled才说已取消。不要播报推理或操作计划。仅当用户明确编排、预览或修改泡泡表演草稿时使用；不执行动作。每次改稿前必须在本次会话调用get_status读取show_draft最新revision与steps，即使用户或上下文已经给出版本也要查。只允许行走和吹泡泡。喷水、点火、放电、护盾等不支持的效果只说明限制，不调用本工具，不提交空数组。用户说短一点等相对时长且没有明确新时长时，只问要改成几秒。参数edit为replace/replace_step/remove_step/cancel，revision为当前草稿版本，无草稿填0；step为从1开始的步骤索引，整单替换或取消填0；“同时／一边…一边”把行走和泡泡写进同一个步骤，各填各的时长；“先…再／然后”写为先后两步。回顾用户要求的先后关系再保存。steps_json沿用sequence步骤格式，首版仅行走与泡泡，water_ms/ignition_ms均0。replace传完整1到16步，replace_step只传单步数组，其余步骤由设备保留；remove_step/cancel传空字符串。draft_saved表示保存未执行，简短说明改动并请家长在网页预览后点开始；draft_changed先说明版本已变，不自动重试。不能用sequence/move等工具替代确认；没有语音确认执行工具。",
        PropertyList({Property("edit", kPropertyTypeString), Property("revision", kPropertyTypeInteger, 0, INT_MAX),
                      Property("step", kPropertyTypeInteger, 0, 16), Property("steps_json", kPropertyTypeString)}),
        [](const PropertyList& p) -> ReturnValue {
            cJSON* root = cJSON_CreateObject();
            cJSON_AddStringToObject(root, "edit", p["edit"].value<std::string>().c_str());
            cJSON_AddNumberToObject(root, "revision", p["revision"].value<int>());
            cJSON_AddNumberToObject(root, "step", p["step"].value<int>());
            cJSON_AddStringToObject(root, "steps_json", p["steps_json"].value<std::string>().c_str());
            ShowDraft::Command edit;
            const bool valid = ParseShowEdit(root, edit); cJSON_Delete(root);
            if (!valid) return std::string("{\"result\":\"invalid_plan\"}");
            return Reply(p["_ct_turn"].value<int>(), "show_edit", p["_ct_ticket"].value<int>(), 0, nullptr, 0, 0, nullptr, nullptr, 100, &edit);
        });
    server.AddTool("self.tank.sequence",
        "直接动作指令使用本工具；明确编排、预览或修改草稿用compose，不得用本工具代替草稿确认。明确请求多个先后步骤或多通道同时执行时，一次提交整个序列，不能拆成连续单项调用。steps_json是JSON数组的字符串，1到16步，每步必须包含direction、move_ms、water_ms、bubbles_ms、ignition_ms五字段，可选speed_percent为60到100整数、默认100；每步独立指定行走PWM，全句指定速度时应用到各行走步骤。direction为forward/backward/left/right；不行走用none且move_ms=0。各时长为整数毫秒，0表示不用该通道，每步至少一通道；move_ms最多2147483647，喷水/泡泡最多30000，点火最多5000。一步内各通道同时启动、独立停止；全部结束并满足冷却后下一步，无指定时长时，本步100%速度（含省略速度）的left/right行走默认880，其他动作1000；同时或在某动作时做另一动作且只给一个时长则共享，分别遵守效果上限。不用额外步骤绕过效果上限。整单验证且四路均空闲才启动，运行中保留四路；失败不重试，停止/BOOT/断线/故障或网页抢占取消整单，不能补做。accepted仅表示序列已开始，sequence_result查询完成或取消。",
        PropertyList({Property("steps_json", kPropertyTypeString)}),
        [](const PropertyList& p) -> ReturnValue {
            ActionPlan plan;
            if (!ParseActionPlan(p["steps_json"].value<std::string>(), plan)) return std::string("{\"result\":\"invalid_plan\"}");
            return Reply(p["_ct_turn"].value<int>(), "sequence", p["_ct_ticket"].value<int>(), 0, nullptr, 0, 0, nullptr, &plan);
        });
    ESP_LOGI("CT_AUDIO", "READY tools=status,stop,water,bubbles,ignition,frenzy,move,move_and_water,sequence,compose,adjust_speed,set_speed concurrent=true motor_A=8/9/10 motor_B=11/12/13 GPIO18=LOW GPIO17=LOW GPIO21=LOW BOOT=stop_all move_max_ms=2147483647 water_max_ms=30000 bubbles_max_ms=30000 ignition_max_ms=5000");
}
