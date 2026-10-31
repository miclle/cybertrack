#include <cstdlib>
#include <new>
static bool fail_next_allocation = false;
void* operator new(std::size_t size) {
    if (fail_next_allocation) {
        fail_next_allocation = false;
        throw std::bad_alloc();
    }
    if (void* memory = std::malloc(size ? size : 1)) return memory;
    throw std::bad_alloc();
}
void operator delete(void* memory) noexcept { std::free(memory); }
void operator delete(void* memory, std::size_t) noexcept { std::free(memory); }

#include "receipt_host.h"
#include <iostream>

int main() {
    sessions.WifiLink(clock_ms, true);
    sessions.VoiceLink(clock_ms, true);
    sessions.Tick(clock_ms, false);
    ActionPlan plan;
    plan.count = 2;
    plan.steps[0] = {"forward", 30000, 30000, 30000, 1000, 100};
    plan.steps[1] = {"backward", 1000, 0, 0, 0, 100};
    int ticket = sessions.VoiceClaim(clock_ms, 1, AudioActionGuard::PlanMode);
    Reply("sequence", ticket, 0, nullptr, 0, 0, nullptr, &plan);
    assert(guard.Moving() && guard.Watering() && guard.Bubbling() && guard.Igniting());
    fail_next_allocation = true;
    bool failed = false;
    try {
        Reply("stop");
    } catch (const std::bad_alloc&) {
        failed = true;
    }
    assert(failed && !fail_next_allocation);
    assert(!guard.Moving() && !guard.Watering() && !guard.Bubbling() && !guard.Igniting());
    assert(!sessions.plan_active);
    clock_ms += 60000;
    sessions.Tick(clock_ms, false);
    assert(!guard.Moving() && !guard.Watering() && !guard.Bubbling() && !guard.Igniting());
    ticket = sessions.VoiceClaim(clock_ms, 2, AudioActionGuard::MoveOnly);
    Reply("move", ticket, 30000, "forward");
    assert(guard.Moving());
    auto* expired = cJSON_Parse(Reply("stop", 0, 0, nullptr, 0, 123).c_str());
    assert(expired && !std::strcmp(cJSON_GetObjectItemCaseSensitive(expired, "result")->valuestring, "session_expired"));
    assert(guard.Moving()); // An invalid web session must not gain the MCP stop path.
    cJSON_Delete(expired);
    Reply("stop");
    assert(!guard.Moving());
    std::cout << "PASS: receipt allocation failure leaves all lanes and later steps stopped\n";
}
