#ifndef CYBERTRACK_CONTROL_H
#define CYBERTRACK_CONTROL_H

#include <stdbool.h>
#include <stdint.h>

typedef enum { CT_BOOT, CT_DISARMED, CT_READY, CT_ACTIVE, CT_FAULT } ct_state;
typedef enum { CT_NONE, CT_MOVE, CT_WATER, CT_BUBBLES } ct_action;
typedef enum { CT_FORWARD, CT_BACKWARD, CT_LEFT, CT_RIGHT } ct_direction;
typedef enum {
    CT_OK, CT_NOT_READY, CT_UNAVAILABLE, CT_INVALID, CT_BUSY,
    CT_SESSION_MISMATCH, CT_REPLAY, CT_EXPIRED, CT_CLOCK_ERROR
} ct_result;
typedef enum {
    CT_NO_FAULT, CT_STOPPED, CT_EXTERNAL_FAULT, CT_SESSION_LOST, CT_CLOCK_FAULT
} ct_fault;

/* Zero disables a capability. Values are supplied by a qualified board profile;
 * host tests use synthetic limits, never physical operating recommendations. */
typedef struct {
    uint32_t move_max_ms;
    uint32_t water_max_ms;
    uint32_t bubbles_max_ms;
    uint8_t max_speed_level;
} ct_limits;

typedef struct {
    uint64_t session;
    uint64_t sequence;
    uint64_t expires_at_ms;
    ct_action action;
    ct_direction direction;
    uint8_t speed_level;
    uint32_t duration_ms;
} ct_request;

/* Logical targets only: positive means forward on each track. Speed levels
 * are not PWM percentages. The board adapter must map and verify polarity. */
typedef struct {
    int16_t left_level;
    int16_t right_level;
    bool water;
    bool bubbles;
} ct_output;

/* Owned by one serialized control loop. Do not modify fields outside this API. */
typedef struct {
    ct_state state;
    ct_fault fault;
    ct_limits limits;
    ct_output output;
    bool stop_held;
    bool fault_present;
    uint64_t session;
    uint64_t last_sequence;
    uint64_t last_now_ms;
    uint64_t ends_at_ms;
    /* Captured at ingress so queued requests cannot cross a local re-enable. */
    uint64_t enable_generation;
} ct_controller;

void ct_init(ct_controller *c, ct_limits limits, uint64_t now_ms);
ct_result ct_boot_complete(ct_controller *c);
ct_result ct_tick(ct_controller *c, uint64_t now_ms);
/* session=0 means disconnected. A new session always revokes local enable. */
ct_result ct_set_session(ct_controller *c, uint64_t session, uint64_t now_ms);
void ct_set_stop(ct_controller *c, bool held);
void ct_set_fault(ct_controller *c, bool present);
/* Also handles a remote stop, without requiring an action ID or enabled state. */
void ct_stop(ct_controller *c);
/* Local event only; never expose as a remote tool. Release alone cannot rearm. */
ct_result ct_local_enable(ct_controller *c, uint64_t now_ms);
ct_result ct_submit(ct_controller *c, const ct_request *request, uint64_t now_ms);

#endif
