// Read one captured case from stdin and replay wire order through the firmware
// policy. Optionally count every recorded packet without decoding audio.
#include "voice_feedback.h"
#include <iostream>
#include <string>
int main(int argc, char** argv) {
    const bool packets = argc == 2 && std::string(argv[1]) == "--packets";
    if (argc != 1 && !packets) return 1;
    std::string line;
    if (!std::getline(std::cin,line)) return 1;
    auto* row = cJSON_Parse(line.c_str());
    auto get = cJSON_GetObjectItemCaseSensitive;
    auto str = [&](cJSON* obj,const char* key) {
        auto* field = get(obj,key);
        return std::string(cJSON_IsString(field) ? field->valuestring : "");
    };
    if (!row || !cJSON_IsArray(get(row,"timeline"))) { cJSON_Delete(row); return 1; }
    VoiceFeedback feedback;
    int call_index=0, receipt_index=0;
    int muted=0, audible=0;
    uint64_t bytes=0;
    uint64_t call=0;
    std::string first_packet="absent";
    cJSON* item;
    cJSON_ArrayForEach(item,get(row,"timeline")) {
        auto event = str(item,"event");
        if (event=="stt") feedback.Input(str(item,"text"));
        else if (event=="tool_call") {
            auto* entry=cJSON_GetArrayItem(get(row,"calls"),call_index++);
            auto name=str(entry,"name");
            if (name.compare(0,10,"self_tank_")==0) name.replace(0,10,"self.tank.");
            call=feedback.BeginCall(name,get(entry,"arguments"));
        } else if (event=="tool_reply_sent" && !cJSON_IsTrue(get(item,"is_error"))) {
            auto* receipt=cJSON_GetArrayItem(get(row,"simulated_receipts"),receipt_index++);
            auto* json=cJSON_PrintUnformatted(receipt);
            if (json) { feedback.Receipt(call,json); cJSON_free(json); }
        } else if (event=="tts_start") feedback.StartSpeech();
        else if (event=="tts_stop") feedback.Input("");
        else if (event=="audio_packet" && packets) {
            const auto* size=get(item,"size");
            if (!cJSON_IsNumber(size) || size->valueint <= 0 || size->valuedouble != size->valueint) {
                cJSON_Delete(row);
                return 1;
            }
            bytes += size->valueint;
            if (feedback.Muted()) ++muted; else ++audible;
        } else if (event=="first_audio") first_packet=feedback.Muted() ? "suppressed" : "audible";
    }
    if (packets) {
        const auto* total=get(row,"received_audio_bytes_discarded");
        if (!cJSON_IsNumber(total) || total->valuedouble != bytes || !bytes) {
            cJSON_Delete(row);
            return 1;
        }
        std::cout << "{\"suppressed\":" << muted << ",\"audible\":" << audible << "}" << '\n';
    } else std::cout << first_packet << '\n';
    cJSON_Delete(row);
}
