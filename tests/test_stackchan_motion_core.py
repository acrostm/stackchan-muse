from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StackChanMotionCoreTests(unittest.TestCase):
    def test_priority_expiry_speed_and_clamping(self):
        source = r'''
#include "stackchan_motion_core.h"
#include <assert.h>
#include <math.h>

int main(void) {
    stackchan_motion_t m;
    int yaw, pitch;
    stackchan_motion_init(&m, 0, 0);

    assert(stackchan_motion_set_target(&m, 1400, 1100, 200,
                                       STACKCHAN_MOVE_COMMAND, 1000, 0));
    assert(m.target_yaw == 1280 && m.target_pitch == 900);
    assert(!stackchan_motion_set_target(&m, -300, 100, 1000,
                                        STACKCHAN_MOVE_PET, 2000, 0));
    assert(m.target_yaw == 1280);

    assert(stackchan_motion_tick(&m, 2010000, 0.02f, &yaw, &pitch));
    assert(yaw >= 0 && yaw <= 1280 && pitch >= 0 && pitch <= 900);

    assert(stackchan_motion_set_target(&m, 0, 0, 350,
                                       STACKCHAN_MOVE_EMERGENCY, 2020000, 1000));
    assert(!stackchan_motion_tick(&m, 3020000, 0.02f, &yaw, &pitch));
    assert(yaw > 0);

    stackchan_motion_init(&m, 0, 0);
    assert(stackchan_motion_set_target(&m, 500, 300, 100,
                                       STACKCHAN_MOVE_EXPRESSION, 4000000, 0));
    assert(stackchan_motion_tick(&m, 4020000, 0.02f, &yaw, &pitch));
    const int slow_yaw = yaw;
    stackchan_motion_init(&m, 0, 0);
    assert(stackchan_motion_set_target(&m, 500, 300, 1000,
                                       STACKCHAN_MOVE_EXPRESSION, 4000000, 0));
    assert(stackchan_motion_tick(&m, 4020000, 0.02f, &yaw, &pitch));
    assert(yaw > slow_yaw);

    stackchan_motion_init(&m, 0, 0);
    assert(stackchan_motion_set_target(&m, 500, 300, 100,
                                       STACKCHAN_MOVE_EXPRESSION, 4000000, 0));
    stackchan_motion_rebase(&m, 120, -80);
    assert(m.yaw == 120 && m.pitch == 0 && m.yaw_velocity == 0);
    assert(m.target_yaw == 500 && m.target_pitch == 300 && m.active);
    assert(stackchan_motion_tick(&m, 4020000, 0.02f, &yaw, &pitch));

    stackchan_motion_cancel(&m);
    assert(m.target_yaw == m.yaw && m.target_pitch == m.pitch);
    assert(!m.active);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / "test.c").write_text(source)
            binary = path / "test"
            subprocess.run([
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined",
                "-I", str(ROOT / "firmware/esp32/components/muse/boards"),
                str(path / "test.c"),
                str(ROOT / "firmware/esp32/components/muse/boards/stackchan_motion_core.c"),
                "-lm", "-o", str(binary),
            ], check=True)
            subprocess.run([str(binary)], check=True)

    def test_torque_reacquire_uses_live_feedback_before_enable(self):
        source = (
            ROOT / 'firmware/esp32/components/muse/boards/stackchan_head.c'
        ).read_text()
        task = source[source.index('static void motion_task(void *arg)') :]
        task = task[:task.index('\nesp_err_t stackchan_head_init')]
        feedback = task.index('read_position(SERVO_YAW_ID')
        preload = task.index('servo_write_raw(SERVO_YAW_ID')
        enable = task.index('servo_torque(SERVO_YAW_ID, true)')
        self.assertLess(feedback, preload)
        self.assertLess(preload, enable)
        self.assertIn('head is outside soft limits; motion cancelled', task)
        self.assertIn(
            'if (accepted && !s_torque_on) s_motion.active = true;', source)


if __name__ == "__main__":
    unittest.main()
