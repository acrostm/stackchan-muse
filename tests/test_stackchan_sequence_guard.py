from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BOARDS = ROOT / 'firmware/esp32/components/muse/boards'


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index('{', start)
    while source.find(';', start, brace) >= 0:
        start = source.index(signature, source.find(';', start, brace) + 1)
        brace = source.index('{', start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[brace:index + 1]
    raise AssertionError(f'unclosed function: {signature}')


class StackChanSequenceGuardTests(unittest.TestCase):
    def test_ui_stop_does_not_free_link_backend_buffers(self):
        voice = (ROOT / 'firmware/esp32/components/muse/muse_voice.c').read_text()
        body = function_body(voice, 'void muse_voice_request_stop(void)')
        source = r'''
#include <assert.h>
#include <stdatomic.h>
#include <stdbool.h>
static atomic_bool s_stop_requested;
static unsigned cancelled, ptt, tts, nudges, notices;
void muse_notice_cancel_pending(void) { ++notices; }
void muse_ptt_cancel_current(void) { ++ptt; }
void muse_hatch_turn_cancel(void) { ++cancelled; }
void sw_tts_cancel(void) { ++tts; }
void muse_state_nudge(void) { ++nudges; }
void muse_voice_request_stop(void)
''' + body + r'''
int main(void) {
    muse_voice_request_stop();
    assert(atomic_load(&s_stop_requested));
    assert(ptt == 1 && tts == 1 && nudges == 1 && notices == 1);
    assert(cancelled == CONFIG_MUSE_HATCH);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.c').write_text(source)
            for backend in (0, 1):
                subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                                '-fsanitize=address,undefined',
                                f'-DCONFIG_MUSE_HATCH={backend}', str(path / 'test.c'),
                                '-o', str(path / 'test')], check=True)
                subprocess.run([str(path / 'test')], check=True)

    def test_cancel_drain_before_and_after_stream_initialization(self):
        session = (
            ROOT / 'firmware/esp32/components/muse/muse_chat_session.cpp'
        ).read_text()
        body = function_body(session, 'static void drain_out(void)')
        source = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
static void *s_out;
static unsigned calls, remaining;
static size_t xStreamBufferReceive(void *stream, void *out, size_t cap, int wait) {
    assert(stream != NULL);
    (void)out; (void)cap; (void)wait;
    ++calls;
    if (!remaining) return 0;
    --remaining;
    return 2;
}
static void drain_out(void)
''' + body + r'''
int main(void) {
    drain_out(); assert(calls == 0);
    s_out = &calls; remaining = 3;
    drain_out(); assert(calls == 4 && remaining == 0);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.c').write_text(source)
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', str(path / 'test.c'),
                            '-o', str(path / 'test')], check=True)
            subprocess.run([str(path / 'test')], check=True)

    def test_stop_and_explicit_commands_invalidate_old_sequences(self):
        head = (BOARDS / 'stackchan_head.c').read_text()
        move = function_body(
            head,
            'esp_err_t stackchan_head_move_for_generation(')
        self.assertIn('generation != s_generation', move)
        self.assertIn('priority >= STACKCHAN_MOVE_COMMAND', move)
        stop = function_body(
            head,
            'uint32_t stackchan_head_stop_and_generation(void)')
        self.assertIn('stop_locked()', stop)
        self.assertIn('++s_generation', stop)
        stop_motion = function_body(head, 'static void stop_locked(void)')
        self.assertNotIn('servo_write_raw', stop_motion)
        self.assertIn('cancel_motion_locked()', stop_motion)
        torque_stop = function_body(head, 'static void cancel_motion_locked(void)')
        self.assertNotIn('servo_write_raw', torque_stop)
        self.assertIn('servo_torque(', torque_stop)

    def test_expression_and_pet_steps_use_the_sequence_token(self):
        expression = (BOARDS / 'stackchan_expression.c').read_text()
        self.assertIn('stackchan_head_ready_generation()', expression)
        self.assertIn('stackchan_head_move_for_generation(', expression)
        self.assertNotIn('stackchan_head_move(', expression)

        pet = (BOARDS / 'stackchan_pet.c').read_text()
        self.assertIn('stackchan_head_stop_and_generation()', pet)
        self.assertIn('stackchan_head_move_for_generation(', pet)
        self.assertNotIn('stackchan_head_move(', pet)

        voice = (
            ROOT / 'firmware/esp32/components/muse/muse_voice.c'
        ).read_text()
        self.assertIn('#include "boards/stackchan_head.h"', voice)
        self.assertIn('stackchan_head_cancel_reply();', voice)
        interrupted = function_body(voice, 'static bool take_down(')
        self.assertIn('stackchan_head_cancel_reply();', interrupted)

    def test_face_stop_reaches_the_voice_task(self):
        app = (ROOT / 'firmware/esp32/components/muse/muse_app.c').read_text()
        self.assertIn('muse_voice_request_stop();', app)
        voice = (
            ROOT / 'firmware/esp32/components/muse/muse_voice.c'
        ).read_text()
        self.assertIn('atomic_store_explicit(&s_stop_requested', voice)
        self.assertIn('muse_hatch_turn_cancel();', voice)
        self.assertIn('sw_tts_cancel();', voice)
        self.assertIn('FEED_STOPPED', voice)
        self.assertIn('if (stopped || delivered || interrupted)', voice)
        self.assertIn('drop_oldest();', voice)


if __name__ == '__main__':
    unittest.main()
