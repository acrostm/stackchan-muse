from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]


class NoticePolicyTests(unittest.TestCase):
    def test_schedule_boundaries_record_validation_and_unread_fifo(self):
        source = r'''
#include "muse_notice_policy.h"
#include "muse_notice_core.h"
#include <assert.h>
#include <string.h>
#include <limits.h>
int main(void) {
    muse_notice_policy_t p = muse_notice_policy_default(), copy;
    assert(muse_notice_policy_valid(&p));
    assert(!muse_notice_policy_quiet(&p, 0));
    p.quiet_enabled = true;
    assert(muse_notice_policy_quiet(&p, 0));
    for (int minute = 0; minute < 1440; ++minute) {
        int local = (minute + 480) % 1440;
        bool expected = local >= 1320 || local < 480;
        assert(muse_notice_policy_quiet(&p, MUSE_NOTICE_CLOCK_MIN + minute*60) == expected);
    }
    p.utc_offset_minute = -720;p.start_minute = 60;p.end_minute = 120;
    for (int minute = 0; minute < 1440; ++minute) {
        int local = (minute - 720 + 1440) % 1440;
        assert(muse_notice_policy_quiet(&p, MUSE_NOTICE_CLOCK_MIN + minute*60) == (local>=60&&local<120));
    }
    p.utc_offset_minute = 840;
    (void)muse_notice_policy_quiet(&p, INT64_MAX);
    p.end_minute = p.start_minute;
    assert(muse_notice_policy_quiet(&p, MUSE_NOTICE_CLOCK_MIN));
    p.quiet_enabled=false;p.muted=true;
    assert(muse_notice_policy_quiet(&p, MUSE_NOTICE_CLOCK_MIN));
    uint8_t bytes[MUSE_NOTICE_POLICY_BYTES];
    assert(muse_notice_policy_encode(&p, bytes));
    assert(muse_notice_policy_decode(&copy, bytes, sizeof(bytes)));
    assert(copy.muted && !copy.quiet_enabled && copy.utc_offset_minute==840);
    p.utc_offset_minute=-720;
    assert(muse_notice_policy_encode(&p, bytes));
    assert(muse_notice_policy_decode(&copy, bytes, sizeof(bytes)) && copy.utc_offset_minute==-720);
    assert(!muse_notice_policy_decode(&copy, bytes, sizeof(bytes)-1));
    bytes[0]=2;assert(!muse_notice_policy_decode(&copy, bytes, sizeof(bytes)));
    bytes[0]=1;bytes[1]=4;assert(!muse_notice_policy_decode(&copy, bytes, sizeof(bytes)));
    p.start_minute=1440;assert(!muse_notice_policy_encode(&p, bytes));
    assert(muse_notice_policy_quiet(&p, MUSE_NOTICE_CLOCK_MIN));
    p.start_minute=0;p.utc_offset_minute=841;assert(!muse_notice_policy_valid(&p));
    muse_notice_core_t q = {0}; char out[701];
    assert(muse_notice_core_publish_mode(&q,"one","静音一",true));
    assert(muse_notice_core_publish_mode(&q,"two","静音二",true));
    assert(!muse_notice_core_audible(&q));
    assert(muse_notice_core_publish(&q,"three","新通知"));
    assert(muse_notice_core_take(&q,out,sizeof(out)) && !strcmp(out,"新通知"));
    assert(q.count==2 && !muse_notice_core_take(&q,out,sizeof(out)));
    assert(muse_notice_core_take_mode(&q,out,sizeof(out),true) && !strcmp(out,"静音一"));
    assert(muse_notice_core_publish(&q,"four","普通通知"));
    muse_notice_core_silence(&q);
    assert(!muse_notice_core_take(&q,out,sizeof(out)) && q.count==2);
    assert(muse_notice_core_take_mode(&q,out,sizeof(out),true) && !strcmp(out,"静音二"));
    assert(muse_notice_core_take_mode(&q,out,sizeof(out),true) && !strcmp(out,"普通通知"));
    assert(!q.count && !muse_notice_core_publish(&q,"one","重复"));
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);(path/'test.c').write_text(source)
            c=ROOT/'firmware/esp32/components/muse'
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                            '-I',str(c),str(path/'test.c'),str(c/'muse_notice_policy.c'),str(c/'muse_notice_core.c'),
                            '-o',str(path/'test')],check=True)
            subprocess.run([str(path/'test')],check=True)
