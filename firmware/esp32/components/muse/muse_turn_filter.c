// SPDX-License-Identifier: Apache-2.0
#include "muse_turn_filter.h"

#include <string.h>

void muse_turn_filter_remember(muse_turn_filter_t *filter, const char *id)
{
    if (!filter || !id || !id[0] || strlen(id) >= MUSE_TURN_ID_MAX) return;
    for (unsigned i = 0; i < MUSE_TURN_IGNORED_IDS; ++i)
        if (!strcmp(filter->ids[i], id)) return;
    strncpy(filter->ids[filter->next++ % MUSE_TURN_IGNORED_IDS], id,
            MUSE_TURN_ID_MAX - 1);
    filter->ids[(filter->next + MUSE_TURN_IGNORED_IDS - 1) %
                MUSE_TURN_IGNORED_IDS][MUSE_TURN_ID_MAX - 1] = '\0';
}

bool muse_turn_filter_contains(const muse_turn_filter_t *filter, const char *id)
{
    if (!filter || !id || !id[0]) return false;
    for (unsigned i = 0; i < MUSE_TURN_IGNORED_IDS; ++i)
        if (filter->ids[i][0] && !strcmp(filter->ids[i], id)) return true;
    return false;
}
