from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PttGuardTests(unittest.TestCase):
    def test_exact_two_second_boundary_cancel_and_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'test.c'
            path.write_text(r'''
#include "muse_ptt_guard.h"
#include <assert.h>
#include <stdint.h>
int main(void) {
    assert(muse_ptt_result(0) == MUSE_PTT_WAIT);
    for (long duration = 0; duration <= 2000001; duration += 1) {
        uint32_t turn = muse_ptt_press(123456);
        assert(turn);
        assert(muse_ptt_result(turn) == MUSE_PTT_WAIT);
        muse_ptt_release_current(123456 + duration);
        assert(muse_ptt_result(turn) ==
               (duration > 2000000 ? MUSE_PTT_SEND : MUSE_PTT_SHORT));
        muse_ptt_retire(turn);
    }
    uint32_t cancelled = muse_ptt_press(1);
    muse_ptt_cancel_current();
    muse_ptt_release_current(9000000);
    uint32_t next = muse_ptt_press(10000000);
    muse_ptt_release_current(14000000);
    /* The second press must not erase the first turn's cancellation. */
    assert(cancelled && next && cancelled != next);
    assert(muse_ptt_result(cancelled) == MUSE_PTT_CANCELLED);
    assert(muse_ptt_result(next) == MUSE_PTT_SEND);
    muse_ptt_retire(cancelled);
    assert(muse_ptt_result(cancelled) == MUSE_PTT_WAIT);
    assert(muse_ptt_result(next) == MUSE_PTT_SEND);
    muse_ptt_retire(next);
    uint32_t held = muse_ptt_press(15000000);
    assert(muse_ptt_should_submit(muse_ptt_result(held), false, true));
    muse_ptt_cancel_current();
    assert(!muse_ptt_should_submit(muse_ptt_result(held), false, true));
    muse_ptt_retire(held);
    assert(!muse_ptt_should_submit(MUSE_PTT_CANCELLED, true, false));
    assert(muse_ptt_should_submit(MUSE_PTT_SEND, false, false));
    assert(muse_ptt_should_submit(MUSE_PTT_WAIT, true, false));
    assert(!muse_ptt_should_submit(MUSE_PTT_SHORT, false, false));
    uint32_t ids[16];
    for (unsigned i = 0; i < 16; ++i) assert((ids[i] = muse_ptt_press(i)));
    assert(muse_ptt_press(20) == 0); /* Bounded fail-closed history. */
    for (unsigned i = 0; i < 16; ++i) muse_ptt_retire(ids[i]);
    assert(muse_ptt_press(30));
    muse_ptt_release_current(30000030);
}
''')
            binary = Path(temp) / 'test'
            subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined',
                '-I', str(ROOT / 'tests/ptt_guard_stubs'),
                '-I', str(ROOT / 'firmware/esp32/components/muse'),
                str(path), str(ROOT / 'firmware/esp32/components/muse/muse_ptt_guard.c'),
                '-o', str(binary),
            ], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
