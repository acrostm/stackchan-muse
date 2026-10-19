// SPDX-License-Identifier: Apache-2.0
#include "muse_notice_core.h"

#include <string.h>

static uint64_t hash_text(const char *text)
{
    uint64_t hash = 1469598103934665603ULL;
    for (const unsigned char *p = (const unsigned char *)text; *p; ++p) {
        hash ^= *p;
        hash *= 1099511628211ULL;
    }
    return hash ? hash : 1;
}

static size_t utf8_prefix(const char *text, size_t cap)
{
    if (cap < 2) return 0;
    size_t used = 0, remaining = strlen(text);
    while (used < remaining) {
        unsigned char c = (unsigned char)text[used];
        size_t width = c < 0x80 ? 1 : (c >= 0xc2 && c <= 0xdf) ? 2 :
                       (c >= 0xe0 && c <= 0xef) ? 3 :
                       (c >= 0xf0 && c <= 0xf4) ? 4 : 0;
        if (!width || width > remaining - used || used + width >= cap) break;
        bool valid = true;
        for (size_t i = 1; i < width; ++i)
            if (((unsigned char)text[used + i] & 0xc0) != 0x80) valid = false;
        if (!valid) break;
        used += width;
    }
    return used;
}

bool muse_notice_core_publish(muse_notice_core_t *state, const char *message_id,
                              const char *text)
{
    if (!state || !text || !text[0] || state->count >= MUSE_NOTICE_QUEUE_MAX)
        return false;
    uint64_t id = hash_text(message_id && message_id[0] ? message_id : text);
    for (unsigned i = 0; i < MUSE_NOTICE_SEEN_MAX; ++i)
        if (state->seen[i] == id) return false;
    size_t length = utf8_prefix(text, sizeof(state->text[0]));
    if (!length) return false;
    unsigned slot = (state->head + state->count) % MUSE_NOTICE_QUEUE_MAX;
    memcpy(state->text[slot], text, length);
    state->text[slot][length] = '\0';
    state->seen[state->seen_next++ % MUSE_NOTICE_SEEN_MAX] = id;
    ++state->count;
    return true;
}

bool muse_notice_core_take(muse_notice_core_t *state, char *out, size_t cap)
{
    if (!state || !out || !cap || !state->count) return false;
    size_t n = utf8_prefix(state->text[state->head], cap);
    if (!n) return false;
    memcpy(out, state->text[state->head], n);
    out[n] = '\0';
    state->text[state->head][0] = '\0';
    state->head = (state->head + 1) % MUSE_NOTICE_QUEUE_MAX;
    --state->count;
    return true;
}
