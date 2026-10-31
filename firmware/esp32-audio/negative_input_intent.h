#pragma once
#include <string_view>
#include <initializer_list>

namespace negative_input {
enum class Kind { None, NoNewAction, PreserveExisting };

inline bool TakePrefix(std::string_view& text, std::string_view prefix) {
    if (text.substr(0,prefix.size())!=prefix) return false;
    text.remove_prefix(prefix.size());return true;
}
inline std::string_view Trim(std::string_view text) {
    while (!text.empty() && (text.front()==' ' || text.front()=='\t' || text.front()=='\n' || text.front()=='\r')) text.remove_prefix(1);
    while (!text.empty() && (text.back()==' ' || text.back()=='\t' || text.back()=='\n' || text.back()=='\r')) text.remove_suffix(1);
    return text;
}
inline Kind Clause(std::string_view text) {
    text=Trim(text);
    // Match a whole bounded clause; quotes, questions, mixed positive requests
    // and unknown wording defer to the existing model/stop contract.
    for (unsigned count=0;count<4;++count) {
        bool removed=false;
        for (auto prefix : {"这次","现在","暂时","请","先","你"})
            if (TakePrefix(text,prefix)) { removed=true;break; }
        if (!removed) break;
    }
    for (auto keep : {"保留现在的草稿","保留当前草稿","保留这份草稿"})
        if (text==keep) return Kind::PreserveExisting;
    bool negated=false;
    for (auto prefix : {"不要","不许","不准","不用","禁止","别","我没让你"})
        if (TakePrefix(text,prefix)) { negated=true;break; }
    if (!negated) return Kind::None;
    for (auto body : {"编排","编排表演","编排新节目","编排新的表演","创建节目","创建表演","新建表演",
                      "取消草稿","取消这个草稿","取消这份草稿","取消表演","取消序列",
                      "停止","停","停下","停下来","停止当前序列","停止序列","停止当前动作","取消当前序列"})
        if (text==body) return Kind::PreserveExisting;
    for (auto prefix : {"开启","启动","打开","执行"})
        if (TakePrefix(text,prefix)) break;
    for (auto body : {"前进","后退","左转","右转","喷水","吹泡泡","泡泡","点火","放电","饭店",
                      "开枪","开炮","射击","发射","电击","护盾","打火","狂暴模式"})
        if (text==body) return Kind::NoNewAction;
    return Kind::None;
}
inline Kind Classify(std::string_view text) {
    text=Trim(text);
    for (std::string_view suffix : {"。","！","!"}) {
        if (text.size()>=suffix.size() && text.substr(text.size()-suffix.size())==suffix) {
            text.remove_suffix(suffix.size());break;
        }
    }
    Kind result=Kind::None;
    while (!text.empty()) {
        size_t split=text.size(), width=0;
        for (std::string_view delimiter : {"，",",","；",";"}) {
            const auto at=text.find(delimiter);
            if (at<split) { split=at;width=delimiter.size(); }
        }
        const auto clause=Clause(text.substr(0,split));
        if (clause==Kind::None) return Kind::None;
        if (result!=Kind::None && result!=clause) return Kind::None;
        result=clause;
        if (!width) return result;
        text.remove_prefix(split+width);
        if (Trim(text).empty()) return Kind::None;
    }
    return Kind::None;
}
} // namespace negative_input
