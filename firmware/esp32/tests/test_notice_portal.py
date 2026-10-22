"""Execute the actual notice HTTP controls with real cJSON."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ESP32=Path(__file__).resolve().parents[1]
ROOT=ESP32.parents[1]


class NoticePortalTests(unittest.TestCase):
    def test_auth_exact_schema_persistence_error_and_explicit_read(self):
        portal=(ESP32/'components/muse/sw_portal.c').read_text()
        code=portal[portal.index('static void notice_json('):portal.index('static void handsfree_json(')]
        harness=r'''
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include "muse_notice.h"
#include "cJSON.h"
typedef struct {int content_len;const char *body,*token,*uri;size_t used;bool permit,fail_read;} httpd_req_t;
static const char *csrf="fixture";
static int calls,reads,response;
static bool available=true;
static char output[1024];
static muse_notice_status_t state;
static bool allowed(httpd_req_t *r){return r->permit;}
static int httpd_req_get_hdr_value_str(httpd_req_t *r,const char *name,char *out,size_t cap){
 assert(!strcmp(name,"X-Setup-Token"));if(!r->token||strlen(r->token)>=cap)return ESP_FAIL;strcpy(out,r->token);return ESP_OK;
}
static int httpd_req_recv(httpd_req_t *r,char *out,size_t cap){
 ++reads;if(r->fail_read)return -1;size_t n=(size_t)r->content_len-r->used;if(n>cap)n=cap;if(n>3)n=3;memcpy(out,r->body+r->used,n);r->used+=n;return (int)n;
}
static esp_err_t reply(httpd_req_t *r,const char *status,const char *body){(void)r;response=atoi(status);assert(strlen(body)<sizeof(output));strcpy(output,body);return ESP_OK;}
muse_notice_status_t muse_notice_status(void){return state;}
esp_err_t muse_notice_set_policy(const muse_notice_policy_t *p){++calls;if(!available)return ESP_FAIL;state.policy=*p;return ESP_OK;}
bool muse_notice_request_read(void){++calls;return available;}
CODE
static httpd_req_t request(const char *body){calls=reads=response=0;available=true;return (httpd_req_t){(int)strlen(body),body,csrf,"/notice-policy",0,true,false};}
static void invalid(const char *body){httpd_req_t r=request(body);notice_control(&r);assert(response==400&&!calls);}
int main(void){
 const char *valid="{\"muted\":false,\"quiet_enabled\":true,\"start_minute\":1320,\"end_minute\":480,\"utc_offset_minute\":480}";
 httpd_req_t r=request(valid);notice_control(&r);assert(response==200&&calls==1&&reads>1);assert(state.policy.quiet_enabled&&state.policy.start_minute==1320);
 r=request(valid);available=false;notice_control(&r);assert(response==503&&calls==1);
 r=request(valid);r.permit=false;notice_control(&r);assert(response==403&&!reads&&!calls);
 r=request(valid);r.token="wrong";notice_control(&r);assert(response==403&&!calls);
 r=request(valid);r.fail_read=true;notice_control(&r);assert(response==400&&!calls);
 invalid("{}");invalid("[]");invalid("null");
 invalid("{\"muted\":0,\"quiet_enabled\":true,\"start_minute\":1320,\"end_minute\":480,\"utc_offset_minute\":480}");
 invalid("{\"muted\":false,\"quiet_enabled\":true,\"start_minute\":1440,\"end_minute\":480,\"utc_offset_minute\":480}");
 invalid("{\"muted\":false,\"quiet_enabled\":true,\"start_minute\":1.5,\"end_minute\":480,\"utc_offset_minute\":480}");
 invalid("{\"muted\":false,\"quiet_enabled\":true,\"start_minute\":0,\"end_minute\":480,\"utc_offset_minute\":841}");
 invalid("{\"muted\":false,\"quiet_enabled\":true,\"start_minute\":0,\"end_minute\":480,\"end_minute\":480}");
 invalid("{\"muted\":false,\"quiet_enabled\":true,\"start_minute\":0,\"end_minute\":480,\"utc_offset_minute\":480,\"x\":1}");
 r=request("{}");r.uri="/notice-read";notice_control(&r);assert(response==202&&calls==1);
 r=request("{}");r.uri="/notice-read";available=false;notice_control(&r);assert(response==409&&calls==1);
 r=request("{\"read\":true}");r.uri="/notice-read";notice_control(&r);assert(response==400&&!calls);
 r=request("{}\0x");r.content_len=4;notice_control(&r);assert(response==400&&!calls);
 r=request(valid);r.content_len=161;notice_control(&r);assert(response==413&&!reads&&!calls);
 return 0;
}
'''.replace('CODE',code)
        cjson=ESP32/'managed_components/espressif__cjson/cJSON'
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);(p/'test.c').write_text(harness)
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-deprecated-declarations',
                            '-fsanitize=address,undefined','-I',str(cjson),'-c',str(cjson/'cJSON.c'),'-o',str(p/'cjson.o')],check=True)
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                            '-I',str(cjson),'-I',str(ROOT/'tests/notice_fakes'),'-I',str(ESP32/'components/muse'),
                            str(p/'test.c'),str(p/'cjson.o'),'-lm','-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
