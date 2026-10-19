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
int main(void) {
    assert(muse_ptt_result() == MUSE_PTT_WAIT);
    for (long duration = 0; duration <= 2000001; duration += 1) {
        muse_ptt_press(123456);
        assert(muse_ptt_result() == MUSE_PTT_WAIT);
        muse_ptt_release(123456 + duration);
        assert(muse_ptt_result() ==
               (duration > 2000000 ? MUSE_PTT_SEND : MUSE_PTT_SHORT));
    }
    muse_ptt_press(1);
    muse_ptt_cancel();
    muse_ptt_release(9000000);
    assert(muse_ptt_result() == MUSE_PTT_CANCELLED);
    muse_ptt_press(10000000);
    muse_ptt_release(14000000);
    assert(muse_ptt_result() == MUSE_PTT_SEND);
    muse_ptt_press(14000000);
    muse_ptt_release(1);
    assert(muse_ptt_result() == MUSE_PTT_SHORT);
}
''')
            binary = Path(temp) / 'test'
            subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined',
                '-I', str(ROOT / 'firmware/esp32/components/muse'),
                str(path), str(ROOT / 'firmware/esp32/components/muse/muse_ptt_guard.c'),
                '-o', str(binary),
            ], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
