#include "recent_command.h"
#include <cassert>
#include <cstdio>
int main() {
    RecentCommand receipt;
    assert(!receipt.valid);
    receipt.Record(10, "get_status", "ok", true);
    assert(!receipt.valid);
    char operation[] = "move", outcome[] = "not_ready_or_busy";
    receipt.Record(20, operation, outcome, false);
    operation[0] = 'x'; outcome[0] = 'x';
    assert(!std::strcmp(receipt.operation, "move") && !std::strcmp(receipt.result, "not_ready_or_busy"));
    receipt.Record(30, "get_status", "ok", true);
    receipt.Record(40, "drive_renew", "renewed", true);
    assert(receipt.at == 20 && !receipt.web);
    receipt.Record(50, "drive_renew", "drive_cancelled", true);
    assert(receipt.at == 50 && receipt.web && !std::strcmp(receipt.result, "drive_cancelled"));
    receipt.Record(60, "unknown", "accepted", true);
    receipt.Record(70, "stop", "untrusted\"text", true);
    assert(receipt.at == 50);
    receipt.Record(80, "stop", "ok", false);
    assert(receipt.at == 80 && !std::strcmp(receipt.operation, "stop"));
    std::puts("PASS: bounded request receipt, copied lifetime, query/renewal isolation and invalid text rejection");
}
