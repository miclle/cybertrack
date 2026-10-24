#ifndef LINX_WATER_POLICY_H
#define LINX_WATER_POLICY_H
#include <stdbool.h>
#include <stdint.h>
#define WATER_MS 5000u
#define WATER_MAX_TIMED_MS 30000u
#define WATER_PERMIT_MS 30000u
#define WATER_COOLDOWN_MS 1000u
#define WATER_TOKEN_LEN 32u
/* A locally created, single-use bench intent. It is never restored after boot. */
typedef struct {
    bool armed, active, used, stopped, online, held, clock_fault;
    uint64_t last_ms, permit_until, ends_at, cooldown_until, release_after;
    char token[WATER_TOKEN_LEN + 1];
    unsigned starts;
} water_policy;
void water_tick(water_policy *s, uint64_t now, bool online, bool boot_held);
void water_stop(water_policy *s, uint64_t now);
bool water_arm(water_policy *s, uint64_t now, const char token[WATER_TOKEN_LEN + 1]);
const char *water_request(water_policy *s, uint64_t now, const char *token, uint32_t duration);
/* Variable-duration audio-board entry; the original water_request stays fixed at 5 s. */
const char *water_request_timed(water_policy *s, uint64_t now, const char *token, uint32_t duration);
#endif
