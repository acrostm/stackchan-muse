from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HEAD = ROOT / 'firmware/esp32/components/muse/boards/stackchan_head.c'


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[brace:index + 1]
    raise AssertionError(f'unclosed function: {signature}')


class StackChanCalibrationTests(unittest.TestCase):
    def test_factory_zeroes_require_explicit_user_confirmation(self):
        source = HEAD.read_text()
        load = function_body(source, 'static bool load_calibration(void)')
        self.assertIn('nvs_get_u8(nvs, MUSE_CAL_KEY, &muse_confirmed)', load)
        self.assertIn('muse_confirmed == 1', load)
        self.assertLess(load.index('muse_confirmed == 1'),
                        load.index('nvs_get_i32(nvs, "zero_pos_1"'))

    def test_user_calibration_commits_the_marker_with_the_centre(self):
        source = HEAD.read_text()
        save = function_body(source, 'static esp_err_t save_calibration(int yaw, int pitch)')
        first = save.index('nvs_set_i32(nvs, "zero_pos_1"')
        second = save.index('nvs_set_i32(nvs, "zero_pos_2"')
        marker = save.index('nvs_set_u8(nvs, MUSE_CAL_KEY, 1)')
        commit = save.index('nvs_commit(nvs)')
        self.assertLess(first, second)
        self.assertLess(second, marker)
        self.assertLess(marker, commit)


if __name__ == '__main__':
    unittest.main()
