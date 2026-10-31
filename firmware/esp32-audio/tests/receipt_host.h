#pragma once
// Compile the actual Reply function with real guards and a controlled clock/IO.
#include "control_sessions.h"
#include "recent_command.h"
#include "status_facts.h"
#include "web_request.h"
#include "cJSON.h"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <string>
ControlSessions sessions;
AudioActionGuard& guard = sessions.guard;
RecentCommand recent_command;
struct { bool fault = false; } outputs;
uint64_t clock_ms = 1000;
uint64_t Now() { return clock_ms; }
std::string Decimal(uint64_t value) { return std::to_string(value); }
unsigned sequence = 0, dropped_events = 0;
std::string device_id(32, 'd'), boot_id(32, 'b');
int lock;
constexpr int portMAX_DELAY = 0;
void xSemaphoreTake(int, int) {}
void xSemaphoreGive(int) {}
void TickLocked(uint64_t now) { sessions.Tick(now, false); }
void ApplyLocked(uint64_t) {} // No device output is linked in this host harness.
int CyberTrackDistanceSnapshot() { return 0; }
namespace ultrasonic { std::string Json(int, uint64_t) { return "{\"valid\":false,\"error\":\"no_echo\"}"; } }
#define ESP_LOGI(...) ((void)0)
#include "receipt_reply.inc"
