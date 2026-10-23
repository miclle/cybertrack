#ifndef CT_TEST_FAKE_STORE_H
#define CT_TEST_FAKE_STORE_H
#include "cybertrack/replay_store.h"

typedef struct {
    unsigned char durable[2][CT_REPLAY_SLOT_BYTES];
    unsigned char pending[2][CT_REPLAY_SLOT_BYTES];
    size_t calls, fail_at, cut_bytes;
    bool persist_partial;
} ct_test_store;
void ct_test_store_blank(ct_test_store *s);
void ct_test_store_power_cut(ct_test_store *s);
ct_replay_io ct_test_store_io(ct_test_store *s);
#endif
