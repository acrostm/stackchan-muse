from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HandsfreeCoreTests(unittest.TestCase):
    def test_wake_vad_follow_cancellation_and_playback_suppression(self):
        source = r'''
#include "muse_handsfree_core.h"
#include <assert.h>
static int64_t now;
static muse_hf_event_t tick(muse_handsfree_t *s, bool wake, bool speech) {
    now += 20;
    return muse_handsfree_tick(s, now, wake, speech ? 20 : 0, false, false);
}
static void arm(muse_handsfree_t *s) {
    muse_handsfree_init(s, true, now);
    for (int i = 0; i < 30; ++i) tick(s, false, false);
    assert(s->phase == MUSE_HF_IDLE);
}
int main(void) {
    muse_handsfree_t s;
    muse_handsfree_init(&s, false, 0);
    assert(tick(&s, true, true) == MUSE_HF_NONE);
    arm(&s);
    assert(tick(&s, true, false) == MUSE_HF_START);
    /* No user speech: local buffer is discarded, never submitted. */
    muse_hf_event_t event = MUSE_HF_NONE;
    for (int i = 0; i < 250 && event == MUSE_HF_NONE; ++i) event = tick(&s, false, false);
    assert(event == MUSE_HF_DROP);
    arm(&s);
    assert(tick(&s, true, false) == MUSE_HF_START);
    for (int i = 0; i < 30; ++i) assert(tick(&s, false, true) == MUSE_HF_NONE);
    assert(s.phase == MUSE_HF_RECORDING);
    for (int i = 0; i < 39; ++i) assert(tick(&s, false, false) == MUSE_HF_NONE);
    assert(tick(&s, false, false) == MUSE_HF_END);
    uint32_t token = s.generation;
    /* A completed HTTP request alone is not allowed to open follow listening. */
    for (int i = 0; i < 5; ++i) assert(tick(&s, true, true) == MUSE_HF_NONE);
    assert(s.phase == MUSE_HF_BLOCKED);
    muse_handsfree_reply_done(&s, token, now, true, true);
    for (int i = 0; i < 30; ++i) assert(tick(&s, true, true) == MUSE_HF_NONE);
    assert(s.phase == MUSE_HF_FOLLOW);
    assert(tick(&s, false, true) == MUSE_HF_START);
    uint32_t cancelled = s.generation;
    assert(muse_handsfree_tick(&s, now += 20, false, false, false, true) == MUSE_HF_DROP);
    muse_handsfree_reply_done(&s, cancelled, now, true, true);
    assert(!s.follow_pending && s.phase == MUSE_HF_COOLDOWN);
    for (int i = 0; i < 50; ++i) tick(&s, true, true);
    assert(s.phase == MUSE_HF_IDLE);
    assert(tick(&s, true, false) == MUSE_HF_START);
    now += 500;
    assert(muse_handsfree_tick(&s, now, false, true, false, false) == MUSE_HF_DROP);
    arm(&s);
    assert(muse_handsfree_tick(&s, now += 20, true, true, true, false) == MUSE_HF_NONE);
    assert(s.phase == MUSE_HF_BLOCKED);
    assert(tick(&s, true, true) == MUSE_HF_NONE);
    for (int i = 0; i < 30; ++i) assert(tick(&s, true, true) == MUSE_HF_NONE);
    assert(s.phase == MUSE_HF_IDLE);
    uint32_t manual = muse_handsfree_manual_started(&s, now);
    assert(manual);
    assert(muse_handsfree_enable(&s, false, now) == MUSE_HF_DROP);
    muse_handsfree_reply_done(&s, manual, now, true, true);
    assert(s.phase == MUSE_HF_OFF && !s.follow_pending);
    arm(&s);
    assert(tick(&s, true, false) == MUSE_HF_START);
    assert(muse_handsfree_tick(&s, now - 1, true, true, false, false) == MUSE_HF_DROP);
    assert(!s.enabled && s.phase == MUSE_HF_OFF);
    arm(&s);
    assert(tick(&s, true, false) == MUSE_HF_START);
    for (int i = 0; i < 6; ++i) tick(&s, false, false);
    assert(tick(&s, false, true) == MUSE_HF_NONE);
    for (int i = 0; i < 39; ++i) assert(tick(&s, false, false) == MUSE_HF_NONE);
    assert(tick(&s, false, false) == MUSE_HF_DROP); /* short noise burst */
    arm(&s);
    assert(tick(&s, true, false) == MUSE_HF_START);
    event = MUSE_HF_NONE;
    for (int i = 0; i < 750 && event == MUSE_HF_NONE; ++i) event = tick(&s, false, true);
    assert(event == MUSE_HF_END); /* fifteen-second hard recording cap */
    token = s.generation;
    muse_handsfree_reply_done(&s, token, now, true, true);
    for (int i = 0; i < 430; ++i) tick(&s, false, false);
    assert(s.phase == MUSE_HF_IDLE);
    assert(tick(&s, false, true) == MUSE_HF_NONE); /* expired follow window */
    token = muse_handsfree_manual_started(&s, now);
    assert(token);
    assert(muse_handsfree_tick(&s, now - 1, false, 0, false, false) == MUSE_HF_DROP);
    assert(!s.enabled);
    arm(&s);
    assert(tick(&s, true, false) == MUSE_HF_START);
    for (int i = 0; i < 6; ++i) tick(&s, false, false);
    /* A delayed classifier decision only credits its actual 20 ms of PCM. */
    for (int i = 0; i < 3; ++i)
        assert(muse_handsfree_tick(&s, now += 200, false, 20, false, false) == MUSE_HF_NONE);
    assert(s.speech_ms == 60 && s.phase == MUSE_HF_WAIT_SPEECH);
    for (int i = 0; i < 20; ++i)
        assert(muse_handsfree_tick(&s, now, false, 20, false, false) == MUSE_HF_NONE);
    assert(s.speech_ms == 60);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.c').write_text(source)
            base = ROOT / 'firmware/esp32/components/muse'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-I', str(base),
                            str(path / 'test.c'), str(base / 'muse_handsfree_core.c'),
                            '-o', str(path / 'test')], check=True)
            subprocess.run([str(path / 'test')], check=True)
