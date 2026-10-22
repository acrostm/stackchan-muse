// SPDX-License-Identifier: Apache-2.0
#include "muse_notice_core.h"
#include <stdlib.h>
#include <string.h>

static uint64_t hash_text(const char *text)
{
    uint64_t hash = 1469598103934665603ULL;
    for (const unsigned char *p = (const unsigned char *)text; *p; ++p) {
        hash ^= *p; hash *= 1099511628211ULL;
    }
    return hash ? hash : 1;
}

static size_t width(const unsigned char *s, size_t left)
{
    if (!left) return 0;
    unsigned c = s[0];
    size_t n = c < 0x80 ? 1 : c >= 0xc2 && c <= 0xdf ? 2 :
               c >= 0xe0 && c <= 0xef ? 3 : c >= 0xf0 && c <= 0xf4 ? 4 : 0;
    if (!n || n > left) return 0;
    for (size_t i = 1; i < n; ++i) if ((s[i] & 0xc0) != 0x80) return 0;
    if ((c == 0xe0 && s[1] < 0xa0) || (c == 0xed && s[1] >= 0xa0) ||
        (c == 0xf0 && s[1] < 0x90) || (c == 0xf4 && s[1] >= 0x90)) return 0;
    return n;
}

static bool valid_text(const char *text, size_t n)
{
    size_t at = 0;
    while (at < n) {
        size_t step = width((const unsigned char *)text + at, n - at);
        if (!step) return false;
        at += step;
    }
    return n != 0;
}

size_t muse_notice_text_chunk(const char *text, size_t offset, char *out, size_t cap)
{
    if (!out || !cap) return 0;
    out[0] = 0;
    if (!text || cap < 2) return 0;
    size_t length = strlen(text);
    if (offset > length) return 0;
    size_t n = 0;
    while (offset + n < length) {
        size_t step = width((const unsigned char *)text + offset + n, length - offset - n);
        if (!step || n + step >= cap) break;
        n += step;
    }
    memcpy(out, text + offset, n); out[n] = 0;
    return n;
}

bool muse_notice_core_publish_mode(muse_notice_core_t *state, const char *id,
                                   const char *text, bool unread_only)
{
    if (!state) return false;
    state->last_result = MUSE_NOTICE_INVALID_TEXT;
    if (!text || !text[0]) return false;
    size_t n = 0;
    while (n <= MUSE_NOTICE_TEXT_MAX && text[n]) ++n;
    if (n > MUSE_NOTICE_TEXT_MAX) { state->last_result = MUSE_NOTICE_TOO_LONG; return false; }
    if (!valid_text(text, n)) return false;
    uint64_t key = hash_text(id && id[0] ? id : text);
    for (unsigned i = 0; i < MUSE_NOTICE_SEEN_MAX; ++i)
        if (state->seen[i] == key) { state->last_result = MUSE_NOTICE_DUPLICATE; return false; }
    if (state->reserved >= MUSE_NOTICE_QUEUE_MAX ||
        state->count >= MUSE_NOTICE_QUEUE_MAX - state->reserved) {
        state->last_result = MUSE_NOTICE_FULL; return false;
    }
    char *copy = state->allocate ? state->allocate(n + 1) : malloc(n + 1);
    if (!copy) { state->last_result = MUSE_NOTICE_NO_MEMORY; return false; }
    memcpy(copy, text, n + 1);
    unsigned slot = (state->head + state->count) % MUSE_NOTICE_QUEUE_MAX;
    state->text[slot] = copy; state->unread_only[slot] = unread_only;
    state->seen[state->seen_next++ % MUSE_NOTICE_SEEN_MAX] = key;
    ++state->count; state->last_result = MUSE_NOTICE_ACCEPTED;
    return true;
}

static unsigned selected(const muse_notice_core_t *state, bool include_unread)
{
    unsigned i = 0;
    while (i < state->count && !include_unread &&
           state->unread_only[(state->head + i) % MUSE_NOTICE_QUEUE_MAX]) ++i;
    return i;
}

char *muse_notice_core_claim(muse_notice_core_t *state, bool include_unread)
{
    if (!state || !state->count) return NULL;
    unsigned index = selected(state, include_unread);
    if (index == state->count) return NULL;
    char *text = state->text[(state->head + index) % MUSE_NOTICE_QUEUE_MAX];
    for (unsigned i = index; i + 1 < state->count; ++i) {
        unsigned to = (state->head + i) % MUSE_NOTICE_QUEUE_MAX, from = (to + 1) % MUSE_NOTICE_QUEUE_MAX;
        state->text[to] = state->text[from]; state->unread_only[to] = state->unread_only[from];
    }
    unsigned tail = (state->head + --state->count) % MUSE_NOTICE_QUEUE_MAX;
    state->text[tail] = NULL; state->unread_only[tail] = false;
    return text;
}

void muse_notice_core_release(muse_notice_core_t *state, char *text)
{
    if (state && state->release) state->release(text); else free(text);
}

bool muse_notice_core_take_mode(muse_notice_core_t *state, char *out, size_t cap, bool include_unread)
{
    if (!state || !out || !state->count) return false;
    unsigned index = selected(state, include_unread);
    if (index == state->count || cap <= strlen(state->text[(state->head + index) % MUSE_NOTICE_QUEUE_MAX])) return false;
    char *text = muse_notice_core_claim(state, include_unread);
    memcpy(out, text, strlen(text) + 1); muse_notice_core_release(state, text); return true;
}

bool muse_notice_core_return_owned(muse_notice_core_t *state, char *text)
{
    if (!state || !text || !*text || state->count >= MUSE_NOTICE_QUEUE_MAX) return false;
    state->head = (state->head + MUSE_NOTICE_QUEUE_MAX - 1) % MUSE_NOTICE_QUEUE_MAX;
    state->text[state->head] = text; state->unread_only[state->head] = true; ++state->count; return true;
}

bool muse_notice_core_publish(muse_notice_core_t *state, const char *id, const char *text)
{ return muse_notice_core_publish_mode(state, id, text, false); }
bool muse_notice_core_take(muse_notice_core_t *state, char *out, size_t cap)
{ return muse_notice_core_take_mode(state, out, cap, false); }
void muse_notice_core_silence(muse_notice_core_t *state)
{
    if (state) for (unsigned i = 0; i < state->count; ++i)
        state->unread_only[(state->head + i) % MUSE_NOTICE_QUEUE_MAX] = true;
}
bool muse_notice_core_audible(const muse_notice_core_t *state)
{
    return state && selected(state, false) < state->count;
}
void muse_notice_core_clear(muse_notice_core_t *state)
{
    if (!state) return;
    for (unsigned i = 0; i < MUSE_NOTICE_QUEUE_MAX; ++i) {
        muse_notice_core_release(state, state->text[i]); state->text[i] = NULL;
        state->unread_only[i] = false;
    }
    state->head = state->count = 0;
}
