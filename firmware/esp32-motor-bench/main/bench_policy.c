#include "bench_policy.h"

void bench_stop(bench_policy *state, uint64_t now)
{
    if (state->active) state->cooldown_until_ms = now + BENCH_COOLDOWN_MS;
    state->active = false;
    state->armed = false;
    state->deadline_ms = 0;
}

void bench_tick(bench_policy *state, uint64_t now, bool stop_held)
{
    if (now < state->last_ms || now > UINT64_MAX - BENCH_ARM_MS ||
        now > UINT64_MAX - BENCH_PULSE_MS || now > UINT64_MAX - BENCH_COOLDOWN_MS) {
        bench_stop(state, 0);
        state->cooldown_until_ms = UINT64_MAX;
    } else if (stop_held || ((state->active || state->armed) && now >= state->deadline_ms)) {
        bench_stop(state, now);
    }
    state->last_ms = now;
}

void bench_receive(bench_policy *state, uint64_t now, bool stop_held,
                   const unsigned char *bytes, size_t count)
{
    bench_tick(state, now, stop_held);
    unsigned char key = 0;
    size_t keys = 0;
    for (size_t i = 0; i < count; ++i) {
        if (bytes[i] != '\r' && bytes[i] != '\n') {
            key = bytes[i];
            ++keys;
        }
    }
    if (keys == 0) return;
    if (stop_held || keys != 1 || state->active || now < state->cooldown_until_ms) {
        bench_stop(state, now);
        return;
    }
    if (key >= '1' && key <= '3') {
        bench_stop(state, now);
        state->channels = key - '0';
    } else if (key == 'a' && state->channels != 0) {
        state->armed = true;
        state->deadline_ms = now + BENCH_ARM_MS;
    } else if (state->armed && ((key == 'f' || key == 'r') ||
               ((key == 'x' || key == 'y') && state->channels == BENCH_CHANNEL_BOTH))) {
        state->armed = false;
        state->reverse = key == 'r' || key == 'y';
        state->reverse_b = key == 'r' || key == 'x';
        state->active = true;
        state->deadline_ms = now + BENCH_PULSE_MS;
    } else {
        bench_stop(state, now);
    }
}
