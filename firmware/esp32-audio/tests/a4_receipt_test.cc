// Compile the production A4 receipt path with a controlled permission snapshot.
#define CYBERTRACK_MAINBOARD_A4 1
bool actuator_armed = false;
#include "receipt_host.h"
int main() {
    auto check = [](const char* fault) {
        auto* data = cJSON_Parse(Reply("get_status").c_str());
        assert(data && cJSON_IsBool(cJSON_GetObjectItem(data, "drive_armed")));
        assert(!!cJSON_IsTrue(cJSON_GetObjectItem(data, "drive_armed")) == actuator_armed);
        assert(!std::strcmp(cJSON_GetStringValue(cJSON_GetObjectItem(data, "fault")), fault));
        assert(!std::strcmp(cJSON_GetStringValue(cJSON_GetObjectItem(data, "actuator_backend")), "a4_dual_drv8874"));
        cJSON_Delete(data);
    };
    check("actuator_disarmed");
    outputs.fault = true;
    check("output_fault");
    actuator_armed = true;
    check("output_fault"); // Hardware permission does not clear a software fault.
}
