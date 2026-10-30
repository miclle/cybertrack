// Compile the actual Reply function with real guards and a controlled clock/IO.
#include "control_sessions.h"
#include "recent_command.h"
#include "web_request.h"
#include "cJSON.h"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <string>
ControlSessions sessions;
AudioActionGuard& guard = sessions.guard;
RecentCommand recent_command;
struct { bool fault = false; } outputs;
uint64_t clock_ms = 1000;
uint64_t Now() { return clock_ms; }
std::string Decimal(uint64_t value) { return std::to_string(value); }
unsigned sequence = 0, dropped_events = 0;
std::string device_id(32, 'd'), boot_id(32, 'b');
int lock;
constexpr int portMAX_DELAY = 0;
void xSemaphoreTake(int, int) {}
void xSemaphoreGive(int) {}
void TickLocked(uint64_t now) { sessions.Tick(now, false); }
void ApplyLocked(uint64_t) {} // No device output is linked in this host harness.
int CyberTrackDistanceSnapshot() { return 0; }
namespace ultrasonic { std::string Json(int, uint64_t) { return "{\"valid\":false,\"error\":\"no_echo\"}"; } }
#define ESP_LOGI(...) ((void)0)
#include "receipt_reply.inc"

std::string field(const cJSON* object, const char* name) {
    auto value = cJSON_GetObjectItemCaseSensitive(object, name);
    assert(cJSON_IsString(value)); return value->valuestring;
}
int main() {
    sessions.WifiLink(clock_ms, true);
    const auto session = sessions.Acquire(clock_ms);
    auto initial = cJSON_Parse(Reply("get_status", 0, 0, nullptr, 0, session).c_str());
    assert(initial);
    assert(!cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(initial,"recent_command"),"valid")));
    cJSON_Delete(initial);
    WebCommand command;
    command.operation="move"; command.target=AudioActionGuard::MoveOnly;
    command.sequence=1; command.window=sessions.window; command.direction="forward"; command.move_ms=1000;
    auto result = cJSON_Parse(Reply("move",0,1000,"forward",0,session,&command).c_str());
    assert(result && field(result,"result")=="accepted");
    cJSON_Delete(result);
    clock_ms += 100;
    auto status = cJSON_Parse(Reply("get_status",0,0,nullptr,0,session).c_str());
    assert(status && field(status,"result")=="ok");
    auto receipt = cJSON_GetObjectItemCaseSensitive(status,"recent_command");
    assert(field(receipt,"operation")=="move" && field(receipt,"result")=="accepted" && field(receipt,"source")=="web");
    assert(cJSON_GetObjectItemCaseSensitive(receipt,"age_ms")->valueint==100);
    cJSON_Delete(status);
    command.sequence=2; command.window=0;
    auto failed = cJSON_Parse(Reply("move",0,1000,"forward",0,session,&command).c_str());
    assert(failed && field(failed,"result")=="stale_request"); cJSON_Delete(failed);
    status = cJSON_Parse(Reply("get_status",0,0,nullptr,0,session).c_str());
    receipt = cJSON_GetObjectItemCaseSensitive(status,"recent_command");
    assert(field(receipt,"result")=="stale_request");
    assert(guard.Moving()); // Explaining/querying did not cancel or restart prior motion.
    cJSON_Delete(status);
    auto stopped = cJSON_Parse(Reply("stop").c_str());
    assert(stopped && !guard.Moving());
    receipt = cJSON_GetObjectItemCaseSensitive(stopped,"recent_command");
    assert(field(receipt,"operation")=="stop" && field(receipt,"source")=="voice");
    cJSON_Delete(stopped);
    std::puts("PASS: actual Reply JSON acceptance/rejection/query/stop persistence with real guards and no hardware");
}
