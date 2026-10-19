// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <stdbool.h>
#include <stdint.h>

enum muse_ptt_result {
    MUSE_PTT_WAIT,
    MUSE_PTT_SHORT,
    MUSE_PTT_CANCELLED,
    MUSE_PTT_SEND,
};

/* Physical press duration, independent of audio pre-roll and queue latency. */
void muse_ptt_press(int64_t now_us);
void muse_ptt_release(int64_t now_us);
void muse_ptt_cancel(void);
enum muse_ptt_result muse_ptt_result(void);

/* A completed turn includes recordings that stopped at the maximum duration
 * while the physical key is still down. An explicit cancellation always wins. */
bool muse_ptt_should_submit(enum muse_ptt_result result, bool wake, bool reached_limit);
