from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class NoticeCoreTests(unittest.TestCase):
    def test_dedupe_bounded_queue_fifo_and_utf8_take(self):
        source = r'''
#include "muse_notice_core.h"
#include <assert.h>
#include <string.h>
int main(void) {
    muse_notice_core_t q = {0};
    char text[MUSE_NOTICE_TEXT_MAX + 1];
    assert(muse_notice_core_publish(&q, "one", "第一条"));
    assert(!muse_notice_core_publish(&q, "one", "重复事件"));
    assert(muse_notice_core_publish(&q, "two", "第二条"));
    assert(muse_notice_core_publish(&q, "three", "第三条"));
    assert(muse_notice_core_publish(&q, "four", "第四条"));
    assert(!muse_notice_core_publish(&q, "five", "队列已满"));
    assert(muse_notice_core_take(&q, text, sizeof(text)) && !strcmp(text, "第一条"));
    assert(muse_notice_core_take(&q, text, sizeof(text)) && !strcmp(text, "第二条"));
    assert(muse_notice_core_publish(&q, "five", "队列有空间"));
    char tiny[5];
    unsigned count = q.count;
    assert(!muse_notice_core_take(&q, tiny, sizeof(tiny)) && q.count == count);
    assert(muse_notice_core_take(&q, text, sizeof(text)) && !strcmp(text, "第三条"));
    strcpy(tiny, "ok");
    for (const unsigned char *p = (const unsigned char *)tiny; *p; ++p)
        assert((*p & 0xc0) != 0x80 || p > (const unsigned char *)tiny);
    muse_notice_core_clear(&q);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / 'test.c').write_text(source)
            subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined',
                '-I', str(ROOT / 'firmware/esp32/components/muse'),
                str(path / 'test.c'),
                str(ROOT / 'firmware/esp32/components/muse/muse_notice_core.c'),
                '-o', str(path / 'test'),
            ], check=True)
            subprocess.run([str(path / 'test')], check=True)


if __name__ == '__main__':
    unittest.main()
