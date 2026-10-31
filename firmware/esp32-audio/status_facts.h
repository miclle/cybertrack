#pragma once
#include <string>
#include <string_view>

// All fragments are fixed firmware text and safe to embed in a JSON string.
inline std::string StatusFacts(std::string_view fault, bool blocked, bool sequence,
                               bool any_output, std::string_view last_result) {
    std::string facts;
    if (fault == "output_fault" || fault == "driver_error") facts += "驱动输出故障。";
    if (fault == "clock_fault") facts += "设备计时故障。";
    if (blocked) facts += "前进保护已锁定。障碍移开并解除保护后，仍需新的前进指令，旧动作不会恢复。";
    if (sequence && !any_output) facts += "表演仍在进行，当前在步骤间等待。";
    if (last_result.empty()) facts += "没有最近的动作回执，无法据此解释上一次动作。";
    else if (last_result == "not_ready_or_busy") facts += "上次请求被拒绝，回执没有区分未就绪或忙碌，也没有具体原因。";
    else if (last_result == "accepted") facts += "上次请求已被控制器接受，这条回执没有记录停止原因。";
    facts += "设备没有电量读数和实际动作反馈。";
    return facts;
}

// Expose the show's narrower contract separately from the robot's direct tools.
inline constexpr char DraftEditingCapabilities[] =
    R"({"allowed":["move","bubbles"],"unsupported":["water","ignition"],"confirmation":"web","explanation":"草稿只支持行走和泡泡。喷水无法加入表演，改变时长也无法添加。"})";

inline const char* FaultRecovery(std::string_view fault) {
    return fault == "output_fault" || fault == "driver_error"
        ? "请保持停止，请家长检查驱动输出。未查明故障前不要重启或试跑。" : nullptr;
}
