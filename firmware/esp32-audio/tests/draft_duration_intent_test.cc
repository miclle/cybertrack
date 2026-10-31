#include "draft_duration_intent.h"
#include <cassert>
#include <iostream>

int main() {
    for (const char* text : {"第二步短一点","第2步再短点","把结尾的泡泡改短","把表演时间延长一点",
                             "最后一步长一些","第一步稍短一点","把泡泡时间少一点","草稿再缩短些",
                             "节目更长一些","短一点","再长一些吧","第二步短一点。"})
        assert(draft_duration::NeedsClarification(text));
    for (const char* text : {"第二步缩短到0.001秒","把第二步缩短到半秒","把第二步改短为两秒半",
                             "结尾泡泡长一点，改为一分半","最后一步长一点，设置为2小时",
                             "第二步缩短至500 ms","第二步稍长一点，设为３秒","第二步缩短一半",
                             "第二步延长到两倍","第二步时间缩短50%","第二步改成三秒",
                             "第一步改长为三周","第一步改长为两天","第一步加长到两个星期","第二步缩短到1000微秒",
                             "第一步延长到3h","第二步缩短到俩秒","第二步缩短到仨秒","第二步改成右转","取消草稿","删除第二步","停止",
                             "回答短一点","请回答得短一点","介绍草稿时说话短一点","泡泡表演解释得短一点"})
        assert(!draft_duration::NeedsClarification(text));
    // These contain no precise time; an ordinal is not a duration.
    for (const char* text : {"第二步缩短几秒","第12步长一点"})
        assert(draft_duration::NeedsClarification(text));
    std::cout << "PASS: unquantified relative draft category and explicit/speech contrasts\n";
}
