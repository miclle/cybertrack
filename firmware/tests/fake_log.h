#ifndef CT_TEST_FAKE_LOG_H
#define CT_TEST_FAKE_LOG_H
#include "cybertrack/replay_log.h"

typedef struct {
    unsigned char durable[CT_REPLAY_LOG_REDUNDANT_SLOTS][CT_REPLAY_LOG_SLOT_BYTES];
    unsigned char pending[CT_REPLAY_LOG_REDUNDANT_SLOTS][CT_REPLAY_LOG_SLOT_BYTES];
    unsigned slots, unreadable_mask;
    size_t calls, fail_at, cut_bytes;
    bool persist_partial;
} ct_test_log;
void ct_test_log_blank(ct_test_log *s);
void ct_test_log_blank_redundant(ct_test_log *s);
void ct_test_log_power_cut(ct_test_log *s);
ct_replay_io ct_test_log_io(ct_test_log *s);
#endif
