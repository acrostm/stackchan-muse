// SPDX-License-Identifier: Apache-2.0
#include "muse_ptt_guard.h"

#include <stdatomic.h>

#define MIN_HOLD_US (2 * 1000000LL)
#define PTT_TURN_SLOTS 16

typedef struct {
    uint32_t id;
    int64_t pressed_us;
    int64_t released_us;
    bool down;
    bool released;
    bool cancelled;
} ptt_turn_t;

static ptt_turn_t s_turns[PTT_TURN_SLOTS];
static uint32_t s_current;
static uint32_t s_next_id;
static atomic_flag s_lock = ATOMIC_FLAG_INIT;

static void lock(void)
{
    while (atomic_flag_test_and_set_explicit(&s_lock, memory_order_acquire)) {}
}

static void unlock(void)
{
    atomic_flag_clear_explicit(&s_lock, memory_order_release);
}

static ptt_turn_t *find(uint32_t id)
{
    if (!id) return NULL;
    for (size_t i = 0; i < PTT_TURN_SLOTS; ++i)
        if (s_turns[i].id == id) return &s_turns[i];
    return NULL;
}

uint32_t muse_ptt_press(int64_t now_us)
{
    uint32_t id = 0;
    lock();
    for (size_t i = 0; i < PTT_TURN_SLOTS; ++i) {
        if (s_turns[i].id) continue;
        ++s_next_id;
        if (!s_next_id) ++s_next_id;
        id = s_next_id;
        s_turns[i] = (ptt_turn_t){
            .id = id,
            .pressed_us = now_us,
            .down = true,
        };
        s_current = id;
        break;
    }
    unlock();
    return id;
}

void muse_ptt_release_current(int64_t now_us)
{
    lock();
    ptt_turn_t *turn = find(s_current);
    if (turn && turn->down) {
        turn->down = false;
        turn->released = true;
        turn->released_us = now_us;
    }
    unlock();
}

void muse_ptt_cancel_current(void)
{
    lock();
    ptt_turn_t *turn = find(s_current);
    if (turn && turn->down) turn->cancelled = true;
    unlock();
}

enum muse_ptt_result muse_ptt_result(uint32_t id)
{
    lock();
    const ptt_turn_t *turn = find(id);
    enum muse_ptt_result result = MUSE_PTT_WAIT;
    if (turn) {
        if (turn->cancelled) result = MUSE_PTT_CANCELLED;
        else if (!turn->released || turn->down) result = MUSE_PTT_WAIT;
        else if (turn->pressed_us < 0 || turn->released_us < turn->pressed_us ||
                 turn->released_us - turn->pressed_us <= MIN_HOLD_US)
            result = MUSE_PTT_SHORT;
        else
            result = MUSE_PTT_SEND;
    }
    unlock();
    return result;
}

void muse_ptt_retire(uint32_t id)
{
    if (!id) return;
    lock();
    ptt_turn_t *turn = find(id);
    if (turn) {
        *turn = (ptt_turn_t){0};
        if (s_current == id) s_current = 0;
    }
    unlock();
}

bool muse_ptt_should_submit(enum muse_ptt_result result, bool wake, bool reached_limit)
{
    if (result == MUSE_PTT_CANCELLED) return false;
    return result == MUSE_PTT_SEND || wake || reached_limit;
}
