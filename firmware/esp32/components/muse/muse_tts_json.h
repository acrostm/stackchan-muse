// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Encode a bounded UTF-8 prefix as {"text":"..."}. Never split a codepoint.
 * Controls become spaces. Invalid input or insufficient capacity fails closed;
 * output is empty and written is zero. Capacity includes the terminating NUL. */
bool muse_tts_json(const char *text, size_t max_chars, char *output,
                   size_t capacity, size_t *written);

#ifdef __cplusplus
}
#endif
