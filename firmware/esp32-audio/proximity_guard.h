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
            near_samples_ = 0;
            return None; // Missing data never clears an existing movement lock.
        }
        // Count sensor samples, not the 5 ms control ticks reusing a snapshot.
        // Only ordinary audio waits for confirmation; protection below stays immediate.
        if (r.distance_mm >= 500) {
            near_samples_ = 0;
        } else if (!near_samples_ || r.sampled_at_ms != last_near_sample_) {
            if (r.sampled_at_ms < last_near_sample_ ||
                r.sampled_at_ms - last_near_sample_ > ultrasonic::FreshnessMs)
                near_samples_ = 0;
            if (near_samples_ < 3) ++near_samples_;
            last_near_sample_ = r.sampled_at_ms;
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
        if (near_samples_ < 3) return None;
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
    unsigned near_samples_ = 0;
    uint64_t last_near_sample_ = 0;
    bool beep_started_ = false;
    uint64_t last_beep_ = 0;
};
