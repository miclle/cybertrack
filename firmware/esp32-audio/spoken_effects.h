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
    {"点火","ignition","ignition_last_duration_ms",3,1000,5000,true},
    {"放电","ignition","ignition_last_duration_ms",3,1000,5000,true},
    {"闪电","ignition","ignition_last_duration_ms",3,1000,5000,true},
    {"护盾","ignition","ignition_last_duration_ms",3,1000,5000,true},
    {"打火","ignition","ignition_last_duration_ms",3,1000,5000,true},
    {"电击","ignition","ignition_last_duration_ms",3,1000,5000,true},
    // The homophone correction is limited to independent short phrases.
    {"饭店","ignition","ignition_last_duration_ms",3,1000,5000,false},
    {"狂暴模式","frenzy","frenzy_last_duration_ms",-1,5000,30000,false}
};
