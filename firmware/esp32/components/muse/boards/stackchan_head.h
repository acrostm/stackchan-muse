/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/* StackChan head base: servo power and the two head servos (MuseChan). */
#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "driver/i2c_master.h"
#include "esp_err.h"
#include "stackchan_motion_core.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Power the base through its M5IOE1 expander and start the servo bus.
 * Returns ESP_ERR_NOT_FOUND when no base answers (a bare CoreS3). */
esp_err_t stackchan_head_init(i2c_master_bus_handle_t bus);

/* Whether a StackChan head base answered at boot. */
bool stackchan_head_present(void);

/* Motion starts only after a per-device centre has been saved in the official
 * StackChan BSP's `servo` NVS namespace. A head without that calibration is
 * present but stays torque-free. */
bool stackchan_head_ready(void);

/* Aim the head: yaw -128..128 degrees, pitch 0..90 (clamped). */
esp_err_t stackchan_head_look(int yaw_deg, int pitch_deg);

/* Priority-arbitrated target in whole degrees. Lower-priority requests cannot
 * interrupt a higher-priority gesture. Command/emergency priorities invalidate
 * any older multi-step expression or pet sequence. TTL 0 holds until replaced. */
esp_err_t stackchan_head_move(int yaw_deg, int pitch_deg, int speed,
                              stackchan_move_priority_t priority,
                              int64_t expires_us);

/* Multi-step gestures capture a generation and pass it back to each move.
 * Stop or a higher-priority explicit command invalidates those later moves. */
uint32_t stackchan_head_ready_generation(void);
uint32_t stackchan_head_stop_and_generation(void);
esp_err_t stackchan_head_move_for_generation(int yaw_deg, int pitch_deg, int speed,
                                             stackchan_move_priority_t priority,
                                             int64_t expires_us,
                                             uint32_t generation);

/* Back to yaw 0, pitch 0. */
esp_err_t stackchan_head_center(void);

/* Immediately stop torque, discard queued targets and invalidate older
 * multi-step sequences. */
void stackchan_head_stop(void);

/* Save the current physical position as this unit's (0, 0). Centre the head
 * by hand while torque is off before calling this. */
esp_err_t stackchan_head_calibrate_current(void);

/* The servos' motor supply, through the expander. Safe without a base. */
esp_err_t stackchan_head_set_power(bool on);

/* Bench/serial: head.status, head.calibrate, head.stop, head.look=YAW,PITCH. */
bool stackchan_head_console_command(const char *line);

/* Explicit USB tracking session. Any stop or explicit command invalidates it.
 * Requests use tenths of degrees, ordered sequence numbers and a 100..1000 ms
 * device-local TTL. Expiry requires a new explicit begin, never auto-resume. */
uint32_t stackchan_head_track_begin(void);
esp_err_t stackchan_head_track_stop(uint32_t generation);
esp_err_t stackchan_head_track(uint32_t generation, uint32_t sequence,
                                int yaw_tenths, int pitch_tenths, int ttl_ms);

#ifdef __cplusplus
}
#endif
