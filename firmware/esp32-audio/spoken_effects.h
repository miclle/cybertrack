#pragma once
#include <string_view>

// Playback vocabulary only; actuator limits and admission remain independent.
struct SpokenEffectAlias {
    std::string_view phrase, tool, duration_field;
    int lane, default_ms, maximum_ms;
    bool compound;
};
inline constexpr SpokenEffectAlias spoken_effects[] = {
    {"喷水","water","water_last_duration_ms",1,1000,30000,true},
    {"发射","water","water_last_duration_ms",1,1000,30000,true},
    {"开枪","water","water_last_duration_ms",1,1000,30000,true},
    {"射击","water","water_last_duration_ms",1,1000,30000,true},
    {"吹泡泡","bubbles","bubbles_last_duration_ms",2,1000,30000,true},
    {"开炮","bubbles","bubbles_last_duration_ms",2,1000,30000,true},
    // The homophone correction is limited to independent short phrases.
};
