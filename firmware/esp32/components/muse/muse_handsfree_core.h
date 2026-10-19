// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Policy only. Classification is supplied by the real wake/VAD adapter. */
typedef enum {
    MUSE_HF_OFF, MUSE_HF_IDLE, MUSE_HF_COOLDOWN, MUSE_HF_FOLLOW,
    MUSE_HF_WAIT_SPEECH, MUSE_HF_RECORDING, MUSE_HF_BLOCKED,
} muse_hf_phase_t;
typedef enum {
    MUSE_HF_NONE = 0, MUSE_HF_START = 1, MUSE_HF_END = 2, MUSE_HF_DROP = 4,
} muse_hf_event_t;

typedef struct {
    muse_hf_phase_t phase;
    uint32_t generation;
    uint32_t speech_ms;
    uint32_t cooldown_ms, ignore_ms;
    int64_t last_ms, started_ms, last_speech_ms;
    bool enabled, had_speech, follow_pending, awaiting_reply;
} muse_handsfree_t;

void muse_handsfree_init(muse_handsfree_t *state, bool enabled, int64_t now_ms);
muse_hf_event_t muse_handsfree_enable(muse_handsfree_t *state, bool enabled, int64_t now_ms);
muse_hf_event_t muse_handsfree_tick(muse_handsfree_t *state, int64_t now_ms,
                                    bool wake, uint32_t speech_ms, bool busy, bool cancel);
/* speech_ms counts only fresh VAD-classified samples (0..60 ms per call), not
 * elapsed wall time or a cached positive label. */
/* All calls belong to the voice task; UI only posts a request to that owner. */
uint32_t muse_handsfree_manual_started(muse_handsfree_t *state, int64_t now_ms);
/* Must be driven by actual local turn/playback completion, never HTTP success.
 * A stale completion cannot reopen the microphone after cancellation. */
void muse_handsfree_reply_done(muse_handsfree_t *state, uint32_t generation,
                               int64_t now_ms, bool completed, bool allow_follow);

#ifdef __cplusplus
}
#endif
