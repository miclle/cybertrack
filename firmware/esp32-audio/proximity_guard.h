#pragma once
#include "distance_reading.h"

// Raw fresh readings control protection; audio scheduling never delays stopping.
class ProximityGuard {
public:
    enum Alert { None, Beep, Stop };
    bool blocked = false;
    bool beeping = false;
    Alert Update(const ultrasonic::Reading& r, uint64_t now, bool forward, bool auto_stop) {
        if (!auto_stop) blocked = false;
        beeping = false;
        if (!r.sampled || r.error != ultrasonic::Error::None || now < r.sampled_at_ms ||
            now - r.sampled_at_ms > ultrasonic::FreshnessMs ||
            r.distance_mm < ultrasonic::MinDistanceMm || r.distance_mm > ultrasonic::MaxDistanceMm) {
            return None; // Missing data never clears an existing movement lock.
        }
        if (r.distance_mm >= 200) blocked = false;
        if (auto_stop && r.distance_mm < 150) {
            const bool newly_blocked = !blocked;
            blocked = true;
            if (forward && newly_blocked) {
                // The stop triplet takes this cadence slot; ordinary range beeps continue after it.
                beep_started_ = true;
                last_beep_ = now;
                return Stop;
            }
        }
        if (r.distance_mm >= 500) return None;
        beeping = true;
        const uint64_t interval = r.distance_mm < 400 ? 400 : 800;
        // Re-evaluate cadence without restarting it at a distance-band crossing.
        // One delayed tick emits at most one beep, never a catch-up burst.
        if (!beep_started_ || now < last_beep_ || now - last_beep_ >= interval) {
            beep_started_ = true;
            last_beep_ = now;
            return Beep;
        }
        return None;
    }
private:
    bool beep_started_ = false;
    uint64_t last_beep_ = 0;
};
