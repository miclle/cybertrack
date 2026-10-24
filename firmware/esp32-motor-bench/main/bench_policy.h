#ifndef BENCH_POLICY_H
#define BENCH_POLICY_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

enum { BENCH_ARM_MS = 3000, BENCH_PULSE_MS = 10000, BENCH_COOLDOWN_MS = 1000 };
typedef struct {
    bool armed;
    bool active;
    bool reverse;
    uint64_t last_ms;
    uint64_t deadline_ms;
    uint64_t cooldown_until_ms;
} bench_policy;

void bench_stop(bench_policy *state, uint64_t now);
void bench_tick(bench_policy *state, uint64_t now, bool stop_held);
/* One local key per read. Bursts, unknown keys and input while running stop/disarm. */
void bench_receive(bench_policy *state, uint64_t now, bool stop_held,
                   const unsigned char *bytes, size_t count);
#endif
