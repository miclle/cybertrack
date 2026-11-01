#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <vector>

// Same audible tone as sounds/generate_range_tones.py, at the codec output rate.
// Ordinary notifications never enter or reset the cloud Opus decoder.
inline std::vector<int16_t> RangeNotificationPcm(int rate) {
    if (rate < 8000 || rate > 96000) return {};
    std::vector<int16_t> pcm(rate * 80 / 1000);
    const int fade = std::max(1, rate * 5 / 1000);
    for (size_t i = 0; i < pcm.size(); ++i) {
        const double envelope = static_cast<double>(std::min({fade, static_cast<int>(i),
            static_cast<int>(pcm.size() - 1 - i)})) / fade;
        pcm[i] = static_cast<int16_t>(std::lround(32767 * 0.18 * envelope *
            std::sin(6.283185307179586 * 1400 * i / rate)));
    }
    return pcm;
}
