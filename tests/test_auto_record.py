"""Execute the production automatic-record function with bounded fake peripherals.

The real policy core decides eligibility. Fakes do not prove VAD accuracy or
hardware playback; they check local buffering, submission and cancellation.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AutomaticRecordTests(unittest.TestCase):
    def test_voice_owner_submission_and_preemption(self):
        base = ROOT / 'firmware/esp32/components/muse'
        source = (base / 'muse_voice.c').read_text()
        function = source[source.index('static void hf_record('):source.index('static void hf_idle(')]
        harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>
#include "muse_handsfree_core.h"
#define CONFIG_MUSE_BOARD_M5STACK_STACKCHAN 0
#define MUSE_AUDIO_CHUNK 320
#define MAX_FRAMES 240000
#define MUSE_MODE_LISTENING 1
#define MUSE_WIFI_FULL 1
#define MUSE_PTT_DOWN 1
#define pdTRUE 1
#define ESP_OK 0
static atomic_bool s_hf_requested;
static muse_handsfree_t s_hf;
static int s_held_count;
static int16_t *s_rec;
static int16_t s_chunk[MUSE_AUDIO_CHUNK];
static size_t s_rec_n,s_sent;
static bool s_live,s_tried;
static int64_t now;
static int reads, speech_reads, fail_read, press_at, disable_at, stop_at;
static int uploads, replies, cancels, freed;
static uint32_t returned_press;
static bool ready, allocate, interrupt_reply, stop_reply, asleep;
typedef enum { FED, FEED_FAILED, FEED_PRESSED, FEED_STOPPED } feed_t;
static feed_t feed_result;
typedef struct {bool wake; uint32_t speech_ms;} muse_sr_result_t;
typedef struct {int type; uint32_t turn;} muse_input_event_t;
static int64_t hf_now(void) {return now;}
static bool muse_hatch_ready(void) {return ready;}
static bool can_record(void) {if(allocate)s_rec=calloc(MAX_FRAMES,sizeof(int16_t)); return s_rec!=NULL;}
static void muse_state_set_asleep(bool v) {asleep=v;}
static void muse_state_set_reply_pending(bool v) {(void)v;}
static void muse_state_set_mode(int v) {(void)v;}
static void muse_state_set_caption(const char *v) {(void)v;}
static void muse_state_set_level(float v) {(void)v;}
static float muse_audio_level(const int16_t *p,size_t n) {(void)p;(void)n;return 0;}
static bool take_stop_request(void) {return stop_at && reads>=stop_at;}
static bool press_waiting(void) {return press_at && reads>=press_at;}
static int muse_audio_read(int16_t *p,size_t n) {
 ++reads; now+=20;
 for(size_t i=0;i<n;++i)p[i]=12;
 if(disable_at && reads>=disable_at)atomic_store(&s_hf_requested,false);
 return fail_read && reads>=fail_read ? -1 : ESP_OK;
}
static int muse_sr_engine_feed(const int16_t *p,size_t n,bool wake,bool vad,muse_sr_result_t *r) {
 (void)p; assert(n==320 && !wake && vad);
 *r=(muse_sr_result_t){.speech_ms=reads<=speech_reads && reads%2==0 ? 30 : 0}; return ESP_OK;
}
static void muse_sr_engine_reset(void) {}
static void hf_cancel(void) {muse_handsfree_tick(&s_hf,now,false,0,false,true);}
static void drop_rec(void) {assert(s_rec);free(s_rec);s_rec=NULL;++freed;}
static void pre_reset(void) {}
static void go_idle(const char *s) {(void)s;}
static void muse_wifi_power(int v) {(void)v;}
static void muse_hatch_turn_begin(void) {assert(s_hf.awaiting_reply && s_hf.speech_ms>=300);++uploads;}
static feed_t feed_rest(const int16_t *p,size_t n,size_t *sent,bool yield) {
 assert(p==s_rec && n>0 && yield); *sent=n; return feed_result;
}
static bool hatch_reply(bool *delivered,uint32_t *press,bool *stopped) {
 ++replies;*delivered=true;*stopped=stop_reply;*press=interrupt_reply?77:0;return interrupt_reply;
}
static void muse_hatch_turn_cancel(void) {++cancels;}
FUNCTION
static void run_record(void) {returned_press=0;hf_record(&returned_press);}
static void setup(void) {
 assert(!s_rec); reads=uploads=replies=cancels=freed=0;returned_press=0;
 fail_read=press_at=disable_at=stop_at=s_held_count=0;
 ready=allocate=asleep=true; interrupt_reply=stop_reply=false; feed_result=FED;speech_reads=40;
 atomic_store(&s_hf_requested,true);
 muse_handsfree_init(&s_hf,true,0);
 muse_handsfree_tick(&s_hf,600,false,0,false,false);
 assert(muse_handsfree_tick(&s_hf,620,true,0,false,false)==MUSE_HF_START);now=620;
}
int main(void) {
 setup();run_record();assert(uploads==1 && replies==1 && freed==1 && !s_rec && !s_hf.follow_pending && !asleep);
 setup();speech_reads=6;run_record();assert(!uploads && freed==1 && !s_rec);
 setup();speech_reads=0;run_record();assert(!uploads && freed==1 && reads>=250);
 setup();press_at=8;run_record();assert(!uploads && freed==1 && press_waiting());
 setup();disable_at=8;run_record();assert(!uploads && freed==1);
 setup();stop_at=8;run_record();assert(!uploads && freed==1);
 setup();fail_read=8;run_record();assert(!uploads && freed==1);
 setup();ready=false;run_record();assert(!uploads && !s_rec && !freed);
 setup();allocate=false;run_record();assert(!uploads && !s_rec && !freed);
 setup();s_held_count=1;run_record();assert(!uploads && !s_rec && !freed);
 setup();feed_result=FEED_STOPPED;run_record();assert(uploads==1 && !replies && freed==1 && cancels==1);
 setup();feed_result=FEED_FAILED;run_record();assert(uploads==1 && !replies && freed==1 && cancels==1);
 setup();interrupt_reply=true;run_record();assert(returned_press==77 && freed==1 && cancels==1);
 setup();stop_reply=true;run_record();assert(!returned_press && freed==1 && cancels==1 && !s_hf.follow_pending);
 return 0;
}
'''.replace('FUNCTION', function)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.c').write_text(harness)
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-I', str(base),
                            str(path / 'test.c'), str(base / 'muse_handsfree_core.c'),
                            '-o', str(path / 'test')], check=True)
            subprocess.run([str(path / 'test')], check=True)
