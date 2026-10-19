// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <stdbool.h>
#include <stdint.h>

#define STACKCHAN_YAW_LIMIT_TENTHS 1280
#define STACKCHAN_PITCH_LIMIT_TENTHS 900

typedef enum {
    STACKCHAN_MOVE_EXPRESSION = 1,
    STACKCHAN_MOVE_PET = 2,
    STACKCHAN_MOVE_COMMAND = 3,
    STACKCHAN_MOVE_EMERGENCY = 4,
} stackchan_move_priority_t;

typedef struct {
    float yaw;
    float pitch;
    float yaw_velocity;
    float pitch_velocity;
    float target_yaw;
    float target_pitch;
    float stiffness;
    float damping;
    int priority;
    int64_t expires_us;
    bool active;
} stackchan_motion_t;

void stackchan_motion_init(stackchan_motion_t *motion, int yaw_tenths, int pitch_tenths);

/* The newest request wins at equal priority. A lower-priority request is
 * ignored. Speed is the StackChan BSP's 0..1000 scale. expires_us == 0 keeps
 * the target until replaced; otherwise a non-positive duration cancels it. */
bool stackchan_motion_set_target(stackchan_motion_t *motion, int yaw_tenths, int pitch_tenths,
                                 int speed, stackchan_move_priority_t priority,
                                 int64_t now_us, int64_t expires_us);

/* Emergency stop has no trajectory and cannot be delayed by queued motion. */
void stackchan_motion_cancel(stackchan_motion_t *motion);

/* Advances a 50 Hz spring integration. Returns true while torque is needed. */
bool stackchan_motion_tick(stackchan_motion_t *motion, int64_t now_us, float dt_s,
                           int *yaw_tenths, int *pitch_tenths);
