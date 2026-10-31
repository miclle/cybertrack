#include "voice_feedback.h"
#include <cassert>
#include <cstdio>
#include <string>

// Independently construct the protocol expectation; never execute a command.
struct Expected {
    std::array<int,4> ms;
    const char* direction = "forward";
};
static const char* Tool(const Expected& expected, unsigned count=1) {
    unsigned mask=0;
    for (unsigned lane=0;lane<4;++lane) if (expected.ms[lane]) mask|=1u<<lane;
    if (count>1 || (mask!=1 && mask!=2 && mask!=4 && mask!=8 && mask!=3)) return "sequence";
    return mask==3?"move_and_water":mask==1?"move":mask==2?"water":mask==4?"bubbles":"ignition";
}
static cJSON* Step(const Expected& expected) {
    auto* step=cJSON_CreateObject();
    cJSON_AddStringToObject(step,"direction",expected.ms[0]?expected.direction:"none");
    const char* fields[]={"move_ms","water_ms","bubbles_ms","ignition_ms"};
    for (unsigned lane=0;lane<4;++lane) cJSON_AddNumberToObject(step,fields[lane],expected.ms[lane]);
    return step;
}
static cJSON* Args(const Expected& expected, const Expected* next=nullptr) {
    const std::string_view tool=Tool(expected,next?2:1);
    auto* args=cJSON_CreateObject();
    if (tool=="sequence") {
        auto* array=cJSON_CreateArray();cJSON_AddItemToArray(array,Step(expected));
        if (next) cJSON_AddItemToArray(array,Step(*next));
        auto* raw=cJSON_PrintUnformatted(array);cJSON_AddStringToObject(args,"steps_json",raw);
        cJSON_free(raw);cJSON_Delete(array);
    } else if (tool=="move_and_water") {
        cJSON_AddStringToObject(args,"direction",expected.direction);
        cJSON_AddNumberToObject(args,"move_duration_ms",expected.ms[0]);
        cJSON_AddNumberToObject(args,"water_duration_ms",expected.ms[1]);
    } else {
        if (tool=="move") cJSON_AddStringToObject(args,"direction",expected.direction);
        int duration=0;for (int ms:expected.ms) if(ms) duration=ms;
        cJSON_AddNumberToObject(args,"duration_ms",duration);
    }
    return args;
}
static cJSON* Receipt(const Expected& expected, unsigned count=1) {
    auto* receipt=cJSON_CreateObject();
    cJSON_AddStringToObject(receipt,"operation",Tool(expected,count));
    cJSON_AddStringToObject(receipt,"result","accepted");cJSON_AddStringToObject(receipt,"fault","none");
    cJSON_AddNumberToObject(receipt,"last_duration_ms",30000); // Other active lanes must not dominate a match.
    const char* durations[]={"move_last_duration_ms","water_last_duration_ms","bubbles_last_duration_ms","ignition_last_duration_ms"};
    const char* sources[]={"move_source","water_source","bubbles_source","ignition_source"};
    for(unsigned lane=0;lane<4;++lane) if(expected.ms[lane]) {
        cJSON_AddNumberToObject(receipt,durations[lane],expected.ms[lane]);cJSON_AddStringToObject(receipt,sources[lane],"voice");
    }
    if(expected.ms[0]) {
        cJSON_AddStringToObject(receipt,"move_direction",expected.direction);cJSON_AddNumberToObject(receipt,"move_speed_percent",100);
    }
    if(std::string_view(Tool(expected,count))=="sequence") {
        cJSON_AddBoolToObject(receipt,"sequence_active",true);cJSON_AddNumberToObject(receipt,"sequence_step",1);
        cJSON_AddNumberToObject(receipt,"sequence_steps",count);cJSON_AddStringToObject(receipt,"sequence_source","voice");
        cJSON_AddStringToObject(receipt,"sequence_result","running");
    }
    return receipt;
}
static bool Muted(const std::string& text, const Expected& expected, cJSON* args, cJSON* receipt, unsigned count=1, int order=0) {
    VoiceFeedback feedback;feedback.Input(text);
    auto token=feedback.BeginCall(std::string("self.tank.")+Tool(expected,count),args);
    if(order==1) feedback.StartSpeech();
    if(order==2) feedback.Input("现在什么状态？");
    if(order==3) feedback.BeginCall("self.tank.get_status",nullptr);
    auto* raw=cJSON_PrintUnformatted(receipt);feedback.Receipt(token,raw);cJSON_free(raw);
    feedback.StartSpeech();return feedback.Muted();
}
int main() {
    unsigned positive=0,preserved=0;
    const char* words[]={"前进三秒","喷水两秒","吹泡泡一秒","点火半秒"};
    const std::array<int,4> durations={3000,2000,1000,500};
    for(unsigned mask=1;mask<16;++mask) {
        Expected expected{};std::string sentence;
        for(unsigned lane=0;lane<4;++lane) if(mask&(1u<<lane)) {
            expected.ms[lane]=durations[lane];if(!sentence.empty())sentence+="并";sentence+=words[lane];
        }
        auto* args=Args(expected);auto* receipt=Receipt(expected);
        assert(Muted(sentence,expected,args,receipt));++positive;
        for(int order:{1,2,3}) {assert(!Muted(sentence,expected,args,receipt,1,order));++preserved;}
        cJSON_SetValuestring(cJSON_GetObjectItem(receipt,"fault"),"output_fault");
        assert(!Muted(sentence,expected,args,receipt));++preserved;
        cJSON_Delete(args);cJSON_Delete(receipt);
    }
    const std::pair<const char*,unsigned> aliases[]={
        {"喷水",1},{"发射",1},{"开枪",1},{"射击",1},{"吹泡泡",2},{"开炮",2},
        {"点火",3},{"放电",3},{"闪电",3},{"护盾",3},{"打火",3},{"电击",3}};
    for(auto alias:aliases) for(const char* prefix:{"","开启"}) for(bool reverse:{false,true}) {
        Expected expected{{1000,0,0,0}};expected.ms[alias.second]=2000;
        auto* args=Args(expected);auto* receipt=Receipt(expected);
        std::string effect=std::string(prefix)+alias.first+"两秒";
        assert(Muted(reverse?effect+"并前进一秒":"前进一秒并"+effect,expected,args,receipt));++positive;
        cJSON_Delete(args);cJSON_Delete(receipt);
    }
    for(const char* text:{"同时前进和喷水和吹泡泡和点火两秒","前进两秒并喷水两秒并吹泡泡两秒并点火两秒"}) {
        Expected expected{{2000,2000,2000,2000}};auto* args=Args(expected);auto* receipt=Receipt(expected);
        assert(Muted(text,expected,args,receipt));++positive;cJSON_Delete(args);cJSON_Delete(receipt);
    }
    for(const auto& item:{std::pair<const char*,Expected>{"同时前进和喷水和吹泡泡和点火五秒",Expected{{5000,5000,5000,5000}}},
                         {"喷水三十秒并护盾五秒",Expected{{0,30000,0,5000}}}}) {
        auto* args=Args(item.second);auto* receipt=Receipt(item.second);
        assert(Muted(item.first,item.second,args,receipt));++positive;cJSON_Delete(args);cJSON_Delete(receipt);
    }
    {
        Expected first{{5000,0,0,0}},next{{0,0,0,1000}};
        auto* args=Args(first,&next);auto* receipt=Receipt(first,2);
        assert(Muted("先前进五秒，然后点火",first,args,receipt,2));++positive;cJSON_Delete(args);cJSON_Delete(receipt);
    }
    Expected first{{0,1000,0,1000}},next{{0,0,2000,0}};
    auto* args=Args(first,&next);auto* receipt=Receipt(first,2);
    const char* sentence="先开枪并开启护盾，然后开炮两秒";
    assert(Muted(sentence,first,args,receipt,2));++positive;
    for(const char* field:{"ignition_last_duration_ms","ignition_source","water_last_duration_ms","water_source", "sequence_source","sequence_steps"}) {
        auto* changed=cJSON_Duplicate(receipt,true);cJSON_DeleteItemFromObject(changed,field);
        assert(!Muted(sentence,first,args,changed,2));++preserved;cJSON_Delete(changed);
    }
    for(const char* field:{"ignition_last_duration_ms","water_last_duration_ms"}) {
        auto* changed=cJSON_Duplicate(receipt,true);cJSON_SetNumberValue(cJSON_GetObjectItem(changed,field),500);
        assert(!Muted(sentence,first,args,changed,2));++preserved;cJSON_Delete(changed);
    }
    auto* web=cJSON_Duplicate(receipt,true);cJSON_SetValuestring(cJSON_GetObjectItem(web,"ignition_source"),"web");
    assert(!Muted(sentence,first,args,web,2));++preserved;cJSON_Delete(web);
    auto* changed=Args(first,&next);auto* encoded=cJSON_GetObjectItem(changed,"steps_json");
    auto* plan=cJSON_Parse(encoded->valuestring);cJSON_SetNumberValue(cJSON_GetObjectItem(cJSON_GetArrayItem(plan,1),"bubbles_ms"),1000);
    auto* raw=cJSON_PrintUnformatted(plan);cJSON_SetValuestring(encoded,raw);cJSON_free(raw);cJSON_Delete(plan);
    assert(!Muted(sentence,first,changed,receipt,2));++preserved;cJSON_Delete(changed);
    cJSON_Delete(args);cJSON_Delete(receipt);
    SpokenPlayback playback;
    assert(playback.Parse("先前进然后点火") && playback.count==2 && playback.steps[1].ms[3]==1000);++positive;
    for(const char* text:{"前进十秒并点火","先前进然后点火六秒","点火六秒和喷水","喷水六十秒和点火", "前进和点火八秒",
                         "不要点火并喷水","先点火吗再喷水","护盾结束了吗","去饭店并喷水","饭店并喷水","先饭店然后点火",
                         "狂暴模式并喷水","开枪和喷水","点火并放电","前进并未知动作","先点火然后", "编排开枪并护盾"}) {
        assert(!playback.Parse(text));++preserved;
    }
    printf("four-lane playback: %u positive, %u explanations preserved\n",positive,preserved);
}
