// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define MUSE_NOTICE_POLICY_BYTES 9
#define MUSE_NOTICE_CLOCK_MIN 1577836800LL

typedef struct {
    bool muted;
    bool quiet_enabled;
    uint16_t start_minute;
    uint16_t end_minute;
    int16_t utc_offset_minute;
} muse_notice_policy_t;

muse_notice_policy_t muse_notice_policy_default(void);
bool muse_notice_policy_valid(const muse_notice_policy_t *policy);
/* Quiet periods are [start,end), same start/end means all day. Unknown clock
 * suppresses automatic speech when a schedule is enabled. Explicit reading is
 * a separate user action and still respects the physical speaker setting. */
bool muse_notice_policy_quiet(const muse_notice_policy_t *policy, int64_t utc);
bool muse_notice_policy_encode(const muse_notice_policy_t *policy, uint8_t out[MUSE_NOTICE_POLICY_BYTES]);
bool muse_notice_policy_decode(muse_notice_policy_t *policy, const uint8_t *data, size_t size);
