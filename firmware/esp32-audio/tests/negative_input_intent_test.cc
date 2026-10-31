#include "negative_input_intent.h"
#include <cassert>
#include <iostream>

int main() {
    using negative_input::Classify;
    using negative_input::Kind;
    for (auto text : {"不要前进","别喷水","不要开启狂暴模式","不许吹泡泡","不要放电","不要饭店",
                      "请先不要启动泡泡。","不要前进，不要放电"," 不准点火! "})
        assert(Classify(text)==Kind::NoNewAction);
    for (auto text : {"不要编排表演","这次先别编排新的表演","先不要创建节目，保留现在的草稿",
                      "别取消这份草稿","我没让你取消草稿","不要停止当前序列","不要停","保留当前草稿"})
        assert(Classify(text)==Kind::PreserveExisting);
    // Actual stopping, questions, quotes, mixed requests and unknown forms
    // must remain outside this bounded refusal grammar.
    for (auto text : {"停止","停下","停止行走","取消序列","所有动作都停下来","别动","不要再动了",
                      "别喷水了","别再往前走了，马上停下","先别编排了，马上停下","不要放电，停下",
                      "先不要编排，直接吹泡泡两秒","别编排新节目，告诉我前方多远",
                      "不要停止当前序列，不要喷水","不要喷水吗","不许吹泡泡？","他说不要放电",
                      "‘不要放电’是什么意思","不要放电然后停止","不要前进，","不要前进，未知",
                      "帮我编排一段先左转，再吹泡泡的表演，先别执行","前进一秒",""," "})
        assert(Classify(text)==Kind::None);
    std::cout << "PASS: whole negative clauses; true stop, mixed request, quote and question counterexamples defer\n";
}
