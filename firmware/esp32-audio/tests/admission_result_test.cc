#include "admission_result.h"
#include <cassert>
#include <cstring>

int main() {
    for (const char* tool : {"set_speed","adjust_speed"}) {
        const char* reason = "设备未移动，拒绝 \"全速\"\nNo action started.";
        const auto raw = CyberTrackAdmissionResult(tool,reason);
        auto* envelope = cJSON_Parse(raw.c_str());
        assert(cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(envelope,"isError")));
        auto* content = cJSON_GetObjectItemCaseSensitive(envelope,"content");
        assert(cJSON_IsArray(content) && cJSON_GetArraySize(content)==1);
        auto* entry = cJSON_GetArrayItem(content,0);
        assert(!strcmp(cJSON_GetObjectItemCaseSensitive(entry,"type")->valuestring,"text"));
        auto* receipt = cJSON_Parse(cJSON_GetObjectItemCaseSensitive(entry,"text")->valuestring);
        assert(!strcmp(cJSON_GetObjectItemCaseSensitive(receipt,"operation")->valuestring,tool));
        assert(!strcmp(cJSON_GetObjectItemCaseSensitive(receipt,"result")->valuestring,"rejected"));
        assert(!strcmp(cJSON_GetObjectItemCaseSensitive(receipt,"rejection_reason")->valuestring,reason));
        assert(cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(receipt,"physical_feedback")));
        cJSON_Delete(receipt);
        cJSON_Delete(envelope);
    }
}
