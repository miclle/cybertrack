#ifndef CT_TEST_SYNTHETIC_PROOF_H
#define CT_TEST_SYNTHETIC_PROOF_H
/* Regression fixtures ONLY: model a producer obtaining a window before a new
 * command. Never use this receive-time shortcut in a real transport. Dedicated
 * freshness integration tests preserve real creation-time proof across delays. */
#include "cybertrack/protocol.h"
static inline ct_rpc_delivery ct_test_delivery(ct_protocol *p, uint64_t session,
    uint64_t received, uint64_t enable, bool fresh)
{
    static uint64_t next_intent;
    ct_action_proof proof = {0};
    if (fresh) {
        ct_freshness *f = &p->freshness;
        if (!f->serial || f->session != p->session || f->enable_generation != p->control->enable_generation ||
            received >= f->expires_at_ms) {
            (void)ct_protocol_issue_window(p, received, &proof);
        } else proof = (ct_action_proof){f->session, f->enable_generation, f->serial, 0};
        proof.intent = ++next_intent;
    }
    return (ct_rpc_delivery){session, received, enable, proof};
}
#endif
