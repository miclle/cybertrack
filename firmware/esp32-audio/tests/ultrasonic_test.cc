// Exercise the actual ESP-IDF adapter with deterministic peripheral events.
#include "../ultrasonic.cc"
#include <iostream>
void Reset() {
    mock::us = 0; mock::fail.clear(); mock::initially_high = mock::final_high = false;
    mock::captured = mock::enabled = mock::deleted = false;
    mock::task_ok = mock::completion = true;
    mock::triggers = mock::pulses = mock::delays = mock::reads = 0; mock::cycles = 1;
    mock::trig_level = 0;
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
    assert(mock::us >= 200000);
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
    for (const auto failure : {"gpio_config", "new_rx", "pull", "callback", "enable", "receive", "trig_high", "trig_low"}) {
        Reset(); mock::fail = failure; Run();
        assert(CyberTrackDistanceSnapshot().error == ultrasonic::Error::Driver);
        assert(!mock::enabled && mock::trig_level == 0);
    }
    Reset(); mock::task_ok = false; Run();
    assert(CyberTrackDistanceSnapshot().error == ultrasonic::Error::Driver);
    std::cout << "PASS: actual distance adapter capture, missing/stuck/noisy echo, bounded waits, driver cleanup and task allocation failure\n";
}
