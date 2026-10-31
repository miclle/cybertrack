#include "voice_feedback.h"
#include <cassert>
#include <string>

static cJSON* Args(const char* plan) {
    auto* object = cJSON_CreateObject();
    cJSON_AddStringToObject(object, "steps_json", plan);
    return object;
}
static bool Playback(const char* text, const char* tool, cJSON* args, const char* receipt, int order = 0) {
    VoiceFeedback feedback;
    feedback.Input(text);
    auto call = feedback.BeginCall(tool, args);
    if (order == 1) feedback.StartSpeech();
    if (order == 2) feedback.Input("现在状态怎么样？");
    if (order == 3) feedback.BeginCall("self.tank.get_status", nullptr);
    feedback.Receipt(call, receipt);
    feedback.StartSpeech();
    return feedback.Muted();
}
int main() {
    SpokenPlayback plan;
    assert(plan.Parse("前进五秒，同时喷水"));
    assert(std::string_view(plan.tool) == "move_and_water" && plan.steps[0].ms[0] == 5000 && plan.steps[0].ms[1] == 5000);
    assert(plan.Parse("同时喷水和左转两秒"));
    assert(plan.steps[0].ms[0] == 2000 && plan.steps[0].ms[1] == 2000);
    assert(plan.Parse("先前进，再左转"));
    assert(plan.count == 2 && plan.steps[0].ms[0] == 1000 && plan.steps[1].ms[0] == 880);
    assert(plan.Parse("前进五秒同时喷水两秒和吹泡泡"));
    assert(plan.steps[0].ms == (std::array<int, 3>{5000, 2000, 1000}));
    assert(plan.Parse("前进五秒同时喷水和吹泡泡"));
    assert(plan.steps[0].ms == (std::array<int, 3>{5000, 5000, 5000}));
    std::string many = "前进一秒";
    for (unsigned i = 1; i < 16; ++i) many += "然后左转";
    assert(plan.Parse(many) && plan.count == 16);
    assert(!plan.Parse(many + "然后喷水"));
    for (const char* phrase : {"不要前进五秒同时喷水", "前进五秒同时不要喷水", "前进五秒吗", "前进五秒后会怎样",
                              "前进五秒然后", "前进五秒，", "左转两秒和右转", "喷水和喷水", "前进31秒",
                              "喷水六十秒同时前进", "前进零秒", "前进-1秒", "编排前进一秒然后泡泡", "先前进然后点火"})
        assert(!plan.Parse(phrase));

    auto* both = cJSON_Parse(R"({"direction":"forward","move_duration_ms":5000,"water_duration_ms":5000})");
    const char* accepted = R"({"operation":"move_and_water","result":"accepted","fault":"none","move_direction":"forward","move_last_duration_ms":5000,"water_last_duration_ms":5000,"move_source":"voice","water_source":"voice","move_speed_percent":100})";
    assert(Playback("前进五秒，同时喷水。", "self.tank.move_and_water", both, accepted));
    for (int order : {1, 2, 3}) assert(!Playback("前进五秒，同时喷水", "self.tank.move_and_water", both, accepted, order));
    assert(!Playback("前进五秒，同时喷水", "self.tank.sequence", both, accepted));
    cJSON_SetNumberValue(cJSON_GetObjectItem(both, "water_duration_ms"), 1000);
    assert(!Playback("前进五秒，同时喷水", "self.tank.move_and_water", both, accepted));
    cJSON_SetNumberValue(cJSON_GetObjectItem(both, "water_duration_ms"), 5000);
    cJSON_AddNumberToObject(both, "extra", 1);
    assert(!Playback("前进五秒，同时喷水", "self.tank.move_and_water", both, accepted));
    cJSON_DeleteItemFromObject(both, "extra");
    for (const char* bad : {"not_ready_or_busy", "output_fault", "voice_input_failed"}) {
        auto* reply = cJSON_Parse(accepted);cJSON_SetValuestring(cJSON_GetObjectItem(reply, "result"), bad);
        auto* raw = cJSON_PrintUnformatted(reply);
        assert(!Playback("前进五秒，同时喷水", "self.tank.move_and_water", both, raw));
        cJSON_free(raw);cJSON_Delete(reply);
    }
    cJSON_Delete(both);

    const char* steps = R"([{"direction":"forward","move_ms":1000,"water_ms":0,"bubbles_ms":0,"ignition_ms":0},{"direction":"left","move_ms":2000,"water_ms":0,"bubbles_ms":2000,"ignition_ms":0}])";
    auto* sequence = Args(steps);
    const char* sequence_receipt = R"({"operation":"sequence","result":"accepted","fault":"none","sequence_active":true,"sequence_step":1,"sequence_steps":2,"sequence_source":"voice","sequence_result":"running","move_direction":"forward","move_last_duration_ms":1000,"move_source":"voice","move_speed_percent":100})";
    const char* sentence = "先前进一秒，再同时左转两秒和吹泡泡两秒。";
    assert(Playback(sentence, "self.tank.sequence", sequence, sequence_receipt));
    for (int order : {1, 2, 3}) assert(!Playback(sentence, "self.tank.sequence", sequence, sequence_receipt, order));
    for (const char* field : {"sequence_active", "sequence_step", "sequence_steps", "sequence_source", "sequence_result",
                              "move_direction", "move_last_duration_ms", "move_source", "move_speed_percent", "fault"}) {
        auto* reply = cJSON_Parse(sequence_receipt);cJSON_DeleteItemFromObject(reply, field);
        auto* raw = cJSON_PrintUnformatted(reply);
        assert(!Playback(sentence, "self.tank.sequence", sequence, raw));
        cJSON_free(raw);cJSON_Delete(reply);
    }
    for (const char* bad : {R"([{"direction":"forward","move_ms":1000,"water_ms":0,"bubbles_ms":0,"ignition_ms":0}])",
                            R"([{"direction":"left","move_ms":1000,"water_ms":0,"bubbles_ms":0,"ignition_ms":0},{"direction":"forward","move_ms":2000,"water_ms":0,"bubbles_ms":2000,"ignition_ms":0}])",
                            R"([{"direction":"forward","move_ms":1000,"water_ms":0,"bubbles_ms":0,"ignition_ms":0,"speed_percent":80},{"direction":"left","move_ms":2000,"water_ms":0,"bubbles_ms":2000,"ignition_ms":0}])",
                            "[]", "null", "[", "[] trailing"}) {
        auto* args = Args(bad);
        assert(!Playback(sentence, "self.tank.sequence", args, sequence_receipt));
        cJSON_Delete(args);
    }
    cJSON_AddStringToObject(sequence, "steps_json", steps); // Duplicate keys remain audible.
    assert(!Playback(sentence, "self.tank.sequence", sequence, sequence_receipt));
    cJSON_Delete(sequence);

    for (int target = 60; target <= 100; ++target) {
        auto* args = cJSON_CreateObject();cJSON_AddNumberToObject(args, "speed_percent", target);
        std::string phrase = "速度调到" + std::to_string(target) + "%";
        std::string reply = "{\"operation\":\"set_speed\",\"result\":\"accepted\",\"fault\":\"none\",\"move_speed_percent\":" + std::to_string(target) + "}";
        assert(Playback(phrase.c_str(), "self.tank.set_speed", args, reply.c_str()));
        cJSON_SetNumberValue(cJSON_GetObjectItem(args, "speed_percent"), target == 100 ? 90 : target+1);
        assert(!Playback(phrase.c_str(), "self.tank.set_speed", args, reply.c_str()));
        cJSON_Delete(args);
    }
    for (const char* phrase : {"调到百分之六十", "掉到百分之六十", "减速到60%", "速度60"})
        assert(plan.Parse(phrase) && plan.speed == 60);
    for (const char* phrase : {"加速到百分之一百", "速度100％"}) assert(plan.Parse(phrase) && plan.speed == 100);
    for (const char* phrase : {"掉到60", "不要调到60%", "调到60%吗", "调到59%", "调到101%", "调到60.5%", "调到60%然后前进"})
        assert(!plan.Parse(phrase));
}
