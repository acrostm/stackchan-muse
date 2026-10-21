// SPDX-License-Identifier: Apache-2.0
#include "stackchan_motion_core.h"

#include <math.h>

static float clampf(float value, float low, float high)
{
    return value < low ? low : value > high ? high : value;
}

static int clampi(int value, int low, int high)
{
    return value < low ? low : value > high ? high : value;
}

static float spring_stiffness(int speed)
{
    const float normalized = clampf((float)speed, 0.0f, 1000.0f) / 1000.0f;
    return 10.0f + normalized * normalized * 640.0f;
}

/* Exact critically damped spring solution. Explicit Euler becomes unstable at
 * the BSP's fastest stiffness, so integrate the closed form instead. */
static float spring_step(float position, float *velocity, float target,
                         float stiffness, float dt)
{
    const float omega = sqrtf(stiffness);
    const float error = position - target;
    const float decay = expf(-omega * dt);
    const float next_error =
        (error + (*velocity + omega * error) * dt) * decay;
    *velocity = (*velocity - omega * (*velocity + omega * error) * dt) * decay;
    return target + next_error;
}

/* Spring stiffness controls response, not a hard speed bound. Clamp both
 * the emitted displacement and the stored velocity, including a large first
 * target after reacquiring physical feedback. */
static float bounded_spring_step(float position, float *velocity, float target,
                                 float stiffness, float max_velocity, float dt)
{
    const float next = spring_step(position, velocity, target, stiffness, dt);
    *velocity = clampf(*velocity, -max_velocity, max_velocity);
    const float step = clampf(next - position, -max_velocity * dt, max_velocity * dt);
    return position + step;
}

void stackchan_motion_init(stackchan_motion_t *motion, int yaw_tenths, int pitch_tenths)
{
    if (!motion) return;
    *motion = (stackchan_motion_t){
        .yaw = (float)clampi(yaw_tenths, -STACKCHAN_YAW_LIMIT_TENTHS,
                             STACKCHAN_YAW_LIMIT_TENTHS),
        .pitch = (float)clampi(pitch_tenths, 0, STACKCHAN_PITCH_LIMIT_TENTHS),
    };
    motion->target_yaw = motion->yaw;
    motion->target_pitch = motion->pitch;
}

void stackchan_motion_rebase(stackchan_motion_t *motion, int yaw_tenths,
                             int pitch_tenths)
{
    if (!motion) return;
    motion->yaw = (float)clampi(yaw_tenths, -STACKCHAN_YAW_LIMIT_TENTHS,
                                STACKCHAN_YAW_LIMIT_TENTHS);
    motion->pitch = (float)clampi(pitch_tenths, 0, STACKCHAN_PITCH_LIMIT_TENTHS);
    motion->yaw_velocity = motion->pitch_velocity = 0;
}

static bool same_target(const stackchan_motion_t *motion, float yaw, float pitch)
{
    return fabsf(motion->target_yaw - yaw) < 0.1f &&
           fabsf(motion->target_pitch - pitch) < 0.1f;
}

bool stackchan_motion_set_target(stackchan_motion_t *motion, int yaw_tenths, int pitch_tenths,
                                 int speed, stackchan_move_priority_t priority,
                                 int64_t now_us, int64_t expires_us)
{
    if (!motion || expires_us < 0) return false;
    const float yaw = (float)clampi(yaw_tenths, -STACKCHAN_YAW_LIMIT_TENTHS,
                                    STACKCHAN_YAW_LIMIT_TENTHS);
    const float pitch = (float)clampi(pitch_tenths, 0, STACKCHAN_PITCH_LIMIT_TENTHS);
    if (motion->active && (int)priority < motion->priority) return false;
    /* Even a settled target is a new accepted command. The hardware owner may
     * reactivate it after measuring a head moved while torque was off. */
    motion->stiffness = spring_stiffness(speed);
    /* BSP speed 0..1000 maps to a conservative 2..62 degrees/second cap. */
    motion->max_velocity = 20.0f + 0.6f * clampf((float)speed, 0.0f, 1000.0f);
    motion->damping = 2.0f * sqrtf(motion->stiffness);
    motion->priority = priority;
    motion->expires_us = expires_us ? now_us + expires_us : 0;
    if (same_target(motion, yaw, pitch) &&
        fabsf(motion->yaw - yaw) < 0.1f && fabsf(motion->pitch - pitch) < 0.1f) {
        motion->active = false;
        motion->yaw_velocity = motion->pitch_velocity = 0;
        return true;
    }
    motion->target_yaw = yaw;
    motion->target_pitch = pitch;
    motion->active = true;
    return true;
}

void stackchan_motion_cancel(stackchan_motion_t *motion)
{
    if (!motion) return;
    motion->target_yaw = motion->yaw;
    motion->target_pitch = motion->pitch;
    motion->yaw_velocity = motion->pitch_velocity = 0;
    motion->priority = STACKCHAN_MOVE_EMERGENCY;
    motion->expires_us = 0;
    motion->active = false;
}

bool stackchan_motion_tick(stackchan_motion_t *motion, int64_t now_us, float dt_s,
                           int *yaw_tenths, int *pitch_tenths)
{
    if (!motion || dt_s <= 0) return false;
    if (motion->active && motion->expires_us && now_us >= motion->expires_us) {
        stackchan_motion_cancel(motion);
    }
    if (motion->active) {
        const float yaw_error = motion->target_yaw - motion->yaw;
        const float pitch_error = motion->target_pitch - motion->pitch;
        motion->yaw = bounded_spring_step(motion->yaw, &motion->yaw_velocity,
                                  motion->target_yaw, motion->stiffness,
                                  motion->max_velocity, dt_s);
        motion->pitch = bounded_spring_step(motion->pitch, &motion->pitch_velocity,
                                    motion->target_pitch, motion->stiffness,
                                    motion->max_velocity, dt_s);
        motion->yaw = clampf(motion->yaw, -STACKCHAN_YAW_LIMIT_TENTHS,
                             STACKCHAN_YAW_LIMIT_TENTHS);
        motion->pitch = clampf(motion->pitch, 0, STACKCHAN_PITCH_LIMIT_TENTHS);
        if (fabsf(yaw_error) < 0.1f && fabsf(motion->yaw_velocity) < 0.1f &&
            fabsf(pitch_error) < 0.1f && fabsf(motion->pitch_velocity) < 0.1f &&
            fabsf(yaw_error) <= motion->max_velocity * dt_s &&
            fabsf(pitch_error) <= motion->max_velocity * dt_s) {
            motion->yaw = motion->target_yaw;
            motion->pitch = motion->target_pitch;
            motion->yaw_velocity = motion->pitch_velocity = 0;
            motion->active = false;
        }
    }
    if (yaw_tenths) *yaw_tenths = (int)lroundf(motion->yaw);
    if (pitch_tenths) *pitch_tenths = (int)lroundf(motion->pitch);
    return motion->active;
}
