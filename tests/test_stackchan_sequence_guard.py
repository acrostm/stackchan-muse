from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BOARDS = ROOT / 'firmware/esp32/components/muse/boards'


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
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
        self.assertIn('servo_torque(', stop_motion)

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
        self.assertIn('stackchan_head_stop();', voice)

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
