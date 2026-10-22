"""Run production full-text storage, UTF-8 fragments and allocation ownership."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]


class NoticeLongTextTests(unittest.TestCase):
    def test_complete_text_fragments_bounds_allocation_failure_and_owned_return(self):
        source=r'''
#include "muse_notice_core.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
static unsigned live,allocations;
static bool fail;
static void *allocate(size_t n){if(fail)return NULL;assert(n<=MUSE_NOTICE_TEXT_MAX+1);void *p=malloc(n);assert(p);++live;++allocations;return p;}
static void release(void *p){if(p){assert(live);--live;free(p);}}
int main(void){
 muse_notice_core_t q={.allocate=allocate,.release=release};
 char *original=malloc(MUSE_NOTICE_TEXT_MAX+2),*rebuilt=malloc(MUSE_NOTICE_TEXT_MAX+1);assert(original&&rebuilt);
 const char *unit="你好🙂";assert(strlen(unit)==10);
 for(unsigned i=0;i<16380;i+=10)memcpy(original+i,unit,10);
 original[16380]=0;
 assert(muse_notice_core_publish(&q,"long",original)&&live==1);
 char *owned=muse_notice_core_claim(&q,false);assert(owned&&strlen(owned)==16380);
 char part[MUSE_NOTICE_SPEECH_BYTES+1];size_t offset=0;unsigned pieces=0;
 while(owned[offset]){size_t n=muse_notice_text_chunk(owned,offset,part,sizeof(part));assert(n&&n<=700);memcpy(rebuilt+offset,part,n);offset+=n;++pieces;}
 rebuilt[offset]=0;assert(offset==16380&&pieces==24&&!strcmp(rebuilt,original));
 assert(!muse_notice_text_chunk(owned,1,part,sizeof(part)));
 assert(!muse_notice_text_chunk(owned,offset+1,part,sizeof(part)));
 unsigned before=allocations;assert(muse_notice_core_return_owned(&q,owned));assert(allocations==before&&!muse_notice_core_audible(&q));
 owned=muse_notice_core_claim(&q,true);muse_notice_core_release(&q,owned);assert(!live);
 memset(original,'x',MUSE_NOTICE_TEXT_MAX);original[MUSE_NOTICE_TEXT_MAX]=0;
 assert(muse_notice_core_publish(&q,"max",original));owned=muse_notice_core_claim(&q,false);assert(strlen(owned)==MUSE_NOTICE_TEXT_MAX);muse_notice_core_release(&q,owned);
 original[MUSE_NOTICE_TEXT_MAX]='x';original[MUSE_NOTICE_TEXT_MAX+1]=0;
 assert(!muse_notice_core_publish(&q,"retry",original)&&q.last_result==MUSE_NOTICE_TOO_LONG&&!q.count);
 assert(muse_notice_core_publish(&q,"retry","short"));muse_notice_core_clear(&q);assert(!live);
 const char *invalid[]={"\xed\xa0\x80","\xf4\x90\x80\x80","\xc0\xaf","\xe4\xbd"};
 for(unsigned i=0;i<4;++i)assert(!muse_notice_core_publish(&q,NULL,invalid[i])&&q.last_result==MUSE_NOTICE_INVALID_TEXT);
 fail=true;assert(!muse_notice_core_publish(&q,"allocation","retry")&&q.last_result==MUSE_NOTICE_NO_MEMORY);
 fail=false;assert(muse_notice_core_publish(&q,"allocation","retry"));owned=muse_notice_core_claim(&q,false);q.reserved=1;
 assert(muse_notice_core_publish(&q,"a","a"));assert(muse_notice_core_publish(&q,"b","b"));assert(muse_notice_core_publish(&q,"c","c"));
 assert(!muse_notice_core_publish(&q,"overflow","overflow")&&q.last_result==MUSE_NOTICE_FULL&&live==4);
 assert(!muse_notice_core_publish(&q,"a","a")&&q.last_result==MUSE_NOTICE_DUPLICATE);
 before=allocations;assert(muse_notice_core_return_owned(&q,owned)&&allocations==before);q.reserved=0;
 char tiny[2];assert(!muse_notice_core_take_mode(&q,tiny,sizeof(tiny),true)&&q.count==4);
 muse_notice_core_clear(&q);assert(!live);
 free(original);free(rebuilt);return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'test.c').write_text(source);c=ROOT/'firmware/esp32/components/muse'
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                            '-I',str(c),str(p/'test.c'),str(c/'muse_notice_core.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True,timeout=10)
