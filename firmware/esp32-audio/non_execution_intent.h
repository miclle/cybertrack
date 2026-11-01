#pragma once
#include <initializer_list>
#include <string_view>

namespace non_execution {
// Conservative refusal only: matching text never authorizes an actuator.
// Unknown wording still relies on the model/tool contract. Stop is exempt in
// the adapter so a delayed real stop is never lost to a newer input.
inline bool Requested(std::string_view text) {
    for (std::string_view cue : {"预览", "编排", "草稿", "排演", "先别执行", "不要执行", "不执行",
                                 "先别动", "先不要动", "不要启动", "只讨论", "只说说", "修改表演", "编辑表演"})
        if (text.find(cue) != text.npos) return true;
    return false;
}
} // namespace non_execution
