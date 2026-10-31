#include "receipt_host.h"
#include "voice_feedback.h"

int main() {
    // All integral millisecond values in the effect protocol retain their value.
    for (int ms=1;ms<=30000;++ms)
        assert(SpokenEffectMs(std::to_string(ms)+"毫秒")==ms);
    const char* chinese[]={"一","二","三","四","五","六","七","八","九","十","十一","十二",
        "十三","十四","十五","十六","十七","十八","十九","二十","二十一","二十二","二十三",
        "二十四","二十五","二十六","二十七","二十八","二十九","三十"};
    for (int i=1;i<=30;++i) {
        assert(SpokenEffectMs(std::to_string(i)+"秒")==i*1000);
        assert(SpokenEffectMs(std::string(chinese[i-1])+"秒")==i*1000);
    }
    for (const auto& test : {std::pair<const char*,int>{"0.001秒",1},{"29.999秒",29999},
                            {"零点五秒",500},{"两点五秒",2500},{"半秒",500},{"一秒半",1500}}) {
        assert(SpokenEffectMs(test.first)==test.second);
    }
    for (const char* text : {"零秒","0毫秒","30001毫秒","六十秒","两分钟","-2秒","2.0001秒",
                            "1e1秒","一半秒","十零秒","两秒？","两秒然后喷水三秒"})
        assert(SpokenEffectMs(text)==0);

    sessions.WifiLink(clock_ms,true);
    sessions.VoiceLink(clock_ms,true);
    sessions.Tick(clock_ms,false);
    VoiceFeedback feedback;
    feedback.Input("吹泡泡两点五秒。");
    auto* args=cJSON_Parse(R"({"duration_ms":2500})");
    const auto call=feedback.BeginCall("self.tank.bubbles",args);
    assert(call);
    auto ticket=sessions.VoiceClaim(clock_ms,1,AudioActionGuard::BubblesOnly);
    assert(ticket);
    const auto receipt=Reply("bubbles",ticket,2500);
    feedback.Receipt(call,receipt.c_str());
    feedback.StartSpeech();
    assert(feedback.Muted());
    assert(guard.Starts()==1 && guard.Bubbling());
    cJSON_Delete(args);

    feedback.Input("喷水半秒");
    args=cJSON_Parse(R"({"duration_ms":500})");
    auto water_call=feedback.BeginCall("self.tank.water",args);
    ticket=sessions.VoiceClaim(clock_ms,2,AudioActionGuard::WaterOnly);
    assert(water_call && ticket);
    feedback.Receipt(water_call,Reply("water",ticket,500).c_str());
    feedback.StartSpeech();
    assert(feedback.Muted() && guard.Starts()==2 && guard.Watering() && guard.Bubbling());
    cJSON_Delete(args);

    feedback.Input("吹泡泡两秒");
    args=cJSON_Parse(R"({"duration_ms":2000})");
    auto old=feedback.BeginCall("self.tank.bubbles",args);
    feedback.Input("吹泡泡三秒");
    feedback.Receipt(old,R"({"operation":"bubbles","result":"accepted","fault":"none","last_duration_ms":2000})");
    feedback.StartSpeech();
    assert(!feedback.Muted());
    feedback.Input("吹泡泡两秒");
    old=feedback.BeginCall("self.tank.bubbles",args);
    feedback.StartSpeech();
    feedback.Receipt(old,R"({"operation":"bubbles","result":"accepted","fault":"none","last_duration_ms":2000})");
    assert(!feedback.Muted());
    cJSON_Delete(args);

    // These inputs must preserve explanations and have no action callback.
    for (const char* text : {"吹泡泡六十秒","不要吹泡泡两秒","吹泡泡两秒？",
                            "吹泡泡两秒是什么意思","吹泡泡两秒，然后喷水两秒"}) {
        feedback.Input(text);
        auto* duration=cJSON_Parse(R"({"duration_ms":2000})");
        assert(!feedback.BeginCall("self.tank.bubbles",duration));
        feedback.StartSpeech();
        assert(!feedback.Muted());
        cJSON_Delete(duration);
    }
    for (const char* reply : {R"({"operation":"bubbles","result":"rejected","fault":"none","last_duration_ms":2000})",
                             R"({"operation":"bubbles","result":"accepted","fault":"none"})",
                             R"({"operation":"bubbles","result":"accepted","fault":"none","last_duration_ms":1000})"}) {
        feedback.Input("吹泡泡两秒");
        auto* duration=cJSON_Parse(R"({"duration_ms":2000})");
        auto token=feedback.BeginCall("self.tank.bubbles",duration);
        feedback.Receipt(token,reply);
        feedback.StartSpeech();
        assert(!feedback.Muted());
        cJSON_Delete(duration);
    }
}
