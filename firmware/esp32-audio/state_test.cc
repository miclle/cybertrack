#include "cybertrack_state.h"
#include <cassert>
#include <iostream>
int main() {
    CyberTrackAudioState state(10);
    auto first = state.Call(false, 20, "30:ed:a0:a1:97:7c", "0123456789abcdef");
    assert(first.find("\"state\":\"DISARMED\"") != std::string::npos);
    assert(first.find("\"request_sequence\":1") != std::string::npos);
    auto stopped = state.Call(true, 30, "30:ed:a0:a1:97:7c", "0123456789abcdef");
    assert(stopped.find("\"fault\":\"stopped\"") != std::string::npos);
    assert(stopped.find("\"state\":\"FAULT\"") != std::string::npos);
    auto queried = state.Call(false, 40, "30:ed:a0:a1:97:7c", "0123456789abcdef");
    assert(queried.find("\"fault\":\"stopped\"") != std::string::npos);
    auto repeated = state.Call(true, 50, "30:ed:a0:a1:97:7c", "0123456789abcdef");
    assert(repeated.find("\"request_sequence\":4") != std::string::npos);
    for (auto result : {first, stopped, queried, repeated}) {
        assert(result.find("\"capabilities\":{\"move\":false,\"water\":false,\"bubbles\":false}") != std::string::npos);
        assert(result.find("\"physical_feedback\":false") != std::string::npos);
        assert(result.find("\"actuator_backend\":\"not_installed\"") != std::string::npos);
    }
    CyberTrackAudioState clock(100);
    assert(clock.Call(false, 99, "device", "boot").find("\"fault\":\"clock_fault\"") != std::string::npos);
    CyberTrackAudioState wide(0);
    assert(wide.Call(false, UINT64_MAX, "device", "boot").find("\"uptime_ms\":18446744073709551615") != std::string::npos);
    std::cout << "PASS: no-actuator state, stop latch, repeat stop, sequence, clock fault\n";
}
