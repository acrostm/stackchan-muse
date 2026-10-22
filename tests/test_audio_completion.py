from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'firmware/esp32/components/muse'


def execute(source):
    with tempfile.TemporaryDirectory() as directory:
        p = Path(directory)
        (p / 'test.c').write_text(source)
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', str(p / 'test.c'), '-o', str(p / 'test')], check=True)
        subprocess.run([str(p / 'test')], check=True)


class AudioCompletionTests(unittest.TestCase):
    def test_board_fence_observes_dma_events_not_elapsed_time(self):
        board = (BASE / 'boards/board_m5stack_stackchan.c').read_text()
        code = board[board.index('#define AUDIO_DMA_DESCRIPTORS'):board.index('/* The AW88298 drives the speaker')]
        execute(r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#define IRAM_ATTR
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(m) ((void)(m))
#define portEXIT_CRITICAL(m) ((void)(m))
#define portENTER_CRITICAL_ISR(m) ((void)(m))
#define portEXIT_CRITICAL_ISR(m) ((void)(m))
typedef int portMUX_TYPE;
typedef int esp_err_t;
typedef void *i2s_chan_handle_t;
typedef struct {int unused;} i2s_event_data_t;
enum {ESP_OK, ESP_ERR_INVALID_STATE, ESP_ERR_TIMEOUT};
static int64_t now;
static int events_per_tick;
static int64_t esp_timer_get_time(void) {return now;}
static void vTaskDelay(int ticks);
CODE
static void vTaskDelay(int ticks) {
 assert(ticks==1);now+=10000;
 for(int i=0;i<events_per_tick;++i)audio_sent(NULL,NULL,NULL);
}
int main(void) {
 assert(audio_drain(300)==ESP_ERR_INVALID_STATE);
 s_audio_tx_ready=true; events_per_tick=0;
 assert(audio_drain(100)==ESP_ERR_TIMEOUT && now==100000);
 now=0;events_per_tick=1;s_audio_tx_sequence=0;
 assert(audio_drain(50)==ESP_ERR_TIMEOUT && s_audio_tx_sequence==5);
 now=0;s_audio_tx_sequence=0;
 assert(audio_drain(300)==ESP_OK && s_audio_tx_sequence==7 && now==70000);
 now=0;s_audio_tx_sequence=UINT32_MAX-3;
 assert(audio_drain(300)==ESP_OK && s_audio_tx_sequence==3);
 now=0;events_per_tick=2;s_audio_tx_sequence=0;
 assert(audio_drain(300)==ESP_OK && now==40000);
 assert(audio_drain(0)==ESP_ERR_TIMEOUT);
 return 0;
}
'''.replace('CODE', code))

    def test_reply_completion_requires_successful_audio_and_drain(self):
        voice = (BASE / 'muse_voice.c').read_text()
        wrapper = voice[voice.index('static esp_err_t voice_write('):voice.index('/*\n * The note being recorded')]
        code = voice[voice.index('static bool hatch_reply('):voice.index('static void go_idle(const char *caption)\n{')]
        execute(r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdarg.h>
#define CONFIG_MUSE_HANDSFREE 1
#define MUSE_AUDIO_CHUNK 320
#define MUSE_AUDIO_RATE 16000
#define MUSE_CAPTION_MAX 160
#define pdMS_TO_TICKS(n) (n)
enum {ESP_OK=0, MUSE_MODE_THINKING, MUSE_MODE_SPEAKING};
typedef enum {MUSE_HATCH_EV_NONE,MUSE_HATCH_EV_HEARD,MUSE_HATCH_EV_SENT,
 MUSE_HATCH_EV_REPLY,MUSE_HATCH_EV_DONE,MUSE_HATCH_EV_ERROR} muse_hatch_ev_t;
static const char *TAG="test";
static bool s_hf_reply_audio_complete, s_output_tail;
typedef int esp_err_t;
static int events, reads, writes, drains, cancels;
static bool audio, write_fail, drain_fail, speaker, stop_during_drain, press_during_drain, stop;
static int volume;
static void mock_log(const char *tag,const char *format,...) {(void)tag;(void)format;}
#define ESP_LOGI(...) mock_log(__VA_ARGS__)
#define ESP_LOGW(...) mock_log(__VA_ARGS__)
static int64_t esp_timer_get_time(void) {return 1000;}
static void muse_state_set_mode(int v) {(void)v;}
static void muse_state_set_caption(const char *v,...) {(void)v;}
static void muse_state_set_level(float v) {(void)v;}
static void muse_state_set_reply_pending(bool v) {(void)v;}
static void go_idle(const char *v) {(void)v;}
static bool take_stop_request(void) {bool v=stop;stop=false;return v;}
static void muse_hatch_turn_cancel(void) {++cancels;}
static bool take_down(uint32_t *p,void *wake) {
 (void)wake;if(drains && press_during_drain){*p=91;return true;}return false;
}
static muse_hatch_ev_t muse_hatch_turn_event(char *s,size_t n) {
 (void)n;s[0]=0;++events;return events==1?MUSE_HATCH_EV_REPLY:events==2?MUSE_HATCH_EV_DONE:MUSE_HATCH_EV_NONE;
}
static size_t muse_hatch_turn_read(int16_t *p,size_t n,int timeout) {
 (void)p;(void)timeout;return audio && reads++==0?n:0;
}
static bool muse_hatch_turn_caption(size_t n,char *p,size_t cap) {(void)n;(void)p;(void)cap;return false;}
static float muse_audio_level(const int16_t *p,size_t n) {(void)p;(void)n;return 0;}
static int muse_audio_write(const int16_t *p,size_t n) {(void)p;assert(n==320);++writes;return write_fail?-1:ESP_OK;}
static bool muse_settings_speaker_on(void) {return speaker;}
static int muse_settings_volume(void) {return volume;}
static int muse_audio_drain(uint32_t ms) {
 assert(writes>0 && ms==300);++drains;stop=stop_during_drain;return drain_fail?-1:ESP_OK;
}
static void vTaskDelay(int ticks) {(void)ticks;}
WRAPPER
CODE
static void setup(void) {
 events=reads=writes=drains=cancels=0;volume=50;audio=speaker=true;
 write_fail=drain_fail=stop_during_drain=press_during_drain=stop=false;
 s_hf_reply_audio_complete=true;s_output_tail=false;
}
int main(void) {
 bool delivered,stopped;uint32_t press=0;
 setup();assert(!hatch_reply(&delivered,&press,&stopped));
 assert(delivered && !stopped && s_hf_reply_audio_complete && drains==1 && s_output_tail);
 setup();drain_fail=true;hatch_reply(&delivered,&press,&stopped);assert(!s_hf_reply_audio_complete);
 setup();write_fail=true;hatch_reply(&delivered,&press,&stopped);assert(!s_hf_reply_audio_complete && !drains && cancels==1 && stopped);
 setup();audio=false;hatch_reply(&delivered,&press,&stopped);assert(!s_hf_reply_audio_complete && !drains);
 setup();speaker=false;hatch_reply(&delivered,&press,&stopped);assert(!s_hf_reply_audio_complete && !drains);
 setup();volume=0;hatch_reply(&delivered,&press,&stopped);assert(!s_hf_reply_audio_complete && !drains);
 setup();stop_during_drain=true;hatch_reply(&delivered,&press,&stopped);assert(stopped && !s_hf_reply_audio_complete && cancels==1);
 setup();press_during_drain=true;assert(hatch_reply(&delivered,&press,&stopped));assert(press==91 && !s_hf_reply_audio_complete);
 return 0;
}
'''.replace('WRAPPER', wrapper).replace('CODE', code))
