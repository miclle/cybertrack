#ifndef CT_TEST_FAKE_ANCHOR_H
#define CT_TEST_FAKE_ANCHOR_H
#include "cybertrack/replay_store.h"
typedef struct {
    ct_replay_anchor_record durable;
    size_t calls, fail_at, replacements;
    bool commit_on_failure;
} ct_test_anchor;
ct_replay_anchor_io ct_test_anchor_io(ct_test_anchor *a);
void ct_test_anchor_power_cut(ct_test_anchor *a);
#endif
