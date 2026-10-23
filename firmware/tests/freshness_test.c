#include "cybertrack/freshness.h"
#include <stdio.h>
#include <stdlib.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%d: %s\n", __LINE__, #x); exit(1); } } while (0)
int main(void)
{
    ct_freshness f = {0}; ct_action_proof p;
    CHECK(ct_freshness_issue(&f, 1, 2, 100, 50, &p));
    CHECK(ct_freshness_check(&f, p, 1, 2, 100, 100) == CT_FRESH_MISSING);
    p.intent = 1;
    CHECK(ct_freshness_check(&f, p, 1, 2, 100, 149) == CT_FRESH);
    CHECK(ct_freshness_check(&f, p, 1, 2, 100, 150) == CT_FRESH_EXPIRED);
    CHECK(ct_freshness_check(&f, p, 1, 2, 151, 151) == CT_FRESH_EXPIRED);
    CHECK(ct_freshness_check(&f, p, 1, 2, 99, 100) == CT_FRESH_EXPIRED);
    CHECK(ct_freshness_check(&f, p, 1, 2, 101, 100) == CT_FRESH_EXPIRED);
    CHECK(ct_freshness_check(&f, p, 2, 2, 100, 100) == CT_FRESH_STALE);
    CHECK(ct_freshness_check(&f, p, 1, 3, 100, 100) == CT_FRESH_STALE);
    CHECK(ct_freshness_check(&f, p, 0, 2, 100, 100) == CT_FRESH_STALE);
    ct_action_proof next;
    CHECK(ct_freshness_issue(&f, 1, 2, 120, 50, &next));
    CHECK(ct_freshness_check(&f, p, 1, 2, 120, 120) == CT_FRESH_STALE);
    CHECK(!ct_freshness_issue(&f, 1, 2, 119, 50, &next));
    CHECK(!next.window && f.serial == 2);
    CHECK(!ct_freshness_issue(&f, 1, 2, UINT64_MAX, 1, &next));
    CHECK(!ct_freshness_issue(&f, 1, 2, 120, 0, &next));
    CHECK(!ct_freshness_issue(&f, 0, 2, 120, 50, &next));
    f.serial = UINT64_MAX;
    CHECK(!ct_freshness_issue(&f, 1, 2, 120, 50, &next));
    CHECK(!ct_freshness_issue(NULL, 1, 2, 120, 50, &next));
    CHECK(!ct_freshness_issue(&f, 1, 2, 120, 50, NULL));
    puts("freshness: window boundaries, scope changes and exhaustion passed");
    return 0;
}
