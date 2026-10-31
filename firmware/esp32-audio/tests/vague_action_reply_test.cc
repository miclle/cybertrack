#include "receipt_host.h"
#include <iostream>

int main() {
    sessions.WifiLink(clock_ms, true);
    sessions.VoiceLink(clock_ms, true);
    sessions.Tick(clock_ms, false);
    sessions.AdvanceVoiceTurn(true);
    sessions.voice_action_unspecified = true;
    int ticket = sessions.VoiceClaim(clock_ms, 1, AudioActionGuard::BubblesOnly, sessions.voice_turn);
    auto* denied = cJSON_Parse(Reply(sessions.voice_turn,"bubbles",ticket,1000).c_str());
    assert(denied && !std::strcmp(cJSON_GetObjectItemCaseSensitive(denied,"result")->valuestring,"action_unspecified"));
    assert(cJSON_IsString(cJSON_GetObjectItemCaseSensitive(denied,"clarification_facts")));
    assert(guard.Starts()==0 && sessions.voice_turn_failed);
    cJSON_Delete(denied);

    const auto owner = sessions.Acquire(clock_ms);
    assert(owner && sessions.Heartbeat(clock_ms, owner));
    WebCommand command;
    command.operation="bubbles"; command.target=AudioActionGuard::BubblesOnly;
    command.sequence=1; command.window=sessions.window; command.bubbles_ms=1000;
    auto* web = cJSON_Parse(Reply("bubbles",0,0,nullptr,0,owner,&command).c_str());
    assert(web && !std::strcmp(cJSON_GetObjectItemCaseSensitive(web,"result")->valuestring,"accepted"));
    assert(guard.Bubbling() && guard.Starts()==1);
    cJSON_Delete(web);
    Reply("stop");
    assert(!guard.Bubbling());
    sessions.AdvanceVoiceTurn(true);
    assert(!sessions.voice_action_unspecified && !sessions.voice_turn_failed);
    std::cout << "PASS: vague-input rejection preserves trusted web, stop and new input recovery\n";
}
