// Host-only inspection of the same classifier used by the STT callback.
#include "draft_duration_intent.h"
#include <iostream>
#include <iterator>
#include <string>
int main() {
    const std::string text{std::istreambuf_iterator<char>(std::cin), std::istreambuf_iterator<char>()};
    std::cout << (draft_duration::NeedsClarification(text) ? "true\n" : "false\n");
}
