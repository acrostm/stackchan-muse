// SPDX-License-Identifier: Apache-2.0
#include "sw_core.h"
#include <string.h>
#include <stdio.h>

bool sw_setup_pin(char out[9], const char *saved, uint32_t entropy)
{
    bool valid = saved && strlen(saved) == 8;
    if (valid) for (unsigned i = 0; i < 8; ++i)
        if (saved[i] < '0' || saved[i] > '9') valid = false;
    if (valid) { memmove(out, saved, 9); return false; }
    snprintf(out, 9, "%08lu", (unsigned long)(entropy % 100000000U));
    return true;
}

void sw_text_copy(char *out, size_t cap, const char *text)
{
    if (!cap) return;
    size_t total = strlen(text), n = 0;
    while (n < total) {
        unsigned char c = (unsigned char)text[n];
        size_t width = c < 0x80 ? 1 : c >= 0xc2 && c <= 0xdf ? 2 :
            c >= 0xe0 && c <= 0xef ? 3 : c >= 0xf0 && c <= 0xf4 ? 4 : 0;
        if (!width || width > total - n || n + width >= cap) break;
        bool valid = true;
        for (size_t j = 1; j < width; ++j)
            if (((unsigned char)text[n + j] & 0xc0) != 0x80) valid = false;
        if (!valid) break;
        n += width;
    }
    memmove(out, text, n);
    out[n] = 0;
}

void sw_history_add(sw_history_t *h, bool assistant, const char *text)
{
    if (!text || !*text) return;
    sw_entry_t *e = &h->entries[h->next];
    sw_text_copy(e->text, sizeof(e->text), text);
    e->assistant = assistant;
    h->next = (h->next + 1) % SW_HISTORY_COUNT;
    if (h->count < SW_HISTORY_COUNT) ++h->count;
    ++h->version;
}

const sw_entry_t *sw_history_get(const sw_history_t *h, unsigned newest)
{
    if (newest >= h->count) return NULL;
    return &h->entries[(h->next + SW_HISTORY_COUNT - 1 - newest) % SW_HISTORY_COUNT];
}

bool sw_header_safe(const char *s, size_t max)
{
    if (!s || strlen(s) > max) return false;
    for (; *s; ++s) if ((unsigned char)*s < 32 || (unsigned char)*s == 127) return false;
    return true;
}

bool sw_lines_feed(sw_lines_t *s, const void *data, size_t len, sw_line_fn fn, void *ctx)
{
    if (s->failed || !s->buf || s->cap < 2) return false;
    const unsigned char *p = data;
    for (size_t i = 0; i < len; ++i) {
        if (p[i] == '\n') {
            if (s->len && s->buf[s->len - 1] == '\r') --s->len;
            s->buf[s->len] = 0;
            if (!fn(s->buf, ctx)) { s->failed = true; return false; }
            s->len = 0;
        } else {
            if (!p[i] || s->len + 1 >= s->cap) { s->failed = true; return false; }
            s->buf[s->len++] = (char)p[i];
        }
    }
    return true;
}

bool sw_pairing_idle_expired(sw_pairing_idle_t *state, int64_t now,
                            bool connected, bool handshake, bool paired)
{
    if (!connected || handshake || paired) { state->tracking = false; return false; }
    if (!state->tracking || now < state->since) {
        state->since = now; state->tracking = true; return false;
    }
    if (now - state->since < 30LL * 1000000) return false;
    state->tracking = false;
    return true;
}

void sw_ptt_press(sw_ptt_t *s, int64_t now)
{
    *s = (sw_ptt_t){ .pressed_us = now, .down = true };
}
void sw_ptt_release(sw_ptt_t *s, int64_t now)
{
    if (!s->down) return;
    s->down = false;
    s->released = true;
    s->released_us = now;
}
void sw_ptt_cancel(sw_ptt_t *s)
{
    if (s->down) s->cancelled = true;
}
sw_ptt_result_t sw_ptt_result(const sw_ptt_t *s)
{
    if (s->cancelled) return SW_PTT_CANCELLED;
    if (!s->released || s->down) return SW_PTT_WAIT;
    if (s->pressed_us < 0 || s->released_us < s->pressed_us ||
        s->released_us - s->pressed_us <= 2000000) return SW_PTT_SHORT;
    return SW_PTT_SEND;
}
