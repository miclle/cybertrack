#pragma once
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <initializer_list>

// One bounded receipt, copied while holding the adapter mutex. Status reads do
// not replace it. This is request history, not a physical sensor or stop cause.
struct RecentCommand {
    char operation[32] = {}, result[40] = {};
    uint64_t at = 0;
    bool valid = false, web = false;
    void Record(uint64_t now, const char* op, const char* outcome, bool from_web) {
        bool action = false;
        for (const auto name : {"move", "water", "bubbles", "ignition", "move_and_water", "sequence", "frenzy",
                               "stop", "set_speed", "adjust_speed", "set_auto_avoidance", "drive_start", "drive_stop",
                               "drive_renew", "water_start", "water_stop", "water_renew", "bubbles_start", "bubbles_stop", "bubbles_renew"})
            action |= !std::strcmp(op, name);
        if (!action || !std::strcmp(outcome, "renewed")) return;
        if (std::strlen(outcome) >= sizeof(result)) return;
        // Results are firmware identifiers. Reject arbitrary text rather than
        // interpolate an unescaped string into the device's JSON reply.
        for (const char* c = outcome; *c; ++c)
            if ((*c < 'a' || *c > 'z') && *c != '_') return;
        std::snprintf(operation, sizeof(operation), "%s", op);
        std::snprintf(result, sizeof(result), "%s", outcome);
        at = now; web = from_web; valid = true;
    }
};
