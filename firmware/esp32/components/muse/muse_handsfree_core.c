// SPDX-License-Identifier: Apache-2.0
#include "muse_handsfree_core.h"

#define MIN_SPEECH_MS 300
#define END_SILENCE_MS 800
#define NO_SPEECH_MS 5000
#define MAX_RECORD_MS 15000
#define WAKE_TAIL_MS 120
#define FOLLOW_MS 8000
#define PLAYBACK_COOLDOWN_MS 600
#define CANCEL_COOLDOWN_MS 1000
#define MAX_AUDIO_GAP_MS 250

static bool capturing(const muse_handsfree_t *s)
{
    return s->phase == MUSE_HF_WAIT_SPEECH || s->phase == MUSE_HF_RECORDING;
}

static void advance(muse_handsfree_t *s)
{
    if (!++s->generation) ++s->generation;
}

static void cooldown(muse_handsfree_t *s, int64_t now, uint32_t length)
{
    s->phase = s->enabled ? MUSE_HF_COOLDOWN : MUSE_HF_OFF;
    s->last_ms = s->started_ms = now;
    s->cooldown_ms = length;
    s->awaiting_reply = s->follow_pending = false;
}

static bool clock_valid(muse_handsfree_t *s, int64_t now)
{
    if (now >= 0 && now >= s->last_ms) return true;
    advance(s);
    s->enabled = s->awaiting_reply = s->follow_pending = false;
    s->phase = MUSE_HF_OFF;
    return false;
}

void muse_handsfree_init(muse_handsfree_t *s, bool enabled, int64_t now)
{
    if (!s) return;
    *s = (muse_handsfree_t){ .generation = 1, .enabled = enabled && now >= 0 };
    cooldown(s, now >= 0 ? now : 0, PLAYBACK_COOLDOWN_MS);
}

muse_hf_event_t muse_handsfree_enable(muse_handsfree_t *s, bool enabled, int64_t now)
{
    if (!s) return MUSE_HF_NONE;
    const bool active = capturing(s) || s->awaiting_reply;
    if (!clock_valid(s, now)) return active ? MUSE_HF_DROP : MUSE_HF_NONE;
    if (s->enabled == enabled) return MUSE_HF_NONE;
    advance(s);
    s->enabled = enabled;
    cooldown(s, now, PLAYBACK_COOLDOWN_MS);
    return active ? MUSE_HF_DROP : MUSE_HF_NONE;
}

static muse_hf_event_t start(muse_handsfree_t *s, int64_t now, bool after_wake)
{
    advance(s);
    s->phase = MUSE_HF_WAIT_SPEECH;
    s->started_ms = s->last_speech_ms = now;
    s->speech_ms = 0;
    s->ignore_ms = after_wake ? WAKE_TAIL_MS : 0;
    s->had_speech = s->follow_pending = s->awaiting_reply = false;
    return MUSE_HF_START;  /* allocate local recording only, do not upload yet */
}

muse_hf_event_t muse_handsfree_tick(muse_handsfree_t *s, int64_t now,
                                    bool wake, uint32_t speech_ms, bool busy, bool cancel)
{
    if (!s) return MUSE_HF_NONE;
    bool active = capturing(s);
    const bool has_turn = active || s->awaiting_reply;
    if (!clock_valid(s, now)) return has_turn ? MUSE_HF_DROP : MUSE_HF_NONE;
    const bool speech = speech_ms != 0;
    const int64_t gap = now - s->last_ms;
    s->last_ms = now;
    if (!s->enabled) return MUSE_HF_NONE;
    if (cancel) {
        const bool drop = active || s->awaiting_reply;
        advance(s);
        cooldown(s, now, CANCEL_COOLDOWN_MS);
        return drop ? MUSE_HF_DROP : MUSE_HF_NONE;
    }
    if (busy) {
        if (s->phase != MUSE_HF_BLOCKED) {
            advance(s);
            s->phase = MUSE_HF_BLOCKED;
            s->awaiting_reply = false;
            s->follow_pending = false;
        }
        return active ? MUSE_HF_DROP : MUSE_HF_NONE;
    }
    if (s->phase == MUSE_HF_BLOCKED) {
        if (!s->awaiting_reply) cooldown(s, now, PLAYBACK_COOLDOWN_MS);
        return MUSE_HF_NONE;
    }
    if (s->phase == MUSE_HF_COOLDOWN) {
        const int64_t elapsed = now - s->started_ms;
        if (elapsed >= s->cooldown_ms) {
            if (s->follow_pending && elapsed < s->cooldown_ms + FOLLOW_MS) {
                s->phase = MUSE_HF_FOLLOW;
                s->started_ms += s->cooldown_ms;
            } else {
                s->phase = MUSE_HF_IDLE;
            }
            s->follow_pending = false;
        }
        return MUSE_HF_NONE;  /* discard the cooldown's last classifier frame */
    }
    if (!gap) return MUSE_HF_NONE;  /* do not credit the same classifier tick twice */
    if (gap > MAX_AUDIO_GAP_MS || speech_ms > 60) {
        advance(s);
        cooldown(s, now, CANCEL_COOLDOWN_MS);
        return active ? MUSE_HF_DROP : MUSE_HF_NONE;
    }
    if (s->phase == MUSE_HF_FOLLOW && now - s->started_ms >= FOLLOW_MS)
        s->phase = MUSE_HF_IDLE;
    if (s->phase == MUSE_HF_IDLE || s->phase == MUSE_HF_FOLLOW) {
        if (wake || (s->phase == MUSE_HF_FOLLOW && speech)) return start(s, now, wake);
        return MUSE_HF_NONE;
    }
    if (!active) return MUSE_HF_NONE;
    if (speech && now - s->started_ms >= s->ignore_ms) {
        s->had_speech = true;
        s->last_speech_ms = now;
        s->speech_ms += speech_ms;
        if (s->speech_ms >= MIN_SPEECH_MS) s->phase = MUSE_HF_RECORDING;
    }
    const bool ended = now - s->started_ms >= MAX_RECORD_MS ||
        (s->had_speech && now - s->last_speech_ms >= END_SILENCE_MS) ||
        (!s->had_speech && now - s->started_ms >= NO_SPEECH_MS);
    if (!ended) return MUSE_HF_NONE;
    if (s->speech_ms < MIN_SPEECH_MS) {
        advance(s);
        cooldown(s, now, CANCEL_COOLDOWN_MS);
        return MUSE_HF_DROP;
    }
    s->phase = MUSE_HF_BLOCKED;
    s->awaiting_reply = true;
    return MUSE_HF_END;
}

uint32_t muse_handsfree_manual_started(muse_handsfree_t *s, int64_t now)
{
    if (!s || !clock_valid(s, now) || !s->enabled) return 0;
    advance(s);
    s->last_ms = now;
    s->phase = MUSE_HF_BLOCKED;
    s->awaiting_reply = true;
    s->follow_pending = false;
    return s->generation;
}

void muse_handsfree_reply_done(muse_handsfree_t *s, uint32_t generation,
                               int64_t now, bool completed, bool allow_follow)
{
    if (!s || !generation || generation != s->generation || !s->enabled ||
        s->phase != MUSE_HF_BLOCKED || !s->awaiting_reply) return;
    if (!clock_valid(s, now)) return;
    cooldown(s, now, PLAYBACK_COOLDOWN_MS);
    s->follow_pending = completed && allow_follow;
}
