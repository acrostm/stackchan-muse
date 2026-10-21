from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from companion.face_tracking import detect_faces, main


class Capture:
    def __init__(self, opened=True, readable=True):
        self.opened, self.readable = opened, readable
        self.released = False

    def isOpened(self):
        return self.opened

    def set(self, *_):
        return True

    def read(self):
        return self.readable, SimpleNamespace(shape=(480, 640, 3))

    def release(self):
        self.released = True


def fake_cv(capture):
    classifier = SimpleNamespace(empty=lambda: False,
                                 detectMultiScale=lambda *a, **k: [(400, 100, 80, 80)])
    return SimpleNamespace(data=SimpleNamespace(haarcascades='/fake/'),
                           CascadeClassifier=lambda _: classifier,
                           VideoCapture=lambda _: capture,
                           CAP_PROP_FRAME_WIDTH=3, CAP_PROP_FRAME_HEIGHT=4,
                           CAP_PROP_BUFFERSIZE=38, COLOR_BGR2GRAY=6,
                           cvtColor=lambda frame, _: frame, equalizeHist=lambda frame: frame,
                           error=RuntimeError)


class Clock:
    value = 0

    def now(self):
        self.value += .03
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class FaceTrackingCLITests(unittest.TestCase):
    def test_default_camera_flow_produces_targets_without_serial(self):
        capture, clock = Capture(), Clock()
        output = StringIO()
        with patch.dict('sys.modules', {'cv2': fake_cv(capture), 'serial': None}), \
             patch('companion.face_tracking.time.monotonic', clock.now), \
             patch('companion.face_tracking.time.sleep', clock.sleep), redirect_stdout(output):
            self.assertEqual(main(['--seconds', '.5']), 0)
        self.assertIn('"ttl_ms": 500', output.getvalue())
        self.assertTrue(capture.released)

    def test_camera_permission_and_read_failure_release_resources(self):
        for capture in [Capture(opened=False), Capture(readable=False)]:
            with patch.dict('sys.modules', {'cv2': fake_cv(capture)}), redirect_stderr(StringIO()):
                self.assertEqual(main(['--seconds', '.5']), 1)
            self.assertTrue(capture.released)

    def test_move_requires_explicit_port(self):
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
            main(['--move'])
        self.assertEqual(error.exception.code, 2)

    def test_detector_normalizes_and_rejects_invalid_rectangles(self):
        capture = Capture()
        cv = fake_cv(capture)
        detector = SimpleNamespace(detectMultiScale=lambda *a, **k:
                                   [(0, 0, 320, 240), (-1, 0, 50, 50), (600, 0, 100, 50)])
        faces = detect_faces(cv, detector, capture.read()[1])
        self.assertEqual(len(faces), 1)
        self.assertEqual(faces[0].center, (.25, .25))
