#pragma once
#include <string_view>
#include <initializer_list>

namespace vague_action {
// This only detects a limited generic-action category. Named words defer to
// the existing model/tool contract; they do not authorize an output here.
inline bool NeedsClarification(std::string_view text) {
    bool generic=false;
    for (std::string_view cue : {"动","转","开","启动","弄","效果","做点什么","来一下"})
        if (text.find(cue)!=text.npos) generic=true;
    if (!generic) return false;
    for (std::string_view named : {"前进","后退","退后","倒退","向前","向后","往前","往后","朝前","朝后","左","右",
                                   "喷","水","泡泡","点火","火花","开枪","开炮","射击","发射","放电","闪电","护盾","打火","电击",
                                   "狂暴","速度","加速","减速","全速","最快","快一点","慢一点","饭店"})
        if (text.find(named)!=text.npos) return false;
    return true;
}
// Block writes for an entire voice turn containing a retired effect.
inline bool MentionsRetiredEffect(std::string_view text) {
    for (std::string_view retired : {"点火", "火花", "放电", "闪电", "护盾", "打火", "电击", "狂暴模式"})
        if (text.find(retired) != text.npos) return true;
    return false;
}
} // namespace vague_action
