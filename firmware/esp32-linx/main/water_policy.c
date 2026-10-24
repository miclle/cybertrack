#include "water_policy.h"
#include <string.h>

void water_stop(water_policy *s, uint64_t now)
{
    if (s->active) s->cooldown_until = now <= UINT64_MAX - WATER_COOLDOWN_MS ? now + WATER_COOLDOWN_MS : UINT64_MAX;
    s->active = false;
    s->armed = false;
    s->stopped = true;
    s->ends_at = 0;
    s->permit_until = 0;
}

void water_tick(water_policy *s, uint64_t now, bool online, bool boot_held)
{
    if (now < s->last_ms || now > UINT64_MAX - WATER_PERMIT_MS) {
        s->clock_fault = true;
        water_stop(s, now);
    }
    s->last_ms = now;
    s->online = online;
    if (boot_held && now <= UINT64_MAX - 30) s->release_after = now + 30;
    s->held = boot_held || now < s->release_after;
    if (s->held || !online) water_stop(s, now);
    if (s->armed && now >= s->permit_until) { s->armed = false; s->permit_until = 0; }
    if (s->active && now >= s->ends_at) {
        s->active = false;
        s->ends_at = 0;
        s->cooldown_until = now + WATER_COOLDOWN_MS;
    }
}

bool water_arm(water_policy *s, uint64_t now, const char token[WATER_TOKEN_LEN + 1])
{
    if (!token || strlen(token) != WATER_TOKEN_LEN) return false;
    for (unsigned i = 0; i < WATER_TOKEN_LEN; ++i)
        if (!((token[i] >= '0' && token[i] <= '9') || (token[i] >= 'a' && token[i] <= 'f'))) return false;
    if (s->clock_fault || !s->online || s->held || s->active || s->armed ||
        now < s->last_ms || now < s->cooldown_until || now > UINT64_MAX - WATER_PERMIT_MS ||
        !strcmp(token, s->token)) return false;
    memcpy(s->token, token, WATER_TOKEN_LEN + 1);
    s->armed = true; s->used = false; s->stopped = false;
    s->permit_until = now + WATER_PERMIT_MS;
    return true;
}

static const char *request(water_policy *s, uint64_t now, const char *token, uint32_t duration, bool timed)
{
    if (s->clock_fault || now < s->last_ms) return "clock_fault";
    if (!s->online || s->held) return "not_ready";
    if (!token || strcmp(token, s->token)) return "invalid_permit";
    if (s->used) return "permit_used";
    if (!s->armed || now >= s->permit_until) return "permit_expired_or_revoked";
    if (!timed && duration != WATER_MS) return "duration_must_match_5000ms_intent";
    if (timed && (duration == 0 || duration > WATER_MAX_TIMED_MS)) return "duration_out_of_range";
    if (now > UINT64_MAX - duration) return "clock_fault";
    if (s->active || now < s->cooldown_until) return "busy";
    /* Consume before requesting a high output. No retry can extend this deadline. */
    s->used = true; s->armed = false; s->permit_until = 0;
    s->ends_at = now + duration;
    s->active = true;
    ++s->starts;
    return "accepted";
}

const char *water_request(water_policy *s, uint64_t now, const char *token, uint32_t duration)
{
    return request(s, now, token, duration, false);
}

const char *water_request_timed(water_policy *s, uint64_t now, const char *token, uint32_t duration)
{
    return request(s, now, token, duration, true);
}
