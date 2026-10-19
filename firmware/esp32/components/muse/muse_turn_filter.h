// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <stdbool.h>
#include <stddef.h>

#define MUSE_TURN_IGNORED_IDS 8
#define MUSE_TURN_ID_MAX 80

typedef struct {
    char ids[MUSE_TURN_IGNORED_IDS][MUSE_TURN_ID_MAX];
    unsigned next;
} muse_turn_filter_t;

void muse_turn_filter_remember(muse_turn_filter_t *filter, const char *id);
bool muse_turn_filter_contains(const muse_turn_filter_t *filter, const char *id);
