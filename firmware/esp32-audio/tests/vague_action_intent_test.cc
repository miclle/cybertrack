#include "vague_action_intent.h"
#include <cassert>
#include <iostream>
int main() {
    for (const char* text : {"动一下那个东西","让那个东西动起来","移动一下","转一下那个东西","启动一下它","开一下这个",
                             "弄一下那个","来点效果","来个效果","你帮我做点什么","动一下三秒","那个动了吗"})
        assert(vague_action::NeedsClarification(text));
    for (const char* text : {"前进","让那个小车向前动两秒","向右转一下那个机器人","启动一下泡泡","弄一下水枪",
                             "开枪","开炮","开启护盾","放电","饭店一下","开启饭店","去饭店吃饭",
                             "动得快一点","那个速度调到70%","停止","取消序列","检查状态","第二步改成三秒"})
        assert(!vague_action::NeedsClarification(text));
    // A creative proposal can be generic. Admission allows draft edits and
    // still requires the existing version/read/web-confirmation contract.
    assert(vague_action::NeedsClarification("帮我编排一个表演，你来想动作"));
    std::cout << "PASS: generic action category and named/direction/alias contrasts\n";
}
