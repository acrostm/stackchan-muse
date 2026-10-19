from pathlib import Path
import subprocess
import tempfile
import unittest

from test_stackchan_sequence_guard import function_body

ROOT = Path(__file__).resolve().parents[1]
BOARDS = ROOT / 'firmware/esp32/components/muse/boards'


class TrackingDeviceTests(unittest.TestCase):
    def test_production_tracking_lease_and_parser(self):
        head = (BOARDS / 'stackchan_head.c').read_text()
        signatures = [
            'static void cancel_motion_locked(void)\n{',
            'static void stop_locked(void)\n{',
            'void stackchan_head_cancel_reply(',
            'static void tracking_expire_locked(',
            'uint32_t stackchan_head_track_begin(',
            'esp_err_t stackchan_head_track_stop(',
            'esp_err_t stackchan_head_track(',
            'esp_err_t stackchan_head_move_for_generation(',
            'static bool parse_tracking(',
        ]
        bodies = []
        for signature in signatures:
            start = head.index(signature)
            brace = head.index('{', start)
            declaration = head[start:brace]
            bodies.append(declaration + function_body(head, signature))
        source = r'''
#include <assert.h>
#include <errno.h>
#include <stdlib.h>
#include <stdint.h>
#include "stackchan_motion_core.h"
typedef int esp_err_t;
typedef int TaskHandle_t;
enum { ESP_OK, ESP_ERR_NOT_FOUND, ESP_ERR_INVALID_ARG, ESP_ERR_INVALID_STATE };
#define portMAX_DELAY 0
#define SERVO_YAW_ID 1
#define SERVO_PITCH_ID 2
static int s_lock = 1, s_motion_task = 1;
static bool s_present, s_calibrated, s_torque_on;
static uint32_t s_generation = 1, s_tracking_generation, s_tracking_sequence;
static int64_t s_tracking_deadline_us, s_rest_since_us, now;
static int s_last_yaw, s_last_pitch;
static stackchan_motion_t s_motion;
static void xSemaphoreTake(int lock, int timeout) { (void)lock; (void)timeout; }
static void xSemaphoreGive(int lock) { (void)lock; }
static void xTaskNotifyGive(int task) { (void)task; }
static int64_t esp_timer_get_time(void) { return now; }
static uint32_t esp_random(void) { static uint32_t token = 100; return ++token; }
static void servo_torque(int id, bool on) { (void)id; assert(!on); }
''' + '\n'.join(bodies) + r'''
int main(void) {
    stackchan_motion_init(&s_motion, 0, 0);
    assert(stackchan_head_track_begin() == 0);
    s_present = true;
    assert(stackchan_head_track_begin() == 0);
    s_calibrated = true;
    uint32_t token = stackchan_head_track_begin();
    assert(token && token == s_tracking_generation);
    assert(stackchan_head_track(token, 1, 100, 100, 500) == ESP_OK);
    assert(s_motion.active && s_motion.priority == STACKCHAN_MOVE_TRACKING);
    assert(s_tracking_deadline_us == 500000);
    uint32_t old_reply_generation = s_generation;
    stackchan_head_cancel_reply();
    assert(s_generation != old_reply_generation);
    assert(s_tracking_generation == token && s_motion.active);
    assert(stackchan_head_move_for_generation(0, 0, 300,
        STACKCHAN_MOVE_EXPRESSION, 0, old_reply_generation) == ESP_ERR_INVALID_STATE);
    assert(stackchan_head_track(token, 2, 100, 100, 500) == ESP_OK);
    assert(stackchan_head_track(token, 1, 200, 100, 500) == ESP_ERR_INVALID_STATE);
    assert(stackchan_head_track(token, 3, 601, 100, 500) == ESP_ERR_INVALID_ARG);
    assert(s_motion.target_yaw == 100);
    now = 500000;
    const uint32_t before_expiry = s_generation;
    tracking_expire_locked(now);
    assert(s_generation != before_expiry);
    assert(!s_motion.active && !s_tracking_generation && s_generation != token);
    assert(stackchan_head_track(token, 2, 200, 100, 500) == ESP_ERR_INVALID_STATE);
    token = stackchan_head_track_begin();
    assert(stackchan_head_track(token, 1, 100, 100, 500) == ESP_OK);
    assert(stackchan_head_move_for_generation(3, 3, 300, STACKCHAN_MOVE_COMMAND, 0, 0) == ESP_OK);
    assert(!s_tracking_generation);
    assert(stackchan_head_track_stop(token) == ESP_ERR_INVALID_STATE);
    assert(stackchan_head_track(token, 2, 200, 100, 500) == ESP_ERR_INVALID_STATE);
    now += 2000000;
    tracking_expire_locked(now);
    assert(s_motion.active && s_motion.priority == STACKCHAN_MOVE_COMMAND);
    assert(stackchan_head_track_begin() == 0);
    stackchan_motion_cancel(&s_motion);
    token = stackchan_head_track_begin();
    assert(stackchan_head_track_stop(token) == ESP_OK);
    assert(!s_motion.active && !s_tracking_generation && s_generation != token);
    int64_t fields[6];
    assert(parse_tracking("1,4294967295,2,-600,600,1000", fields));
    assert(fields[1] == UINT32_MAX && fields[3] == -600);
    const char *bad[] = {"2,1,1,0,0,500", "1,1,1,0,0,0", "1,1,1,601,0,500",
        "1,1,1,0,0,500junk", "1,1,1,0,0,500,6", "1,1,1,0,0",
        "1,9999999999999999999999,1,0,0,500", "1,-1,1,0,0,500"};
    for (unsigned i = 0; i < sizeof(bad)/sizeof(bad[0]); ++i)
        assert(!parse_tracking(bad[i], fields));
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.c').write_text(source)
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-I', str(BOARDS),
                            str(path / 'test.c'), str(BOARDS / 'stackchan_motion_core.c'),
                            '-lm', '-o', str(path / 'test')], check=True)
            subprocess.run([str(path / 'test')], check=True)
