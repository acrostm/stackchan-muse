"""Exercise the actual notification playback function; fake devices are not hardware evidence."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]


class NoticePlaybackTests(unittest.TestCase):
    def test_only_complete_provider_audio_and_output_drain_acknowledge(self):
        voice=(ROOT/'firmware/esp32/components/muse/muse_voice.c').read_text()
        start=voice.index('static bool speak_tts_text(')
        code=voice[start:voice.index('\n#if CONFIG_MUSE_HANDSFREE',start)]
        harness=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#define CONFIG_MUSE_BOARD_M5STACK_STACKCHAN 0
#define MUSE_AUDIO_CHUNK 16
#define MUSE_AUDIO_RATE 16000
#define MUSE_MODE_SPEAKING 4
#define ESP_OK 0
#define pdMS_TO_TICKS(n) (n)
static const char *TAG="test";
static bool s_output_tail,allowed,speaker,configured,provider_ok,never_ends,stop,ptt,stop_drain;
static int writes,chirps,drains,read_calls,cancels,write_error,drain_error;
static int64_t clock_us;
static void log_fake(const char *tag,const char *fmt,...) {(void)tag;(void)fmt;}
#define ESP_LOGI(...) log_fake(__VA_ARGS__)
#define ESP_LOGW(...) log_fake(__VA_ARGS__)
static bool take_stop_request(void){bool value=stop;stop=false;return value;}
static bool muse_notice_automatic_allowed(void){return allowed;}
static void sw_text_copy(char *out,size_t n,const char *text){snprintf(out,n,"%s",text);}
static bool muse_settings_speaker_on(void){return speaker;}
static int muse_settings_volume(void){return 70;}
static void muse_state_set_caption(const char *fmt,...) {(void)fmt;}
static void muse_state_set_reply_pending(bool pending){(void)pending;}
static void go_idle(const char *text){(void)text;}
static void muse_audio_chirp(int n){assert(n==1);++chirps;}
static void pre_reset(void){}
static bool sw_tts_start(const char *text){assert(text&&*text);return configured;}
static void sw_tts_cancel(void){++cancels;provider_ok=false;never_ends=false;}
static void muse_state_set_mode(int mode){assert(mode==MUSE_MODE_SPEAKING);}
static void muse_state_set_level(float level){assert(level==0);}
static int64_t esp_timer_get_time(void){return clock_us+=1000000;}
static bool take_down(uint32_t *turn,void *ignored){(void)ignored;if(ptt){*turn=1;ptt=false;return true;}return false;}
static size_t sw_tts_read(void *out,size_t n){assert(n>=4);++read_calls;if(read_calls==1){memset(out,0,4);return 4;}return 0;}
static int voice_write(const int16_t *p,size_t n){assert(p&&n==2);++writes;return write_error;}
static bool sw_tts_done(void){return !never_ends&&read_calls>=2;}
static bool sw_tts_succeeded(void){return provider_ok&&sw_tts_done();}
static int muse_audio_drain(int timeout){assert(timeout==300);++drains;if(stop_drain)stop=true;return drain_error;}
static void vTaskDelay(int ticks){(void)ticks;}
CODE
static void reset(void){allowed=speaker=configured=provider_ok=true;never_ends=stop=ptt=stop_drain=false;writes=chirps=drains=read_calls=cancels=write_error=drain_error=0;clock_us=0;s_output_tail=false;}
int main(void){
 bool done;uint32_t turn=0;
 reset();assert(!speak_tts_text("reply",true,&turn,false,&done));assert(done&&writes==1&&drains==1&&chirps==1);
 reset();provider_ok=false;speak_tts_text("reply",true,&turn,false,&done);assert(!done&&writes==1&&!drains);
 reset();drain_error=-1;speak_tts_text("reply",true,&turn,false,&done);assert(!done&&drains==1);
 reset();stop_drain=true;speak_tts_text("reply",true,&turn,false,&done);assert(!done);
 reset();write_error=-1;speak_tts_text("reply",true,&turn,false,&done);assert(!done&&cancels==1);
 reset();configured=false;speak_tts_text("reply",true,&turn,false,&done);assert(!done&&!writes);
 reset();never_ends=true;speak_tts_text("reply",true,&turn,false,&done);assert(!done&&cancels==1);
 reset();allowed=false;speak_tts_text("reply",true,&turn,false,&done);assert(!done&&!chirps&&!writes);
 reset();allowed=false;speak_tts_text("reply",true,&turn,true,&done);assert(done&&writes==1);
 reset();stop=true;speak_tts_text("reply",true,&turn,true,&done);assert(!done&&!chirps&&!writes);
 reset();ptt=true;assert(speak_tts_text("reply",true,&turn,false,&done));assert(!done&&turn==1&&cancels==1);
 return 0;
}
'''.replace('CODE',code)
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'test.c').write_text(harness)
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True,timeout=10)
