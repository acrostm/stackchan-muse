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
    unsigned head;
    unsigned count;
    uint64_t seen[MUSE_NOTICE_SEEN_MAX];
    unsigned seen_next;
} muse_notice_core_t;

bool muse_notice_core_publish(muse_notice_core_t *state, const char *message_id,
                              const char *text);
bool muse_notice_core_take(muse_notice_core_t *state, char *out, size_t cap);
