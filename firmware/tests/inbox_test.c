#include "cybertrack/inbox.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(EXIT_FAILURE); } } while (0)
static ct_inbox inbox;
static ct_inbox_item item;
static ct_rpc_delivery delivery = {1, 123, 7, false};

static void init(void)
{
    ct_inbox_init(&inbox);
    CHECK(ct_inbox_bind(&inbox, 1));
}

static void copy_fifo_and_wrap(void)
{
    init();
    for (unsigned round = 0; round < 100; ++round) {
        for (unsigned i = 0; i < CT_INBOX_SLOTS; ++i) {
            char frame[] = {'a' + (char)i, '\0', 'z'};
            CHECK(ct_inbox_push(&inbox, frame, sizeof(frame), delivery) == CT_INBOX_OK);
            frame[0] = 'X'; /* Caller buffer may immediately be reused. */
        }
        for (unsigned i = 0; i < CT_INBOX_SLOTS; ++i) {
            CHECK(ct_inbox_take(&inbox, &item) == CT_EVENT_MESSAGE);
            CHECK(item.length == 3 && item.frame[0] == 'a' + (char)i);
            CHECK(item.frame[1] == '\0' && item.frame[2] == 'z' && item.frame[3] == '\0');
            CHECK(item.delivery.session == 1 && item.delivery.received_at_ms == 123);
            CHECK(item.delivery.enable_generation == 7 && !item.delivery.freshness_verified);
        }
        CHECK(ct_inbox_take(&inbox, &item) == CT_EVENT_IDLE);
        /* Advance head by one to exercise every ring boundary. */
        CHECK(ct_inbox_push(&inbox, "x", 1, delivery) == CT_INBOX_OK);
        CHECK(ct_inbox_take(&inbox, &item) == CT_EVENT_MESSAGE);
    }
}

static void overflow_disconnect_and_reconnect(void)
{
    init();
    for (unsigned i = 0; i < CT_INBOX_SLOTS; ++i)
        CHECK(ct_inbox_push(&inbox, "{}", 2, delivery) == CT_INBOX_OK);
    CHECK(ct_inbox_push(&inbox, "stop", 4, delivery) == CT_INBOX_OVERFLOW);
    CHECK(inbox.count == 0 && inbox.session == 0);
    CHECK(!ct_inbox_bind(&inbox, 2));
    CHECK(ct_inbox_push(&inbox, "x", 1, delivery) == CT_INBOX_STALE);
    CHECK(ct_inbox_take(&inbox, &item) == CT_EVENT_DISCONNECT);
    CHECK(ct_inbox_take(&inbox, &item) == CT_EVENT_IDLE);
    CHECK(!ct_inbox_bind(&inbox, 1));
    CHECK(ct_inbox_bind(&inbox, 2));
    ct_inbox_disconnect(&inbox, 1); /* Late old disconnect cannot close session 2. */
    CHECK(inbox.session == 2);
    CHECK(ct_inbox_push(&inbox, NULL, SIZE_MAX, delivery) == CT_INBOX_STALE);
    CHECK(!inbox.disconnect_pending);
    CHECK(!ct_inbox_bind(&inbox, 3));
}

static void disconnect_priority(void)
{
    init();
    CHECK(ct_inbox_push(&inbox, "action", 6, delivery) == CT_INBOX_OK);
    ct_inbox_disconnect(&inbox, 1);
    ct_inbox_disconnect(&inbox, 1);
    CHECK(ct_inbox_take(&inbox, &item) == CT_EVENT_DISCONNECT);
    CHECK(ct_inbox_take(&inbox, &item) == CT_EVENT_IDLE);
    CHECK(item.length == 0 && item.frame[0] == '\0');
}

static void frame_bounds_and_invalid_arguments(void)
{
    char frame[CT_RPC_FRAME_MAX];
    memset(frame, 'x', sizeof(frame));
    init();
    CHECK(ct_inbox_push(&inbox, frame, sizeof(frame), delivery) == CT_INBOX_OK);
    CHECK(ct_inbox_take(&inbox, &item) == CT_EVENT_MESSAGE);
    CHECK(item.length == sizeof(frame) && !memcmp(frame, item.frame, sizeof(frame)));
    CHECK(item.frame[sizeof(frame)] == '\0');
    CHECK(ct_inbox_push(&inbox, frame, SIZE_MAX, delivery) == CT_INBOX_OVERSIZE);
    CHECK(ct_inbox_take(&inbox, &item) == CT_EVENT_DISCONNECT);
    init();
    CHECK(ct_inbox_push(&inbox, NULL, 0, delivery) == CT_INBOX_INVALID);
    CHECK(ct_inbox_take(&inbox, &item) == CT_EVENT_DISCONNECT);
    init();
    CHECK(ct_inbox_push(&inbox, "", 0, delivery) == CT_INBOX_OK);
    CHECK(ct_inbox_take(&inbox, &item) == CT_EVENT_MESSAGE && item.length == 0);
    CHECK(ct_inbox_push(NULL, "", 0, delivery) == CT_INBOX_INVALID);
    CHECK(!ct_inbox_bind(NULL, 1) && !ct_inbox_bind(&inbox, 0));
    CHECK(ct_inbox_take(&inbox, NULL) == CT_EVENT_IDLE);
    CHECK(ct_inbox_take(NULL, &item) == CT_EVENT_IDLE);
    CHECK(item.kind == CT_EVENT_IDLE && item.length == 0 && item.frame[0] == '\0');
}

int main(void)
{
    copy_fifo_and_wrap();
    overflow_disconnect_and_reconnect();
    disconnect_priority();
    frame_bounds_and_invalid_arguments();
    printf("PASS: 4 inbox scenario groups; inbox=%zu bytes, item=%zu bytes\n", sizeof(inbox), sizeof(item));
    return EXIT_SUCCESS;
}
