#include "negative_input_intent.h"
#include <iostream>
#include <iterator>
#include <string>
int main() {
    const std::string text(std::istreambuf_iterator<char>(std::cin), {});
    std::cout << static_cast<int>(negative_input::Classify(text)) << '\n';
}
