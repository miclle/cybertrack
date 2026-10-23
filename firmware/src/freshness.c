#include "cybertrack/freshness.h"

bool ct_freshness_issue(ct_freshness *f, uint64_t session, uint64_t enable,
                        uint64_t now, uint32_t budget, ct_action_proof *out)
{
    if (out) *out = (ct_action_proof){0};
    if (!f || !out || !session || !budget || f->serial == UINT64_MAX ||
        now > UINT64_MAX - budget || (f->serial && now < f->issued_at_ms)) return false;
    ++f->serial;
    f->session = session;
    f->enable_generation = enable;
    f->issued_at_ms = now;
    f->expires_at_ms = now + budget;
    *out = (ct_action_proof){session, enable, f->serial, 0};
    return true;
}

ct_fresh_result ct_freshness_check(const ct_freshness *f, ct_action_proof p,
                                  uint64_t session, uint64_t enable,
                                  uint64_t received, uint64_t now)
{
    if (!f || !p.intent || !p.window || !p.session || !f->serial) return CT_FRESH_MISSING;
    if (!session || p.session != session || p.enable_generation != enable ||
        p.session != f->session || p.enable_generation != f->enable_generation ||
        p.window != f->serial) return CT_FRESH_STALE;
    if (received < f->issued_at_ms || received > now || now < f->issued_at_ms ||
        now >= f->expires_at_ms) return CT_FRESH_EXPIRED;
    return CT_FRESH;
}
