import ctypes
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TtsJsonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        library = Path(cls.temp.name) / 'tts-json.so'
        compiler = shutil.which('cc')
        if not compiler:
            raise RuntimeError('C compiler required for the firmware UTF-8 harness')
        subprocess.run([compiler, '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-dynamiclib' if sys.platform == 'darwin' else '-shared', '-fPIC',
                        str(ROOT / 'firmware/esp32/components/muse/muse_tts_json.c'),
                        '-o', str(library)], check=True, capture_output=True)
        cls.library = ctypes.CDLL(str(library))
        cls.library.muse_tts_json.restype = ctypes.c_bool
        cls.library.muse_tts_json.argtypes = [ctypes.c_char_p, ctypes.c_size_t,
                                            ctypes.c_void_p, ctypes.c_size_t,
                                            ctypes.POINTER(ctypes.c_size_t)]

    def encode(self, text, limit=700, capacity=2812):
        output = ctypes.create_string_buffer(b'Z' * (capacity + 4))
        written = ctypes.c_size_t(999)
        ok = self.library.muse_tts_json(text, limit, output, capacity, ctypes.byref(written))
        self.assertEqual(output.raw[capacity:capacity+4], b'ZZZZ')
        if not ok:
            self.assertEqual(written.value, 0)
            self.assertEqual(output.value, b'')
        else:
            self.assertEqual(written.value, len(output.value))
        return ok, output.value

    def test_chinese_and_emoji_are_counted_as_characters(self):
        for text in ('中' * 701, '😀' * 701, '中' * 699 + '😀尾'):
            ok, encoded = self.encode(text.encode())
            self.assertTrue(ok)
            self.assertEqual(json.loads(encoded)['text'], text[:700])

    def test_json_escaping_cannot_inject_fields(self):
        text = '提醒："喝水"\\结束\n'
        ok, encoded = self.encode(text.encode())
        self.assertTrue(ok)
        self.assertEqual(json.loads(encoded), {'text': text.replace('\n', ' ')})

    def test_invalid_utf8_and_too_small_output_never_escape(self):
        for invalid in (b'\xc0\x80', b'\xed\xa0\x80', b'\xf0\x9f\x98', b'\xf4\x90\x80\x80', b''):
            self.assertFalse(self.encode(invalid)[0])
        for capacity in (1, 9, 12, 16):
            self.assertFalse(self.encode('中文提醒'.encode(), capacity=capacity)[0])
