#include "distance_reading.h"
#include <cassert>
#include <iostream>
#include <limits>

using namespace ultrasonic;
Reading pulse(unsigned us) {
    EchoDecoder d;
    d.Feed(false, 200); d.Feed(true, us); d.Feed(false, 25000);
    return d.Finish(1000, false, false);
}
int main() {
    auto r = pulse(5831);
    assert(r.error == Error::None && r.distance_mm == 1000);
    assert(pulse(116).error == Error::OutOfRange);
    assert(pulse(117).error == Error::None && pulse(117).distance_mm == 20);
    assert(pulse(23323).error == Error::None && pulse(23323).distance_mm == 4000);
    assert(pulse(23324).error == Error::OutOfRange);
    assert(pulse(25000).error == Error::OutOfRange);
    EchoDecoder empty;
    empty.Feed(false, 25000);
    assert(empty.Finish(0, false, false).error == Error::NoEcho);
    assert(empty.Finish(0, true, false).error == Error::EchoHigh);
    EchoDecoder noisy;
    noisy.Feed(false, 100); noisy.Feed(true, 300); noisy.Feed(false, 10); noisy.Feed(true, 300);
    assert(noisy.Finish(0, false, false).error == Error::InvalidEcho);
    EchoDecoder late;
    late.Feed(false, 10001); late.Feed(true, 1000);
    assert(late.Finish(0, false, false).error == Error::InvalidEcho);
    EchoDecoder split;
    split.Feed(true, 3000); split.Feed(true, 2831); split.Feed(false, 25000);
    assert(split.Finish(0, false, false).distance_mm == 1000);
    assert(split.Finish(0, false, true).error == Error::InvalidEcho);
    assert(Json({}, 0).find("\"error\":\"not_ready\"") != std::string::npos);
    assert(Json({}, 0).find("\"age_ms\":null") != std::string::npos);
    assert(Json(r, 1500).find("\"valid\":true") != std::string::npos);
    for (auto now : {999, 1501}) {
        const auto json = Json(r, now);
        assert(json.find("\"distance_mm\":null") != std::string::npos);
        assert(json.find("\"error\":\"stale\"") != std::string::npos);
    }
    // An invalid next sample immediately replaces a valid value; no hold-last-good.
    r = pulse(1);
    assert(Json(r, 1100).find("\"distance_mm\":null") != std::string::npos);
    r = pulse(5831); r.sampled_at_ms = std::numeric_limits<uint64_t>::max() - 100;
    assert(Json(r, r.sampled_at_ms + 50).find("18446744073709551515") != std::string::npos);
    assert(Json(r, r.sampled_at_ms + 50).find("\"age_ms\":50") != std::string::npos);
    assert(Json({Error::Driver}, 10000).find("\"error\":\"driver_error\"") != std::string::npos);
    r = {Error::Driver};
    r.driver = {"rx_timeout", 263, 1234, 2, 1, 2000, true};
    auto diagnostic = Json(r, 5000);
    assert(diagnostic.find("\"last_failure\":\"rx_timeout\"") != std::string::npos);
    assert(diagnostic.find("\"error_code\":263") != std::string::npos);
    assert(diagnostic.find("\"restarts\":1") != std::string::npos);
    assert(diagnostic.find("\"recovering\":true") != std::string::npos);
    assert(diagnostic.find("\"distance_mm\":null") != std::string::npos);
    std::cout << "PASS: distance units, boundaries, no echo, noise, late echo, freshness, invalidation and 64-bit timestamps\n";
}
