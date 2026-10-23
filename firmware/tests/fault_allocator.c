#include "fault_allocator.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(EXIT_FAILURE); } } while (0)
#define BLOCKS 32

static size_t block_index(const ct_test_heap *h, void *ptr)
{
    for (size_t i = 0; i < BLOCKS; ++i) if (h->blocks[i].ptr == ptr) return i;
    CHECK(false); /* Unknown pointer, double free or ledger exhaustion. */
    return 0;
}

static bool fail(ct_test_heap *h)
{
    ++h->calls;
    if (h->fail_at && (h->calls == h->fail_at || (h->persistent && h->calls > h->fail_at))) {
        ++h->failures;
        return true;
    }
    return false;
}

static void account(ct_test_heap *h, size_t size)
{
    h->live_bytes += size;
    if (h->live_bytes > h->peak_bytes) h->peak_bytes = h->live_bytes;
}

static void *allocate(void *context, size_t size)
{
    ct_test_heap *h = context;
    ++h->allocations;
    CHECK(size > 0);
    if (fail(h)) return NULL;
    size_t i = block_index(h, NULL);
    void *ptr = malloc(size);
    CHECK(ptr != NULL);
    h->blocks[i].ptr = ptr;
    h->blocks[i].size = size;
    ++h->live_blocks;
    account(h, size);
    return ptr;
}

static void *resize(void *context, void *ptr, size_t old_size, size_t size)
{
    ct_test_heap *h = context;
    ++h->resizes;
    CHECK(ptr != NULL && size > 0);
    size_t i = block_index(h, ptr);
    CHECK(h->blocks[i].size == old_size);
    if (fail(h)) {
        ++h->resize_failures;
        return NULL; /* Do not free or mutate the original block. */
    }
    void *resized = realloc(ptr, size);
    CHECK(resized != NULL);
    h->live_bytes -= old_size;
    h->blocks[i].ptr = resized;
    h->blocks[i].size = size;
    account(h, size);
    return resized;
}

static void release(void *context, void *ptr)
{
    ct_test_heap *h = context;
    if (!ptr) return;
    size_t i = block_index(h, ptr);
    h->live_bytes -= h->blocks[i].size;
    --h->live_blocks;
    h->blocks[i].ptr = NULL;
    h->blocks[i].size = 0;
    free(ptr);
}

ct_rpc_allocator ct_test_allocator(ct_test_heap *heap)
{
    return (ct_rpc_allocator){allocate, resize, release, heap};
}

void ct_test_heap_empty(const ct_test_heap *heap)
{
    CHECK(heap->live_blocks == 0 && heap->live_bytes == 0);
    for (size_t i = 0; i < BLOCKS; ++i) CHECK(heap->blocks[i].ptr == NULL);
}

void ct_test_heap_reset(ct_test_heap *heap, size_t fail_at, bool persistent)
{
    ct_test_heap_empty(heap);
    memset(heap, 0, sizeof(*heap));
    heap->fail_at = fail_at;
    heap->persistent = persistent;
}
