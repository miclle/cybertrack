#ifndef CYBERTRACK_FRESHNESS_H
#define CYBERTRACK_FRESHNESS_H

#include <stdbool.h>
#include <stdint.h>

/* Authenticated origin metadata, bound to the complete command by the future
 * transport adapter. NEVER manufacture this evidence at message ingress.
 * intent is nonzero and globally stable for one intent across retries/sessions.
 * A new RPC ID, window or reconnect must not allocate a new intent. */
typedef struct {
    uint64_t session, enable_generation, window, intent;
} ct_action_proof;

/* Zero-initialize once per boot; never reset serial during reconnect/enable. */
typedef struct {
    uint64_t serial, session, enable_generation, issued_at_ms, expires_at_ms;
} ct_freshness;

typedef enum { CT_FRESH, CT_FRESH_MISSING, CT_FRESH_STALE, CT_FRESH_EXPIRED } ct_fresh_result;

/* Issue before the producer creates an intent, not on receive/retry. Replaces
 * the previous window. The producer echoes the challenge's three scope fields;
 * intent remains zero until a genuinely new intent is created. No wall clock,
 * heap, I/O or authentication. Zero budget and counter/time overflow fail. */
bool ct_freshness_issue(ct_freshness *f, uint64_t session, uint64_t enable_generation,
                        uint64_t now_ms, uint32_t budget_ms, ct_action_proof *challenge);
ct_fresh_result ct_freshness_check(const ct_freshness *f, ct_action_proof proof,
                                  uint64_t session, uint64_t enable_generation,
                                  uint64_t received_at_ms, uint64_t now_ms);
#endif
