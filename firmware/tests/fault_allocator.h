#ifndef CYBERTRACK_TEST_FAULT_ALLOCATOR_H
#define CYBERTRACK_TEST_FAULT_ALLOCATOR_H

#include "cybertrack/protocol.h"

/* Test-only ledger: checks each allocation's ownership/size, including failed
 * resize retaining its original block. No global malloc interposition. */
typedef struct {
    struct { void *ptr; size_t size; } blocks[32];
    size_t calls, allocations, resizes, failures, resize_failures;
    size_t live_blocks, live_bytes, peak_bytes;
    size_t fail_at;
    bool persistent;
} ct_test_heap;

ct_rpc_allocator ct_test_allocator(ct_test_heap *heap);
/* Requires no outstanding blocks. fail_at=0 disables failure injection. */
void ct_test_heap_reset(ct_test_heap *heap, size_t fail_at, bool persistent);
void ct_test_heap_empty(const ct_test_heap *heap);

#endif
