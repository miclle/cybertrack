#include "receipt_host.h"

std::string field(const cJSON* object, const char* name) {
    auto value = cJSON_GetObjectItemCaseSensitive(object, name);
    assert(cJSON_IsString(value)); return value->valuestring;
}
int main() {
    sessions.WifiLink(clock_ms, true);
    const auto session = sessions.Acquire(clock_ms);
    auto initial = cJSON_Parse(Reply("get_status", 0, 0, nullptr, 0, session).c_str());
    assert(!cJSON_GetObjectItemCaseSensitive(initial,"show_draft"));
    assert(!cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(initial,"capabilities"),"show_draft"));
    assert(initial && field(initial, "status_facts").find("没有最近") != std::string::npos);
    assert(StatusFacts("output_fault", true, false, false, "").find("旧动作不会恢复") != std::string::npos);
    assert(StatusFacts("none", false, true, false, "accepted").find("步骤间等待") != std::string::npos);
    assert(StatusFacts("none", false, true, true, "").find("步骤间等待") == std::string::npos);
    assert(!cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(initial,"recent_command"),"valid")));
    assert(!cJSON_GetObjectItemCaseSensitive(initial,"fault_recovery"));
    cJSON_Delete(initial);
    outputs.fault = true;
    auto* fault_status = cJSON_Parse(Reply("get_status").c_str());
    assert(field(fault_status,"fault_recovery").find("不要重启") != std::string::npos);
    cJSON_Delete(fault_status);
    outputs.fault = false;
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
    clock_ms=1500;
    Reply("get_status",0,0,nullptr,0,session);
    clock_ms += 300;
    assert(sessions.Heartbeat(clock_ms, session));
    assert(std::string(sessions.DriveStart(clock_ms, session, 5, sessions.window, "forward", 0)) == "accepted");
    assert(sessions.Heartbeat(clock_ms, session));
    assert(std::string(sessions.EffectStart(clock_ms, session, 6, sessions.window, AudioActionGuard::WaterOnly)) == "accepted");
    assert(sessions.Heartbeat(clock_ms, session));
    assert(std::string(sessions.EffectStart(clock_ms, session, 7, sessions.window, AudioActionGuard::BubblesOnly)) == "accepted");
    clock_ms += 200;
    auto* held_status = cJSON_Parse(Reply("get_status").c_str());
    const auto held_facts = field(held_status, "status_facts");
    for (auto channel : {"行走由网页长按", "喷水由网页长按", "吹泡泡由网页长按"})
        assert(held_facts.find(channel) != std::string::npos);
    assert(cJSON_GetObjectItemCaseSensitive(held_status, "move_remaining_ms")->valueint == 400);
    cJSON_Delete(held_status);
    clock_ms += 400;
    auto* expired_status = cJSON_Parse(Reply("get_status").c_str());
    assert(field(expired_status, "status_facts").find("长按") == std::string::npos);
    cJSON_Delete(expired_status);
    std::puts("PASS: actual Reply JSON acceptance/rejection/query/stop persistence with real guards and no hardware");
}
