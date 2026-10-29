// Exercise the actual ESP-IDF adapter with deterministic peripheral events.
#include "../ultrasonic.cc"
#include <iostream>
void Reset() {
    mock::us = 0; mock::fail.clear(); mock::initially_high = mock::final_high = false;
    mock::captured = mock::enabled = mock::deleted = false;
    mock::task_ok = mock::completion = true;
    mock::triggers = mock::pulses = mock::delays = mock::reads = 0; mock::cycles = 1;
    mock::trig_level = 0;
    mock::fail_remaining = -1; mock::timeout_remaining = 0;
    mock::allocations = mock::deletions = mock::live_channels = mock::resets = 0;
    mock::late_completion = false; mock::on_delay = {};
    mock::delay_values.clear(); mock::trigger_times.clear();
    mock::frame = {{200, 0, 5831, 1}, {25000, 0, 0, 0}};
    Publish({});
}
void Run() {
    InitializeCyberTrackUltrasonic();
    if (mock::task_ok) try { mock::task(nullptr); } catch (const mock::Done&) {}
}
int main() {
    Reset(); Run();
    auto r = CyberTrackDistanceSnapshot();
    assert(r.error == ultrasonic::Error::None && r.distance_mm == 1000);
    assert(mock::triggers == 1 && mock::pulses == 1 && mock::trig_level == 0);
    assert(mock::trigger_times.front() >= 1000000);
    Reset(); mock::frame = {{25000, 0, 0, 0}}; Run();
    assert(CyberTrackDistanceSnapshot().error == ultrasonic::Error::NoEcho);
    Reset(); mock::initially_high = true; Run();
    assert(CyberTrackDistanceSnapshot().error == ultrasonic::Error::EchoHigh && mock::triggers == 0);
    Reset(); mock::final_high = true; Run();
    assert(CyberTrackDistanceSnapshot().error == ultrasonic::Error::EchoHigh);
    Reset(); mock::frame = {{100, 0, 100, 1}, {10, 0, 100, 1}, {25000, 0, 0, 0}}; Run();
    assert(CyberTrackDistanceSnapshot().error == ultrasonic::Error::InvalidEcho);
    Reset(); mock::frame = {{100, 0, 25000, 1}, {25000, 0, 0, 0}}; Run();
    assert(CyberTrackDistanceSnapshot().error == ultrasonic::Error::OutOfRange);
    Reset(); mock::completion = false; Run();
    assert(CyberTrackDistanceSnapshot().error == ultrasonic::Error::Driver);
    assert(!mock::enabled && mock::deleted && mock::trig_level == 0);
    assert(CyberTrackDistanceSnapshot().driver.recovering);
    assert(!std::strcmp(CyberTrackDistanceSnapshot().driver.last_failure,"rx_timeout"));
    assert(CyberTrackDistanceSnapshot().driver.error_code == ESP_ERR_TIMEOUT);
    for (const auto failure : {"gpio_config", "new_rx", "pull", "callback", "enable", "receive", "trig_high", "trig_low"}) {
        Reset(); mock::fail = failure; Run();
        assert(CyberTrackDistanceSnapshot().error == ultrasonic::Error::Driver);
        assert(!mock::enabled && mock::trig_level == 0);
    }
    Reset(); mock::task_ok = false; Run();
    assert(CyberTrackDistanceSnapshot().error == ultrasonic::Error::Driver);
    assert(!std::strcmp(CyberTrackDistanceSnapshot().driver.last_failure,"task_create"));
    // Every transient setup/capture failure recovers, with at most one live channel.
    for (const auto failure : {"gpio_config", "new_rx", "pull", "callback", "enable", "receive", "trig_high", "trig_low"}) {
        Reset(); mock::fail = failure; mock::fail_remaining = 1; mock::cycles = 2; Run();
        r = CyberTrackDistanceSnapshot();
        assert(r.error == ultrasonic::Error::None && r.distance_mm == 1000);
        assert(r.driver.failures == 1 && r.driver.restarts == 1 && !r.driver.recovering);
        assert(mock::live_channels == 1 && mock::resets == 1);
    }
    Reset(); mock::timeout_remaining = 1; mock::late_completion = true; mock::cycles = 2; Run();
    r = CyberTrackDistanceSnapshot();
    assert(r.error == ultrasonic::Error::None && r.distance_mm == 1000);
    assert(r.driver.restarts == 1 && r.driver.failures == 1 && !r.driver.recovering);
    assert(!std::strcmp(r.driver.last_failure,"rx_timeout"));
    assert(mock::allocations == 2 && mock::deletions == 1 && mock::resets == 1);
    assert(mock::trigger_times[1] - mock::trigger_times[0] >= 1000000);
    // Persisting failures stay invalid and retry at 1/2/4/8 seconds, never spin.
    Reset(); mock::completion = false; mock::cycles = 6; Run();
    const std::vector<unsigned> waits{1000,1000,2000,4000,8000,8000,8000};
    assert(mock::delay_values == waits && mock::live_channels == 0);
    assert(CyberTrackDistanceSnapshot().driver.restarts == 5);
    // A failed cleanup cannot free/reuse an active buffer or allocate another receiver.
    for (const auto failure : {"disable","delete"}) {
        Reset(); mock::completion = false; mock::fail = failure; mock::cycles = 4; Run();
        r = CyberTrackDistanceSnapshot();
        assert(r.error == ultrasonic::Error::Driver && !r.driver.recovering && !r.driver.retry_delay_ms);
        assert(mock::allocations == 1 && mock::resets == 0 && r.driver.restarts == 0);
    }
    // Good readings are invalidated during recovery; only a new capture restores them.
    Reset(); mock::cycles = 2;
    mock::on_delay = [](unsigned ms) {
        if (ms < 1000) { assert(CyberTrackDistanceSnapshot().error == ultrasonic::Error::None); mock::completion = false; }
        else if (mock::triggers) assert(CyberTrackDistanceSnapshot().error == ultrasonic::Error::Driver);
    };
    Run(); assert(CyberTrackDistanceSnapshot().error == ultrasonic::Error::Driver);
    std::cout << "PASS: cold-start allowance, transient recovery, backoff, late callback discard, cleanup failure latch and detailed diagnostics\n";
    std::cout << "PASS: actual distance adapter capture, missing/stuck/noisy echo, bounded waits, driver cleanup and task allocation failure\n";
}
