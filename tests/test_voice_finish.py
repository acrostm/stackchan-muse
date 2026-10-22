from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class VoiceFinishTests(unittest.TestCase):
    def test_terminal_stop_drops_note_instead_of_retrying(self):
        source = (ROOT / 'firmware/esp32/components/muse/muse_voice.c').read_text()
        function = source[source.index('static bool finish_note('):source.index('/*\n * Whether a press can record')]
        harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#define HOLD_NOTES 1
#define MUSE_MODE_THINKING 1
static int16_t *s_rec;
static int16_t token;
static size_t s_rec_n,s_sent;
static bool s_live,s_tried,s_output_tail;
static int dropped,held,cancelled;
static bool reply_stopped,reply_delivered,reply_interrupted;
typedef enum {FED,FEED_FAILED,FEED_PRESSED,FEED_STOPPED} feed_t;
static feed_t feed_result;
static void muse_hatch_turn_end(void) {}
static void muse_audio_chirp(int n) {(void)n;}
static void muse_state_set_mode(int n) {(void)n;}
static void muse_state_set_caption(const char *s) {(void)s;}
static feed_t feed_rest(const int16_t *p,size_t n,size_t *sent,bool yield) {
 (void)p;(void)n;(void)sent;assert(!yield);return feed_result;
}
static void muse_hatch_turn_cancel(void) {++cancelled;}
static void drop_rec(void) {assert(s_rec);s_rec=NULL;++dropped;}
static void hold_rec(bool tried) {(void)tried;assert(s_rec);s_rec=NULL;++held;}
static void go_idle(const char *s) {(void)s;}
static bool hatch_reply(bool *delivered,uint32_t *press,bool *stopped) {
 *delivered=reply_delivered;*press=reply_interrupted?77:0;*stopped=reply_stopped;return reply_interrupted;
}
FUNCTION
static void setup(void) {
 s_rec=&token;s_rec_n=320;s_sent=320;s_live=s_tried=true;s_output_tail=false;
 dropped=held=cancelled=0;reply_stopped=reply_delivered=reply_interrupted=false;feed_result=FED;
}
int main(void) {
 uint32_t press=0;
 setup();reply_stopped=true;assert(!finish_note(&press));assert(dropped==1 && !held && !s_rec);
 setup();reply_delivered=true;finish_note(&press);assert(dropped==1 && !held);
 setup();reply_interrupted=true;assert(finish_note(&press));assert(press==77 && dropped==1 && !held);
 setup();s_sent=0;feed_result=FEED_STOPPED;finish_note(&press);assert(dropped==1 && !held && cancelled==1);
 setup();s_sent=0;feed_result=FEED_FAILED;finish_note(&press);assert(!dropped && held==1 && cancelled==1);
 return 0;
}
'''.replace('FUNCTION', function)
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / 'test.c').write_text(harness)
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', str(p / 'test.c'),
                            '-o', str(p / 'test')], check=True)
            subprocess.run([str(p / 'test')], check=True)
