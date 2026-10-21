// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

/* One owner: the voice task. Frames are mono PCM16 at 16 kHz. */
typedef struct {
    bool wake;
    uint32_t speech_ms;  /* only freshly classified speech, never cached */
} muse_sr_result_t;
esp_err_t muse_sr_engine_init(void);
void muse_sr_engine_deinit(void);
void muse_sr_engine_reset(void);
esp_err_t muse_sr_engine_feed(const int16_t *pcm, size_t frames,
                               bool allow_wake, bool allow_vad,
                               muse_sr_result_t *result);
