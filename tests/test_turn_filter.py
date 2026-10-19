from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TurnFilterTests(unittest.TestCase):
    def test_cancelled_ids_are_deduplicated_and_bounded(self):
        source = r'''
#include "muse_turn_filter.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    muse_turn_filter_t f = {0};
    muse_turn_filter_remember(&f, "user");
    muse_turn_filter_remember(&f, "assistant");
    muse_turn_filter_remember(&f, "assistant");
    assert(muse_turn_filter_contains(&f, "user"));
    assert(muse_turn_filter_contains(&f, "assistant"));
    assert(!muse_turn_filter_contains(&f, "other"));
    muse_turn_filter_remember(&f, "");
    muse_turn_filter_remember(&f, 0);
    for (unsigned i = 0; i < MUSE_TURN_IGNORED_IDS; ++i) {
        char id[16]; snprintf(id, sizeof(id), "old-%u", i);
        muse_turn_filter_remember(&f, id);
    }
    assert(!muse_turn_filter_contains(&f, "user"));
    assert(!muse_turn_filter_contains(&f, "assistant"));
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
                str(ROOT / 'firmware/esp32/components/muse/muse_turn_filter.c'),
                '-o', str(path / 'test'),
            ], check=True)
            subprocess.run([str(path / 'test')], check=True)


if __name__ == '__main__':
    unittest.main()
