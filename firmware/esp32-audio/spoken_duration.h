#pragma once
#include <string_view>

// Consume one Arabic or Chinese digit from a recognized duration.
inline int SpokenDigit(std::string_view& text) {
    constexpr std::string_view digits[] = {"零", "一", "二", "三", "四", "五", "六", "七", "八", "九"};
    if (!text.empty() && text.front() >= '0' && text.front() <= '9') {
        int value = text.front() - '0';
        text.remove_prefix(1);
        return value;
    }
    if (text.substr(0, 3) == "两") {
        text.remove_prefix(3);
        return 2;
    }
    for (int i = 0; i < 10; ++i) {
        if (text.substr(0, digits[i].size()) == digits[i]) {
            text.remove_prefix(digits[i].size());
            return i;
        }
    }
    return -1;
}

inline int SpokenWhole(std::string_view text) {
    if (text.empty()) return -1;
    if (text.front() >= '0' && text.front() <= '9') {
        int value = 0;
        for (char digit : text) {
            if (digit < '0' || digit > '9' || value > 3000) return -1;
            value = value * 10 + digit - '0';
        }
        return value <= 30000 ? value : -1;
    }
    auto ten = text.find("十");
    if (ten != std::string_view::npos) {
        auto tens_text = text.substr(0, ten);
        auto units_text = text.substr(ten + 3);
        int tens = tens_text.empty() ? 1 : SpokenDigit(tens_text);
        bool has_units = !units_text.empty();
        int units = has_units ? SpokenDigit(units_text) : 0;
        if (!tens_text.empty() || !units_text.empty() || tens < 1 ||
            units < 0 || units > 9 || (has_units && units == 0)) return -1;
        return tens * 10 + units;
    }
    int digit = SpokenDigit(text);
    return text.empty() ? digit : -1;
}

// Playback whitelist only. Unknown syntax stays audible; this never starts actions.
inline int SpokenEffectMs(std::string_view text) {
    while (!text.empty() && text.front() == ' ') text.remove_prefix(1);
    while (!text.empty() && text.back() == ' ') text.remove_suffix(1);
    bool half = text.size() >= 6 && text.substr(text.size() - 6) == "秒半";
    if (half) text.remove_suffix(3);
    bool milliseconds = text.size() >= 6 && text.substr(text.size() - 6) == "毫秒";
    const auto unit = milliseconds ? std::string_view("毫秒") : std::string_view("秒");
    if (text.size() <= unit.size() || text.substr(text.size() - unit.size()) != unit) return 0;
    text.remove_suffix(unit.size());
    while (!text.empty() && text.back() == ' ') text.remove_suffix(1);
    if (milliseconds) {
        if (half) return 0;
        int value = SpokenWhole(text);
        return value >= 1 && value <= 30000 ? value : 0;
    }
    if (text == "半") return half ? 0 : 500;

    auto point = text.find('.');
    std::size_t point_size = 1;
    if (point == std::string_view::npos) {
        point = text.find("点");
        point_size = 3;
    }
    int whole = SpokenWhole(text.substr(0, point));
    int fraction = half ? 500 : 0;
    if (whole < 0 || whole > 30) return 0;
    if (point != std::string_view::npos) {
        if (half) return 0;
        auto rest = text.substr(point + point_size);
        if (rest.empty()) return 0;
        int scale = 100;
        while (!rest.empty()) {
            int digit = SpokenDigit(rest);
            if (digit < 0 || scale == 0) return 0;
            fraction += digit * scale;
            scale /= 10;
        }
    }
    int ms = whole * 1000 + fraction;
    return ms >= 1 && ms <= 30000 ? ms : 0;
}
