#ifndef CT_TEST_FAKE_LOG_H
#define CT_TEST_FAKE_LOG_H
#include "cybertrack/replay_log.h"

typedef struct {
    unsigned char durable[2][CT_REPLAY_LOG_SLOT_BYTES];
    unsigned char pending[2][CT_REPLAY_LOG_SLOT_BYTES];
    size_t calls, fail_at, cut_bytes;
    bool persist_partial;
} ct_test_log;
void ct_test_log_blank(ct_test_log *s);
void ct_test_log_power_cut(ct_test_log *s);
ct_replay_io ct_test_log_io(ct_test_log *s);
#endif
