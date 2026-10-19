// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Single session-task caller; the worker never accesses turn/playback state.
 * Cancel invalidates the request immediately. A bounded in-flight socket may
 * finish later, but its result cannot be adopted by a subsequent request. */
bool muse_local_tts_configured(void);
bool muse_local_tts_begin(const char *text);
void muse_local_tts_cancel(void);
void muse_local_tts_reap(void);
bool muse_local_tts_pending(void);
enum muse_local_tts_result { MUSE_LOCAL_PENDING, MUSE_LOCAL_READY, MUSE_LOCAL_FAILED };
enum muse_local_tts_result muse_local_tts_take(uint8_t *out, size_t capacity, size_t *length);
