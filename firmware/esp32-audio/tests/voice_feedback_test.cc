#include "voice_feedback.h"
#include <cassert>

int main() {
    VoiceFeedback feedback;
    auto move = cJSON_Parse(R"({"direction":"forward","duration_ms":1000})");
    const char* accepted = R"({"operation":"move","result":"accepted"})";
    auto start = [&](const char* text) {
        feedback.Input(text);
        return feedback.BeginCall("self.tank.move", move);
    };
    for (const char* text : {"前进", "前进！"}) {
        auto call = start(text);
        assert(call);
        feedback.Receipt(call, accepted);
        feedback.StartSpeech();
        assert(feedback.Muted());
        feedback.Input("");
        assert(!feedback.Muted());
    }
    for (const char* text : {"前进？", "前进两秒", "前进然后告诉我距离", "别前进", "后退", "喷水六十秒"}) {
        assert(!start(text));
        feedback.StartSpeech();
        assert(!feedback.Muted());
    }
    auto stale = start("前进");
    feedback.Input("你现在在做什么");
    feedback.Receipt(stale, accepted);
    feedback.StartSpeech();
    assert(!feedback.Muted());
    auto failed = start("前进");
    feedback.Receipt(failed, R"({"operation":"move","result":"not_ready_or_busy"})");
    feedback.StartSpeech();
    assert(!feedback.Muted());
    auto early = start("前进");
    feedback.StartSpeech();
    feedback.Receipt(early, accepted);
    assert(!feedback.Muted());
    auto multi = start("前进");
    feedback.BeginCall("self.tank.get_status", nullptr);
    feedback.Receipt(multi, accepted);
    feedback.StartSpeech();
    assert(!feedback.Muted());
    feedback.Input("停止");
    auto stop = feedback.BeginCall("self.tank.stop", nullptr);
    feedback.Receipt(stop, R"({"operation":"stop","result":"ok"})");
    feedback.StartSpeech();
    assert(feedback.Muted());
    cJSON_Delete(move);
}
