#include "voice_feedback.h"
#include <cassert>
#include <cstdio>
#include <string>

// Playback-only fixtures: accepted is software admission, never physical feedback.
int main() {
    VoiceFeedback feedback;
    auto request = [](int ms) { return cJSON_Parse(("{\"duration_ms\":"+std::to_string(ms)+"}").c_str()); };
    auto receipt = [](const char* tool, const char* field, int ms) {
        return std::string("{\"operation\":\"")+tool+"\",\"result\":\"accepted\",\"fault\":\"none\",\""+
            field+"\":"+std::to_string(ms)+",\"last_duration_ms\":30000}";
    };
    struct Alias { const char* phrase; const char* tool; const char* field; int default_ms; };
    const Alias aliases[] = {
        {"喷水","water","water_last_duration_ms",1000}, {"发射","water","water_last_duration_ms",1000},
        {"开枪","water","water_last_duration_ms",1000}, {"射击","water","water_last_duration_ms",1000},
        {"吹泡泡","bubbles","bubbles_last_duration_ms",1000}, {"开炮","bubbles","bubbles_last_duration_ms",1000},
        {"点火","ignition","ignition_last_duration_ms",1000}, {"放电","ignition","ignition_last_duration_ms",1000},
        {"闪电","ignition","ignition_last_duration_ms",1000}, {"护盾","ignition","ignition_last_duration_ms",1000},
        {"打火","ignition","ignition_last_duration_ms",1000}, {"电击","ignition","ignition_last_duration_ms",1000},
        {"饭店","ignition","ignition_last_duration_ms",1000}, {"狂暴模式","frenzy","frenzy_last_duration_ms",5000}
    };
    int positive=0, preserved=0;
    for (const auto& alias : aliases) {
        auto name=std::string("self.tank.")+alias.tool;
        for (const auto& prefix : {std::string(""),std::string("开启")}) {
            for (const auto& suffix : {std::string(""),std::string("一下"),std::string("半秒"),std::string("两秒"),std::string("5000毫秒！")}) {
                int ms=suffix.empty() || suffix=="一下" ? alias.default_ms : suffix=="半秒" ? 500 : suffix=="两秒" ? 2000 : 5000;
                feedback.Input(prefix+alias.phrase+suffix);
                auto* args=request(ms);
                auto token=feedback.BeginCall(name,args);
                assert(token);
                feedback.Receipt(token,receipt(alias.tool,alias.field,ms).c_str());
                feedback.StartSpeech();
                assert(feedback.Muted());
                cJSON_Delete(args);
                ++positive;
            }
        }
        for (auto text : {std::string("不要")+alias.phrase, std::string(alias.phrase)+"？",std::string(alias.phrase)+"是什么意思",
                         std::string("昨天说过")+alias.phrase,std::string(alias.phrase)+"六十秒",std::string(alias.phrase)+"然后喷水两秒"}) {
            feedback.Input(text);
            auto* args=request(alias.default_ms);
            assert(!feedback.BeginCall(name,args));
            feedback.StartSpeech();
            assert(!feedback.Muted());
            cJSON_Delete(args);
            ++preserved;
        }
    }
    for (const char* text : {"饭店吃饭","去饭店","附近饭店","还在饭店吗","开启饭店吃饭","放电八秒","护盾三十秒"}) {
        feedback.Input(text);
        auto* args=request(1000);
        assert(!feedback.BeginCall("self.tank.ignition",args));
        feedback.StartSpeech();
        assert(!feedback.Muted());
        cJSON_Delete(args);
        ++preserved;
    }
    for (const char* raw : {R"({"duration_ms":2000,"extra":1})",R"({"duration_ms":"2000"})",R"({"duration_ms":true})",
                            R"({"duration_ms":1000})",R"({"duration_ms":2000.5})"}) {
        feedback.Input("放电两秒");
        auto* args=cJSON_Parse(raw);
        assert(!feedback.BeginCall("self.tank.ignition",args));
        feedback.StartSpeech();
        assert(!feedback.Muted());
        cJSON_Delete(args);
        ++preserved;
    }
    auto* args=request(2000);
    for (const char* raw : {
        R"({"operation":"ignition","result":"rejected","fault":"none","ignition_last_duration_ms":2000})",
        R"({"operation":"ignition","result":"accepted","ignition_last_duration_ms":2000})",
        R"({"operation":"ignition","result":"accepted","fault":"output_fault","ignition_last_duration_ms":2000})",
        R"({"operation":"water","result":"accepted","fault":"none","ignition_last_duration_ms":2000})",
        R"({"operation":"ignition","result":"accepted","fault":"none","last_duration_ms":2000})",
        R"({"operation":"ignition","result":"accepted","fault":"none","water_last_duration_ms":2000})",
        R"({"operation":"ignition","result":"accepted","fault":"none","last_duration_ms":2000,"ignition_last_duration_ms":1000})"
    }) {
        feedback.Input("放电两秒");
        auto token=feedback.BeginCall("self.tank.ignition",args);
        assert(token);
        feedback.Receipt(token,raw);
        feedback.StartSpeech();
        assert(!feedback.Muted());
        ++preserved;
    }
    for (int timing=0;timing<3;++timing) {
        feedback.Input("放电两秒");
        auto token=feedback.BeginCall("self.tank.ignition",args);
        if (timing==0) feedback.Input("现在什么状态？");
        if (timing==1) feedback.StartSpeech();
        if (timing==2) feedback.BeginCall("self.tank.get_status",nullptr);
        feedback.Receipt(token,receipt("ignition","ignition_last_duration_ms",2000).c_str());
        feedback.StartSpeech();
        assert(!feedback.Muted());
        ++preserved;
    }
    cJSON_Delete(args);
    for (const char* phrase : {"停止点火","停止放电","停止射击","关闭护盾","停止饭店"}) {
        feedback.Input(phrase);
        auto token=feedback.BeginCall("self.tank.stop",nullptr);
        assert(token);
        feedback.Receipt(token,R"({"operation":"stop","result":"ok","fault":"stopped"})");
        feedback.StartSpeech();
        assert(feedback.Muted());
        ++positive;
    }
    printf("effect alias playback: %d positive, %d explanations preserved\n",positive,preserved);
}
