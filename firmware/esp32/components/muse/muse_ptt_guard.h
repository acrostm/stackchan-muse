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
