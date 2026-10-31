#pragma once
#include <string_view>
#include <initializer_list>

// A limited category check, not a natural-language action parser. Quantified
// text is left to the existing model/parameter contract; no value is inferred.
namespace draft_duration {
inline bool NumberBefore(std::string_view text, std::size_t end) {
    while (end && (text[end-1]==' ' || text[end-1]=='\t')) --end;
    if (end>=3 && text.substr(end-3,3)=="个") end-=3;
    while (end && (text[end-1]==' ' || text[end-1]=='\t')) --end;
    if (!end) return false;
    if (text[end-1]>='0' && text[end-1]<='9') return true;
    for (std::string_view number : {"零","一","二","两","俩","三","仨","四","五","六","七","八","九",
                                    "十","百","千","万","亿","半","０","１","２","３","４","５","６","７","８","９"})
        if (end>=number.size() && text.substr(end-number.size(),number.size())==number) return true;
    return false;
}
inline bool Quantified(std::string_view text) {
    for (std::string_view unit : {"毫秒","微秒","纳秒","秒","分钟","分","小时","时","天","日","周","星期","个月","月","年",
                                 "ms","s","MS","S","min","h","d","μs","us","ns","%","％","倍","成"})
        for (auto i=text.find(unit); i!=text.npos; i=text.find(unit,i+unit.size()))
            if (NumberBefore(text,i)) return true;
    for (std::string_view ratio : {"一半","减半","加倍","翻倍"})
        if (text.find(ratio)!=text.npos) return true;
    return false;
}
inline bool NeedsClarification(std::string_view text) {
    if (Quantified(text)) return false;
    for (std::string_view cue : {"短一点","短点","短一些","长一点","长点","长一些","缩短","延长",
                                 "加长","改短","改长","更短","更长","稍短","稍长","少一点","多一点"}) {
        for (auto i=text.find(cue); i!=text.npos; i=text.find(cue,i+cue.size())) {
            const auto before=text.substr(0,i);
            bool speech=false;
            for (std::string_view verb : {"说话","说得","讲得","回答","回答得","回复","回复得","解释","解释得","介绍","介绍得"})
                if (before.size()>=verb.size() && before.substr(before.size()-verb.size())==verb) speech=true;
            if (speech) continue;
            for (std::string_view topic : {"步","草稿","表演","节目","结尾","末尾","泡泡"})
                if (before.find(topic)!=before.npos) return true;
            auto bare=text;
            while (!bare.empty() && (bare.front()==' ' || bare.front()=='\t')) bare.remove_prefix(1);
            if (bare.substr(0,3)=="再") bare.remove_prefix(3);
            for (std::string_view suffix : {"。","！","!","吧"})
                if (bare.size()>=suffix.size() && bare.substr(bare.size()-suffix.size())==suffix) bare.remove_suffix(suffix.size());
            if (bare==cue) return true;
        }
    }
    return false;
}
} // namespace draft_duration
