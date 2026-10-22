"""Execute the production control handler with real cJSON and fake HTTP I/O."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ESP32 = Path(__file__).resolve().parents[1]


class HandsfreePortalTests(unittest.TestCase):
    def test_auth_schema_and_queued_state(self):
        portal = (ESP32 / 'components/muse/sw_portal.c').read_text()
        code = portal[portal.index('static void handsfree_json('):portal.index('static esp_err_t session(')]
        harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include "cJSON.h"
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
typedef struct {int content_len;const char *body,*token;size_t used;bool permit,fail_read;} httpd_req_t;
typedef struct {bool supported,requested,enabled;const char *state;} muse_voice_handsfree_status_t;
static const char *csrf="fixture-token";
static int calls,reads;
static bool available,requested;
static char output[512];
static int response;
static bool allowed(httpd_req_t *r) {return r->permit;}
static esp_err_t httpd_req_get_hdr_value_str(httpd_req_t *r,const char *key,char *out,size_t cap) {
 assert(!strcmp(key,"X-Setup-Token"));
 if(!r->token || strlen(r->token)>=cap)return ESP_FAIL;
 strcpy(out,r->token);return ESP_OK;
}
static int httpd_req_recv(httpd_req_t *r,char *out,size_t cap) {
 ++reads;if(r->fail_read)return -1;
 size_t left=(size_t)r->content_len-r->used,n=left<cap?left:cap;if(n>3)n=3;
 memcpy(out,r->body+r->used,n);r->used+=n;return (int)n;
}
static esp_err_t reply(httpd_req_t *r,const char *status,const char *body) {
 (void)r;response=atoi(status);assert(strlen(body)<sizeof(output));strcpy(output,body);return ESP_OK;
}
static bool muse_voice_set_handsfree(bool value) {++calls;if(!available)return false;requested=value;return true;}
static muse_voice_handsfree_status_t muse_voice_handsfree_status(void) {
 return (muse_voice_handsfree_status_t){true,requested,false,requested?"starting":"off"};
}
CODE
static httpd_req_t request(const char *body) {
 calls=reads=response=0;available=true;requested=false;output[0]=0;
 return (httpd_req_t){(int)strlen(body),body,csrf,0,true,false};
}
static void invalid(const char *body) {
 httpd_req_t r=request(body);handsfree_control(&r);assert(response==400 && !calls);
}
int main(void) {
 httpd_req_t r=request("{\"enabled\":true}");handsfree_control(&r);assert(response==202 && calls==1 && requested && reads>1);
 cJSON *status=cJSON_Parse(output);assert(cJSON_GetArraySize(status)==4);
 assert(cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(status,"requested")));
 assert(!strcmp(cJSON_GetObjectItemCaseSensitive(status,"state")->valuestring,"starting"));cJSON_Delete(status);
 r=request("{\"enabled\":false}");handsfree_control(&r);assert(response==202 && calls==1 && !requested);
 r=request("{\"enabled\":true}");r.permit=false;handsfree_control(&r);assert(response==403 && !calls && !reads);
 r=request("{\"enabled\":true}");r.token="wrong";handsfree_control(&r);assert(response==403 && !calls && !reads);
 r=request("{\"enabled\":true}");r.token=NULL;handsfree_control(&r);assert(response==403 && !calls);
 r=request("{\"enabled\":true}");r.fail_read=true;handsfree_control(&r);assert(response==400 && !calls);
 r=request("{\"enabled\":true}");available=false;handsfree_control(&r);assert(response==503 && calls==1 && !requested);
 invalid("{}");invalid("[]");invalid("null");invalid("{\"enabled\":1}");invalid("{\"enabled\":\"true\"}");
 invalid("{\"enabled\":null}");invalid("{\"Enabled\":true}");invalid("{\"enabled\":true,\"x\":1}");
 invalid("{\"enabled\":true}x");invalid("{\"enabled\":true,\"enabled\":false}");
 r=request("{\"enabled\":true}\0garbage");r.content_len=24;handsfree_control(&r);assert(response==400 && !calls);
 r=request("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx");handsfree_control(&r);assert(response==413 && !calls);
 return 0;
}
'''.replace('CODE', code)
        cjson = ESP32 / 'managed_components/espressif__cjson/cJSON'
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / 'test.c').write_text(harness)
            # Keep our handler warning-clean; macOS deprecates sprintf used
            # by the unmodified pinned cJSON dependency.
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-Wno-deprecated-declarations', '-fsanitize=address,undefined',
                            '-I', str(cjson), '-c', str(cjson / 'cJSON.c'),
                            '-o', str(p / 'cjson.o')], check=True)
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-I', str(cjson),
                            str(p / 'test.c'), str(p / 'cjson.o'), '-lm', '-o', str(p / 'test')], check=True)
            subprocess.run([str(p / 'test')], check=True)
