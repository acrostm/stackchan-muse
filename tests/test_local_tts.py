from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LocalTtsWorkerTests(unittest.TestCase):
    def test_actual_worker_cancellation_faults_and_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            component = ROOT / 'firmware/esp32/components'
            includes = ['-I', str(ROOT / 'tests/local_tts_fakes'),
                        '-I', str(component / 'muse'), '-I', str(component / 'minimp3/include')]
            for name, source in [('json', component / 'muse/muse_tts_json.c'),
                                 ('mp3', component / 'minimp3/src/minimp3.c')]:
                subprocess.run(['cc', '-std=c11', '-O1', *includes, '-c', str(source),
                                '-o', str(path / (name + '.o'))], check=True, capture_output=True)
            subprocess.run(['c++', '-std=c++17', '-O1', '-Wall', '-Wextra', '-Werror', '-pthread', *includes,
                            str(ROOT / 'tests/local_tts_harness.cpp'), str(component / 'muse/muse_local_tts.cpp'),
                            str(path / 'json.o'), str(path / 'mp3.o'), '-o', str(path / 'worker')],
                           check=True, capture_output=True)
            subprocess.run([str(path / 'worker'), str(component / 'muse/test_reply.mp3')],
                           check=True, timeout=15, capture_output=True)
