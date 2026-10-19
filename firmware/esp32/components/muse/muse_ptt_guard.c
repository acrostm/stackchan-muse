// SPDX-License-Identifier: Apache-2.0
#include "muse_ptt_guard.h"

#define MIN_HOLD_US (2 * 1000000LL)

struct ptt_state {
    int64_t pressed_us;
    int64_t released_us;
    bool down;
    bool released;
    bool cancelled;
};

static struct ptt_state s_state;

void muse_ptt_press(int64_t now_us)
{
    s_state = (struct ptt_state){
        .pressed_us = now_us,
        .down = true,
    };
}

void muse_ptt_release(int64_t now_us)
{
    if (!s_state.down) return;
    s_state.down = false;
    s_state.released = true;
    s_state.released_us = now_us;
}

void muse_ptt_cancel(void)
{
    if (s_state.down) s_state.cancelled = true;
}

enum muse_ptt_result muse_ptt_result(void)
{
    if (s_state.cancelled) return MUSE_PTT_CANCELLED;
    if (!s_state.released || s_state.down) return MUSE_PTT_WAIT;
    if (s_state.pressed_us < 0 || s_state.released_us < s_state.pressed_us ||
        s_state.released_us - s_state.pressed_us <= MIN_HOLD_US) {
        return MUSE_PTT_SHORT;
    }
    return MUSE_PTT_SEND;
}
