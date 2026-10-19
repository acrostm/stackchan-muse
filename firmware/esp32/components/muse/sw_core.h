// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define SW_TEXT_CAP 1024
#define SW_HISTORY_COUNT 8
#define SW_LINE_CAP (128 * 1024)

/* Independent of ESP-IDF: callers serialize access to history. */
typedef struct {
    char text[SW_TEXT_CAP];
    bool assistant;
} sw_entry_t;
typedef struct {
    sw_entry_t entries[SW_HISTORY_COUNT];
    unsigned next, count, version;
} sw_history_t;
void sw_text_copy(char *out, size_t cap, const char *text);
void sw_history_add(sw_history_t *h, bool assistant, const char *text);
const sw_entry_t *sw_history_get(const sw_history_t *h, unsigned newest);
bool sw_header_safe(const char *text, size_t max);
/* True when a new per-device eight-digit setup PIN must be saved. */
bool sw_setup_pin(char out[9], const char *saved, uint32_t entropy);
/* Incremental newline framing; rejects oversize lines before writing. */
typedef struct { char *buf; size_t cap, len; bool failed; } sw_lines_t;
typedef bool (*sw_line_fn)(const char *line, void *ctx);
bool sw_lines_feed(sw_lines_t *s, const void *data, size_t len, sw_line_fn fn, void *ctx);

/* Release only unpaired connections that never started a pairing handshake. */
typedef struct { int64_t since; bool tracking; } sw_pairing_idle_t;
bool sw_pairing_idle_expired(sw_pairing_idle_t *state, int64_t now,
                            bool connected, bool handshake, bool paired);

/* Physical button duration, independent of pre-roll and audio scheduling. */
typedef struct { int64_t pressed_us, released_us; bool down, released, cancelled; } sw_ptt_t;
typedef enum { SW_PTT_WAIT, SW_PTT_SHORT, SW_PTT_CANCELLED, SW_PTT_SEND } sw_ptt_result_t;
void sw_ptt_press(sw_ptt_t *s, int64_t now);
void sw_ptt_release(sw_ptt_t *s, int64_t now);
void sw_ptt_cancel(sw_ptt_t *s);
sw_ptt_result_t sw_ptt_result(const sw_ptt_t *s);
