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

bool muse_notice_core_publish_mode(muse_notice_core_t *state, const char *message_id,
                                   const char *text, bool unread_only)
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
    state->unread_only[slot] = unread_only;
    state->seen[state->seen_next++ % MUSE_NOTICE_SEEN_MAX] = id;
    ++state->count;
    return true;
}

bool muse_notice_core_take_mode(muse_notice_core_t *state, char *out, size_t cap,
                                bool include_unread)
{
    if (!state || !out || !cap || !state->count) return false;
    unsigned selected = 0;
    while (selected < state->count && !include_unread &&
           state->unread_only[(state->head + selected) % MUSE_NOTICE_QUEUE_MAX]) ++selected;
    if (selected == state->count) return false;
    unsigned slot = (state->head + selected) % MUSE_NOTICE_QUEUE_MAX;
    size_t n = utf8_prefix(state->text[slot], cap);
    if (!n) return false;
    memcpy(out, state->text[slot], n);
    out[n] = '\0';
    for (unsigned i = selected; i + 1 < state->count; ++i) {
        unsigned to = (state->head + i) % MUSE_NOTICE_QUEUE_MAX;
        unsigned from = (to + 1) % MUSE_NOTICE_QUEUE_MAX;
        memcpy(state->text[to], state->text[from], sizeof(state->text[to]));
        state->unread_only[to] = state->unread_only[from];
    }
    unsigned tail = (state->head + --state->count) % MUSE_NOTICE_QUEUE_MAX;
    state->text[tail][0] = '\0';
    state->unread_only[tail] = false;
    return true;
}

bool muse_notice_core_publish(muse_notice_core_t *state, const char *id, const char *text)
{
    return muse_notice_core_publish_mode(state, id, text, false);
}

bool muse_notice_core_take(muse_notice_core_t *state, char *out, size_t cap)
{
    return muse_notice_core_take_mode(state, out, cap, false);
}

void muse_notice_core_silence(muse_notice_core_t *state)
{
    if (!state) return;
    for (unsigned i = 0; i < state->count; ++i)
        state->unread_only[(state->head + i) % MUSE_NOTICE_QUEUE_MAX] = true;
}

bool muse_notice_core_audible(const muse_notice_core_t *state)
{
    if (!state) return false;
    for (unsigned i = 0; i < state->count; ++i)
        if (!state->unread_only[(state->head + i) % MUSE_NOTICE_QUEUE_MAX]) return true;
    return false;
}

bool muse_notice_core_return_unread(muse_notice_core_t *state, const char *text)
{
    if (!state || !text || !text[0] || state->count >= MUSE_NOTICE_QUEUE_MAX) return false;
    size_t n = utf8_prefix(text, MUSE_NOTICE_TEXT_MAX + 1);
    if (!n) return false;
    state->head = (state->head + MUSE_NOTICE_QUEUE_MAX - 1) % MUSE_NOTICE_QUEUE_MAX;
    memcpy(state->text[state->head], text, n);
    state->text[state->head][n] = '\0';
    state->unread_only[state->head] = true;
    ++state->count;
    return true;
}
