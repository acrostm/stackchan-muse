"""Run production notification state against fake NVS, clock and pthread mutexes."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]


class NoticeSettingsTests(unittest.TestCase):
    def test_persistence_errors_quiet_backlog_manual_read_and_stop(self):
        source=r'''
#include "muse_notice.h"
#include "nvs.h"
#include "freertos/semphr.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef ESP_PLATFORM
#include "esp_heap_caps.h"
void *heap_caps_malloc(size_t n,unsigned caps){assert(caps==(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));return malloc(n);}
#endif
static uint8_t saved[9], staged[9];
static bool have_saved, fail_open, fail_commit, speaker=true;
static int volume=70,nudges;
static time_t now=MUSE_NOTICE_CLOCK_MIN+14*3600;
time_t time(time_t *out) {if(out)*out=now;return now;}
void muse_state_set_reply_pending(bool value) {(void)value;}
void muse_state_nudge(void) {++nudges;}
bool muse_settings_speaker_on(void) {return speaker;}
int muse_settings_volume(void) {return volume;}
SemaphoreHandle_t xSemaphoreCreateMutex(void) {
 SemaphoreHandle_t p=malloc(sizeof(*p));assert(p&&pthread_mutex_init(p,NULL)==0);return p;
}
void vSemaphoreDelete(SemaphoreHandle_t p) {assert(!pthread_mutex_destroy(p));free(p);}
int xSemaphoreTake(SemaphoreHandle_t p,int timeout) {(void)timeout;return !pthread_mutex_lock(p);}
int xSemaphoreGive(SemaphoreHandle_t p) {return !pthread_mutex_unlock(p);}
esp_err_t nvs_open(const char *ns,int mode,nvs_handle_t *h) {
 assert(!strcmp(ns,"muse_notice")&&mode==NVS_READWRITE);if(fail_open)return ESP_FAIL;*h=1;return ESP_OK;
}
esp_err_t nvs_get_blob(nvs_handle_t h,const char *key,void *out,size_t *n) {
 assert(h==1&&!strcmp(key,"policy"));if(!have_saved)return ESP_ERR_NVS_NOT_FOUND;
 assert(*n>=sizeof(saved));memcpy(out,saved,sizeof(saved));*n=sizeof(saved);return ESP_OK;
}
esp_err_t nvs_set_blob(nvs_handle_t h,const char *key,const void *data,size_t n) {
 assert(h==1&&!strcmp(key,"policy")&&n==sizeof(staged));memcpy(staged,data,n);return ESP_OK;
}
esp_err_t nvs_commit(nvs_handle_t h) {assert(h==1);if(fail_commit)return ESP_FAIL;memcpy(saved,staged,9);have_saved=true;return ESP_OK;}
void nvs_close(nvs_handle_t h) {assert(h==1);}
static bool take(char *out,size_t cap,bool *manual) {
 const char *text=muse_notice_claim(manual);if(!text)return false;
 assert(strlen(text)<cap);strcpy(out,text);return true;
}
int main(int argc,char **argv) {
 assert(argc==2);
 if(!strcmp(argv[1],"no_psram")){
  assert(muse_notice_status().max_text_bytes==700);
  char too_long[702];memset(too_long,'x',701);too_long[701]=0;
  assert(!muse_notice_publish("limit",too_long));
  assert(!strcmp(muse_notice_status().rejection,"too_long"));
  assert(muse_notice_publish("limit","accepted retry"));return 0;
 }
 muse_notice_policy_t p=muse_notice_policy_default();
 if(!strcmp(argv[1],"bad")){have_saved=true;saved[0]=99;}
 if(!strcmp(argv[1],"io"))fail_open=true;
 if(!strcmp(argv[1],"saved")){p.quiet_enabled=true;assert(muse_notice_policy_encode(&p,saved));have_saved=true;}
 muse_notice_status_t s=muse_notice_status();
 if(!strcmp(argv[1],"bad")||!strcmp(argv[1],"io"))assert(!s.ready&&s.quiet_now);
 else {assert(s.ready);assert(s.quiet_now==p.quiet_enabled);}
 fail_open=false;
 p.quiet_enabled=true;assert(muse_notice_set_policy(&p)==ESP_OK);
 assert(muse_notice_publish("one","quiet"));
 assert(!muse_notice_pending()&&muse_notice_status().unread==1&&nudges==0);
 now=MUSE_NOTICE_CLOCK_MIN+12*3600;
 assert(muse_notice_automatic_allowed()&&!muse_notice_pending());
 assert(muse_notice_publish("two","new"));assert(muse_notice_pending()&&nudges==1);
 char text[701];bool manual=true;
 assert(take(text,sizeof(text),&manual)&&!manual&&!strcmp(text,"new"));
 muse_notice_finish(true);
 assert(!muse_notice_pending()&&muse_notice_status().unread==1);
 assert(muse_notice_request_read());assert(muse_notice_request_read());
 assert(take(text,sizeof(text),&manual)&&manual&&!strcmp(text,"quiet"));
 muse_notice_finish(true);
 assert(!muse_notice_pending()&&!muse_notice_status().unread);
 p.muted=true;assert(muse_notice_set_policy(&p)==ESP_OK);
 assert(muse_notice_publish("three","muted"));
 fail_commit=true;p.muted=false;assert(muse_notice_set_policy(&p)==ESP_FAIL);
 assert(muse_notice_status().policy.muted);fail_commit=false;
 fail_open=true;assert(muse_notice_set_policy(&p)==ESP_FAIL);fail_open=false;
 assert(!muse_notice_pending());
 p=muse_notice_policy_default();assert(muse_notice_set_policy(&p)==ESP_OK);
 assert(!muse_notice_pending());
 speaker=false;assert(muse_notice_publish("four","speaker off"));assert(!muse_notice_request_read());
 assert(!take(text,sizeof(text),&manual)&&muse_notice_status().unread==2);
 speaker=true;volume=0;assert(!muse_notice_request_read()&&!muse_notice_status().can_read);
 volume=70;assert(!muse_notice_pending()&&muse_notice_status().can_read);
 assert(muse_notice_request_read());muse_notice_cancel_pending();
 assert(!muse_notice_pending()&&!muse_notice_status().read_requested);
 assert(muse_notice_status().unread==2);
 assert(muse_notice_request_read());assert(take(text,sizeof(text),&manual)&&manual&&!strcmp(text,"muted"));
 muse_notice_finish(true);
 assert(muse_notice_request_read());assert(take(text,sizeof(text),&manual)&&manual&&!strcmp(text,"speaker off"));
 muse_notice_finish(true);
 now=0;p.quiet_enabled=true;assert(muse_notice_set_policy(&p)==ESP_OK);
 assert(muse_notice_publish("five","clock unknown"));assert(!muse_notice_status().clock_ready&&!muse_notice_pending());
 now=MUSE_NOTICE_CLOCK_MIN+12*3600;assert(!muse_notice_pending());
 p.start_minute=1440;assert(muse_notice_set_policy(&p)==ESP_ERR_INVALID_ARG);
 assert(muse_notice_request_read());assert(take(text,sizeof(text),&manual)&&manual&&!strcmp(text,"clock unknown"));
 muse_notice_finish(true);
 assert(!muse_notice_status().unread);
 p=muse_notice_policy_default();assert(muse_notice_set_policy(&p)==ESP_OK);
 assert(muse_notice_publish("active","active"));
 assert(take(text,sizeof(text),&manual));
 assert(muse_notice_status().reading&&muse_notice_status().unread==1);
 assert(muse_notice_publish("six","six"));assert(muse_notice_publish("seven","seven"));assert(muse_notice_publish("eight","eight"));
 assert(!muse_notice_publish("overflow","overflow"));
 assert(muse_notice_status().unread==4);
 muse_notice_cancel_pending();muse_notice_finish(false);
 assert(!muse_notice_status().reading&&!muse_notice_pending()&&muse_notice_status().unread==4);
 const char *expected[]={"active","six","seven","eight"};
 for(unsigned i=0;i<4;++i){assert(muse_notice_request_read());assert(take(text,sizeof(text),&manual)&&manual&&!strcmp(text,expected[i]));muse_notice_finish(true);}
 assert(muse_notice_publish("overflow","overflow"));
 assert(take(text,sizeof(text),&manual));muse_notice_finish(true);
 char *long_text=malloc(2101);assert(long_text);
 for(unsigned i=0;i<2100;i+=3){memcpy(long_text+i,"你",3);}
 long_text[2100]=0;
 assert(muse_notice_publish("long-text",long_text));
 const char *borrowed=muse_notice_claim(&manual);assert(borrowed&&strlen(borrowed)==2100&&!manual);
 muse_notice_finish(false);assert(!muse_notice_pending());
 assert(muse_notice_request_read());assert(muse_notice_claim(&manual)==borrowed&&manual);muse_notice_finish(true);free(long_text);
 unsigned prior=muse_notice_status().rejected;
 char *large=malloc(MUSE_NOTICE_TEXT_MAX+2);assert(large);memset(large,'a',MUSE_NOTICE_TEXT_MAX+1);large[MUSE_NOTICE_TEXT_MAX+1]=0;
 assert(!muse_notice_publish("large",large));free(large);
 assert(muse_notice_status().rejected==prior+1&&!strcmp(muse_notice_status().rejection,"too_long"));
 assert(!muse_notice_status().unread);
 assert(muse_notice_publish("large","valid retry"));prior=muse_notice_status().rejected;
 assert(!muse_notice_publish("large","duplicate")&&muse_notice_status().rejected==prior);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);(p/'test.c').write_text(source);c=ROOT/'firmware/esp32/components/muse'
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined',
                            '-I',str(ROOT/'tests/notice_fakes'),'-I',str(c),str(p/'test.c'),
                            *map(str,[c/'muse_notice.c',c/'muse_notice_core.c',c/'muse_notice_policy.c']),
                            '-o',str(p/'test')],check=True)
            for mode in ['missing','bad','saved','io']:
                subprocess.run([str(p/'test'),mode],check=True,timeout=10)
            for psram in (0,1):
                subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined',
                                '-DESP_PLATFORM=1',f'-DCONFIG_SPIRAM={psram}',
                                '-I',str(ROOT/'tests/notice_fakes'),'-I',str(c),str(p/'test.c'),
                                *map(str,[c/'muse_notice.c',c/'muse_notice_core.c',c/'muse_notice_policy.c']),
                                '-o',str(p/'test')],check=True)
                for mode in (['no_psram'] if not psram else ['missing','bad','saved','io']):
                    subprocess.run([str(p/'test'),mode],check=True,timeout=10)
