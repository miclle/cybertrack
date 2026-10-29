#pragma once
#include <charconv>
#include <cstdint>
#include <string>

namespace ultrasonic {
constexpr unsigned SamplePeriodMs = 100;
constexpr unsigned FreshnessMs = 500;
constexpr unsigned MinDistanceMm = 20;
constexpr unsigned MaxDistanceMm = 4000;

enum class Error { None, NotReady, NoEcho, EchoHigh, InvalidEcho, OutOfRange, Driver, Stale };
inline const char* ErrorName(Error error) {
    switch (error) {
        case Error::None: return "none";
        case Error::NotReady: return "not_ready";
        case Error::NoEcho: return "no_echo";
        case Error::EchoHigh: return "echo_high";
        case Error::InvalidEcho: return "invalid_echo";
        case Error::OutOfRange: return "out_of_range";
        case Error::Driver: return "driver_error";
        case Error::Stale: return "stale";
    }
    return "driver_error";
}
struct DriverStatus {
    const char* last_failure = "none";
    int error_code = 0;
    uint64_t failed_at_ms = 0;
    unsigned failures = 0, restarts = 0, retry_delay_ms = 0;
    bool recovering = false;
};
struct Reading {
    Error error = Error::NotReady;
    unsigned distance_mm = 0;
    unsigned echo_us = 0;
    uint64_t sampled_at_ms = 0;
    bool sampled = false;
    DriverStatus driver{};
};

// RMT samples at 1 MHz. Accept one contiguous HIGH pulse, not multiple echoes
// or noise. End-of-reception padding has zero duration and is not fed here.
class EchoDecoder {
public:
    void Feed(bool high, unsigned us) {
        if (!us) return;
        if (high) {
            if (ended_) invalid_ = true;
            seen_ = true;
            high_us_ += us;
        } else if (seen_) ended_ = true;
        else leading_us_ += us;
    }
    Reading Finish(uint64_t trigger_ms, bool echo_high, bool buffer_full) const {
        Reading r{Error::None, 0, high_us_, trigger_ms, true};
        if (echo_high) r.error = Error::EchoHigh;
        else if (invalid_ || buffer_full) r.error = Error::InvalidEcho;
        else if (!seen_) r.error = Error::NoEcho;
        else if (leading_us_ > 10000) r.error = Error::InvalidEcho;
        else {
            // 343 m/s nominal sound speed; no temperature compensation or
            // claimed millimetre accuracy. Integer millimetres are transport units.
            const uint64_t scaled = uint64_t(high_us_) * 343;
            if (scaled < MinDistanceMm * 2000 || scaled > MaxDistanceMm * 2000)
                r.error = Error::OutOfRange;
            else r.distance_mm = static_cast<unsigned>((scaled + 1000) / 2000);
        }
        return r;
    }
private:
    unsigned high_us_ = 0, leading_us_ = 0;
    bool seen_ = false, ended_ = false, invalid_ = false;
};

inline std::string Decimal(uint64_t value) {
    char text[20];
    const auto end = std::to_chars(text, text + sizeof(text), value).ptr;
    return std::string(text, end);
}
inline std::string Json(const Reading& r, uint64_t now_ms) {
    const bool clock_ok = now_ms >= r.sampled_at_ms;
    const auto age = clock_ok ? now_ms - r.sampled_at_ms : 0;
    const auto error = r.sampled && (!clock_ok || age > FreshnessMs) ? Error::Stale : r.error;
    const bool valid = r.sampled && error == Error::None;
    return "{\"valid\":" + std::string(valid ? "true" : "false") +
        ",\"distance_mm\":" + (valid ? Decimal(r.distance_mm) : "null") +
        ",\"error\":\"" + ErrorName(error) + "\",\"sampled_at_ms\":" +
        (r.sampled ? Decimal(r.sampled_at_ms) : "null") +
        ",\"age_ms\":" + (r.sampled && clock_ok ? Decimal(age) : "null") +
        ",\"echo_us\":" + (r.sampled && r.echo_us ? Decimal(r.echo_us) : "null") +
        ",\"driver\":{\"last_failure\":\"" + r.driver.last_failure +
        "\",\"error_code\":" + std::to_string(r.driver.error_code) +
        ",\"failed_at_ms\":" + Decimal(r.driver.failed_at_ms) +
        ",\"failures\":" + Decimal(r.driver.failures) + ",\"restarts\":" + Decimal(r.driver.restarts) +
        ",\"retry_delay_ms\":" + Decimal(r.driver.retry_delay_ms) +
        ",\"recovering\":" + (r.driver.recovering ? "true" : "false") + "}" +
        ",\"max_age_ms\":500,\"min_mm\":20,\"max_mm\":4000,\"auto_avoidance\":false}";
}
} // namespace ultrasonic
