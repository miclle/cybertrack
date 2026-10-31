#include "voice_feedback.h"
#include <cassert>

int main() {
    VoiceFeedback feedback;
    auto move = cJSON_Parse(R"({"direction":"forward","duration_ms":1000})");
    const char* accepted = R"({"operation":"move","result":"accepted","fault":"none"})";
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
    for (const char* phrase : {"停止", "停止行走", "停止喷水", "停止泡泡", "停止狂暴模式",
                               "取消序列", "所有动作都停下来", "取消正在执行的表演！"}) {
        feedback.Input(phrase);
        auto stop = feedback.BeginCall("self.tank.stop", nullptr);
        feedback.Receipt(stop, R"({"operation":"stop","result":"ok","fault":"stopped"})");
        feedback.StartSpeech();
        assert(feedback.Muted());
    }
    for (const char* phrase : {"不要取消序列", "取消这个还没开始的草稿", "停止了吗？"}) {
        feedback.Input(phrase);
        assert(!feedback.BeginCall("self.tank.stop", nullptr));
    }
    for (const char* receipt : {R"({"operation":"move","result":"accepted","fault":"none"})",
                                R"({"operation":"stop","result":"ok","fault":"output_fault"})",
                                R"({"operation":"stop","result":"ok"})"}) {
        feedback.Input("取消序列");
        auto call = feedback.BeginCall("self.tank.stop", nullptr);
        feedback.Receipt(call, receipt);
        feedback.StartSpeech();
        assert(!feedback.Muted());
    }
    auto top_speed = cJSON_Parse(R"({"speed_percent":100})");
    const char* full_speed = R"({"operation":"set_speed","result":"accepted","fault":"none","move_speed_percent":100})";
    for (const char* phrase : {"全速。","最快","最大速度","调到全速"}) {
        feedback.Input(phrase);
        auto call = feedback.BeginCall("self.tank.set_speed", top_speed);
        assert(call);
        feedback.Receipt(call,full_speed);
        feedback.StartSpeech();
        assert(feedback.Muted());
    }
    for (const char* phrase : {"不要全速","全速前进","全速？"}) {
        feedback.Input(phrase);
        assert(!feedback.BeginCall("self.tank.set_speed", top_speed));
    }
    for (const char* raw : {R"({"speed_percent":90})", R"({"speed_percent":"100"})",
                            R"({"speed_percent":100,"extra":1})"}) {
        auto* args = cJSON_Parse(raw);
        feedback.Input("全速");
        assert(!feedback.BeginCall("self.tank.set_speed",args));
        cJSON_Delete(args);
    }
    for (const char* raw : {R"({"operation":"set_speed","result":"not_ready_or_busy","fault":"none"})",
                            R"({"operation":"set_speed","result":"accepted","fault":"none","move_speed_percent":70})",
                            R"({"operation":"set_speed","result":"accepted","fault":"none"})"}) {
        feedback.Input("全速");
        auto call = feedback.BeginCall("self.tank.set_speed", top_speed);
        feedback.Receipt(call,raw);
        feedback.StartSpeech();
        assert(!feedback.Muted());
    }
    cJSON_Delete(top_speed);
    cJSON_Delete(move);
}
