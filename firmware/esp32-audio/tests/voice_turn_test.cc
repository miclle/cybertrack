#include "control_sessions.h"
#include <cassert>
#include <cstring>

static void local_stop_requires_fresh_voice_input() {
    ControlSessions s;
    s.WifiLink(0, true);
    s.VoiceLink(0, true);
    s.Tick(0, false);
    s.AdvanceVoiceTurn(true);
    const int before_stop = s.voice_turn;
    assert(s.VoiceTurnReady(before_stop));
    s.Tick(10, true);
    assert(!s.VoiceTurnReady(before_stop));
    s.AdvanceVoiceTurn(true); // Another transcript arrives while BOOT is held.
    const int while_held = s.voice_turn;
    s.Tick(20, false);
    s.Tick(2000, false);
    for (int turn : {before_stop, while_held}) {
        assert(!s.VoiceClaim(2000, 1, AudioActionGuard::MoveOnly, turn));
    }
    assert(!s.guard.Starts());
    s.AdvanceVoiceTurn(true);
    int ticket = s.VoiceClaim(2000, 2, AudioActionGuard::MoveOnly, s.voice_turn);
    assert(ticket && !std::strcmp(s.guard.Move(2000, ticket, 500, "forward"), "accepted"));
}

int main() {
    local_stop_requires_fresh_voice_input();
    ControlSessions s;
    s.WifiLink(0, true); s.VoiceLink(0, true); s.Tick(0, false);
    assert(!s.VoiceTurnReady(s.voice_turn));
    s.AdvanceVoiceTurn(true);
    const int first = s.voice_turn;
    int pending = s.VoiceClaim(0, 1, AudioActionGuard::WaterOnly, first);
    assert(pending);
    s.FailVoiceTurn(first);
    assert(!s.VoiceTurnReady(first));
    assert(std::strcmp(s.guard.Water(0, pending, 1000), "accepted"));
    assert(!s.VoiceClaim(0, 2, AudioActionGuard::MoveOnly, first));
    // Stopping never reopens failed input.
    s.Stop(0);
    assert(!s.VoiceTurnReady(first) && s.guard.Starts() == 0);

    s.AdvanceVoiceTurn(true);
    int second = s.voice_turn;
    s.FailVoiceTurn(first);
    assert(s.VoiceTurnReady(second));
    assert(!s.VoiceClaim(300, 1, AudioActionGuard::WaterOnly, second)); // RPC replay survives input changes.
    pending = s.VoiceClaim(300, 3, AudioActionGuard::WaterOnly, second);
    assert(pending);
    assert(!std::strcmp(s.guard.Water(300, pending, 1000), "accepted"));
    auto deadline = s.guard.spray.ends_at;
    s.FailVoiceTurn(second);
    assert(s.guard.Watering() && s.guard.spray.ends_at == deadline);
    s.AdvanceVoiceTurn(true);
    assert(s.guard.Watering() && s.guard.spray.ends_at == deadline);
    const int third = s.voice_turn;
    pending = s.VoiceClaim(300, 4, AudioActionGuard::MoveOnly, third);
    assert(pending); // Other lanes retain normal concurrency on a fresh input.
    s.AdvanceVoiceTurn(true);
    assert(std::strcmp(s.guard.Move(300, pending, 1000, "forward"), "accepted"));
    s.FailVoiceTurn(third);
    assert(s.VoiceTurnReady(s.voice_turn));

    int stale = s.voice_turn;
    s.VoiceLink(400, false); s.VoiceLink(400, true);
    assert(!s.VoiceTurnReady(stale) && !s.VoiceTurnReady(s.voice_turn));
    s.AdvanceVoiceTurn(true);
    assert(s.VoiceTurnReady(s.voice_turn));
    s.WifiLink(500, false);
    assert(!s.VoiceTurnReady(s.voice_turn));
    s.voice_turn = INT_MAX - 1;
    s.WifiLink(600, true); s.VoiceLink(600, true); s.AdvanceVoiceTurn(true);
    assert(s.voice_turn == INT_MAX && !s.VoiceTurnReady(INT_MAX));
}
