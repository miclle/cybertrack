#pragma once
#include "distance_reading.h"

// Raw fresh readings control protection; UI smoothing never delays stopping.
class ProximityGuard {
public:
    enum Alert { None, Caution, Stop };
    bool blocked = false;
    Alert Update(const ultrasonic::Reading& r, uint64_t now) {
        if (!r.sampled || r.error != ultrasonic::Error::None || now < r.sampled_at_ms ||
            now - r.sampled_at_ms > ultrasonic::FreshnessMs ||
            r.distance_mm < ultrasonic::MinDistanceMm || r.distance_mm > ultrasonic::MaxDistanceMm) return None;
        if (r.distance_mm >= 350) blocked = false;
        if (r.distance_mm >= 550) warned_ = false;
        if (r.distance_mm < 300) {
            const bool entered = !blocked;
            blocked = true; warned_ = true;
            if (entered && (!stop_announced_ || now - last_stop_ >= 5000)) {
                stop_announced_ = true; last_stop_ = now; return Stop;
            }
        } else if (r.distance_mm < 500 && !warned_) {
            warned_ = true;
            if (!caution_announced_ || now - last_caution_ >= 5000) {
                caution_announced_ = true; last_caution_ = now; return Caution;
            }
        }
        return None;
    }
private:
    bool warned_ = false, stop_announced_ = false, caution_announced_ = false;
    uint64_t last_stop_ = 0, last_caution_ = 0;
};
