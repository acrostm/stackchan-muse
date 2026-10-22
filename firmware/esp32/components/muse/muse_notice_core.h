// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define MUSE_NOTICE_QUEUE_MAX 4
#define MUSE_NOTICE_TEXT_MAX 700
#define MUSE_NOTICE_SEEN_MAX 32

typedef struct {
    char text[MUSE_NOTICE_QUEUE_MAX][MUSE_NOTICE_TEXT_MAX + 1];
    bool unread_only[MUSE_NOTICE_QUEUE_MAX];
    unsigned head;
    unsigned count;
    uint64_t seen[MUSE_NOTICE_SEEN_MAX];
    unsigned seen_next;
} muse_notice_core_t;

bool muse_notice_core_publish(muse_notice_core_t *state, const char *message_id,
                              const char *text);
bool muse_notice_core_take(muse_notice_core_t *state, char *out, size_t cap);

/* Silent arrivals remain unread until explicitly requested, even after quiet
 * hours end. Audible messages behind them can still be consumed in FIFO order. */
bool muse_notice_core_publish_mode(muse_notice_core_t *state, const char *message_id,
                                   const char *text, bool unread_only);
bool muse_notice_core_take_mode(muse_notice_core_t *state, char *out, size_t cap,
                                bool include_unread);
void muse_notice_core_silence(muse_notice_core_t *state);
bool muse_notice_core_audible(const muse_notice_core_t *state);

bool muse_notice_core_return_unread(muse_notice_core_t *state, const char *text);
