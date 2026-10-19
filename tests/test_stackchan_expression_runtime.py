"""Execute the production gesture task with a stop injected during its delay."""
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BOARDS = ROOT / "firmware/esp32/components/muse/boards"


class ExpressionRuntimeTests(unittest.TestCase):
    def test_stop_during_each_gesture_delay_prevents_later_moves(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            headers = {
                "driver/i2c_master.h": "typedef void *i2c_master_bus_handle_t;\n",
                "esp_err.h": "typedef int esp_err_t;\n#define ESP_OK 0\n",
                "esp_log.h": "#define ESP_LOGW(...) ((void)0)\n",
                "freertos/FreeRTOS.h": "#define pdPASS 1\n#define pdMS_TO_TICKS(ms) (ms)\n",
                "freertos/task.h": """
void vTaskDelay(unsigned ticks);
void vTaskDelete(void *task);
int xTaskCreate(void (*fn)(void *), const char *, unsigned, void *, unsigned, void *);
""",
            }
            for name, content in headers.items():
                path = temp / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            # Include the production task in this translation unit so the fake
            # scheduler can run it synchronously and inspect its busy flag.
            source = r'''
#include <assert.h>
#include <stddef.h>
#include "stackchan_expression.c"
static uint32_t generation;
static int delays, stop_at, moves, moves_at_stop;
static bool fail_create;
static stackchan_expression_t selected;
uint32_t stackchan_head_ready_generation(void) { return generation; }
esp_err_t stackchan_head_move_for_generation(int y, int p, int speed,
    stackchan_move_priority_t priority, int64_t ttl, uint32_t token) {
    (void)y; (void)p; (void)speed; (void)priority; (void)ttl;
    if (token != generation) return -1;
    ++moves;
    return ESP_OK;
}
stackchan_expression_t stackchan_expression_plan(const char *text) {
    (void)text; return selected;
}
void vTaskDelay(unsigned ticks) {
    (void)ticks;
    if (++delays == stop_at) { ++generation; moves_at_stop = moves; }
}
void vTaskDelete(void *task) { (void)task; }
int xTaskCreate(void (*fn)(void *), const char *name, unsigned stack,
    void *arg, unsigned priority, void *handle) {
    (void)name; (void)stack; (void)priority; (void)handle;
    if (fail_create) return 0;
    fn(arg); return pdPASS;
}
int main(void) {
    const int delay_count[] = {1, 3, 1, 2, 1};
    for (int expression = 0; expression < 5; ++expression) {
        selected = (stackchan_expression_t)expression;
        for (int stop = 1; stop <= delay_count[expression]; ++stop) {
            generation = 1; delays = moves = moves_at_stop = 0; stop_at = stop;
            stackchan_express_reply("test");
            assert(moves_at_stop > 0 && moves == moves_at_stop);
            assert(!atomic_load(&s_busy));
        }
        generation = 1; delays = moves = 0; stop_at = 0;
        stackchan_express_reply("test");
        assert(moves > 1 && !atomic_load(&s_busy));
    }
    generation = 0; moves = 0;
    stackchan_express_reply("uncalibrated"); assert(moves == 0);
    generation = 1; fail_create = true;
    stackchan_express_reply("allocation failure");
    assert(!atomic_load(&s_busy) && moves == 0);
    return 0;
}
'''
            (temp / "runtime.c").write_text(source)
            binary = temp / "runtime"
            subprocess.run([
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-Wno-unused-variable", "-fsanitize=address,undefined",
                "-I", str(temp), "-I", str(BOARDS),
                str(temp / "runtime.c"), "-o", str(binary),
            ], check=True)
            subprocess.run([str(binary)], check=True)
