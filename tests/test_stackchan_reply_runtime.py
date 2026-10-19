from pathlib import Path
import subprocess
import tempfile
import unittest

from test_stackchan_sequence_guard import function_body

ROOT = Path(__file__).resolve().parents[1]


class ReplyRuntimeTests(unittest.TestCase):
    def test_cancelled_and_empty_completion_cannot_launch_new_gesture(self):
        session = (ROOT / 'firmware/esp32/components/muse/muse_chat_session.cpp').read_text()
        body = function_body(session, 'static void message_done(')
        source = r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstring>
#define CONFIG_MUSE_BOARD_M5STACK_STACKCHAN 1
#define TEXT_MAX 64
#define ESP_LOGI(...) ((void)0)
enum { TTS_NONE, TTS_QUEUED, M_DONE };
struct msg_t { bool done, empty; size_t len; int tts; char id[4]; };
struct { bool text; uint32_t gen, head_generation; char *texts; msg_t msgs[1]; } s_turn;
static std::atomic<uint32_t> s_gen;
static int gestures, marks;
static uint32_t received_token;
static void mark(int) { ++marks; }
static void muse_hatch_console(const char *, const char *, const char *, ...) {}
static void append_text(msg_t &m, const char *text) { m.len += strlen(text); }
static void stackchan_express_reply_for_generation(const char *text, uint32_t token) {
    assert(text && text[0]); ++gestures; received_token = token;
}
static void message_done(int i, const char *final_text)
''' + body + r'''
int main() {
    char previous[TEXT_MAX] = "old response must not be reused";
    s_turn.texts = previous; s_turn.gen = 1; s_gen = 2;
    s_turn.head_generation = 17;
    message_done(0, "late final");
    assert(gestures == 0 && marks == 0 && !s_turn.msgs[0].done);
    s_gen = 1;
    message_done(0, nullptr);
    assert(gestures == 0 && s_turn.msgs[0].empty);
    s_turn.msgs[0] = {};
    message_done(0, "current final");
    assert(gestures == 1 && received_token == 17);
    message_done(0, "duplicate final"); assert(gestures == 1);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.cpp').write_text(source)
            subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', str(path / 'test.cpp'),
                            '-o', str(path / 'test')], check=True)
            subprocess.run([str(path / 'test')], check=True)

    def test_command_carries_original_head_generation(self):
        session = (ROOT / 'firmware/esp32/components/muse/muse_chat_session.cpp').read_text()
        post = function_body(session, 'static void post(')
        self.assertIn('current_head_generation()', post)
        start = function_body(session, 'static bool turn_start(')
        self.assertIn('s_turn.head_generation = head_generation;', start)
        self.assertNotIn('current_head_generation()', start)
