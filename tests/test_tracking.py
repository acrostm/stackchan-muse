import math
import unittest

from companion.tracking import Face, FaceTracker, TrackingConfig


class TrackingTests(unittest.TestCase):
    def test_largest_face_then_nearby_face_without_identity(self):
        tracker = FaceTracker()
        tracker.enable(0)
        tracker.update([Face(.1, .2, .1, .1), Face(.6, .2, .2, .2)], .2, .2)
        self.assertGreater(tracker.yaw, 0)
        before = tracker.yaw
        # A new larger face is far away; keep the small nearby target.
        tracker.update([Face(.05, .1, .4, .4), Face(.65, .2, .1, .1)], .4, .4)
        self.assertGreater(tracker.yaw, before)

    def test_deadzone_and_camera_bias(self):
        tracker = FaceTracker(TrackingConfig(yaw_bias=3, pitch_bias=12))
        tracker.enable(0, 3, 12)
        target = tracker.update([Face(.42, .42, .2, .2)], .2, .2)
        self.assertEqual((target.yaw, target.pitch), (3, 12))
        self.assertFalse(target.returning)

    def test_large_delays_do_not_skip_speed_limit(self):
        tracker = FaceTracker()
        tracker.enable(0)
        target = tracker.update([Face(.8, 0, .2, .2)], 10, 10)
        self.assertLessEqual(abs(target.yaw), 5)
        self.assertLessEqual(abs(target.pitch - 10), 5)
        self.assertEqual(target.ttl_ms, 500)

    def test_lost_face_stops_targets_then_returns_smoothly(self):
        tracker = FaceTracker()
        tracker.enable(0)
        tracker.update([Face(.8, .4, .2, .2)], .2, .2)
        last = tracker.yaw
        self.assertIsNone(tracker.update([], .4, .4))
        self.assertEqual(tracker.yaw, last)
        target = tracker.update([], 1.3, 1.3)
        self.assertTrue(target.returning)
        self.assertLess(target.yaw, last)
        self.assertGreaterEqual(target.yaw, 0)

    def test_stale_duplicate_and_out_of_order_frames_never_select(self):
        tracker = FaceTracker()
        tracker.enable(0)
        face = Face(.8, .4, .2, .2)
        self.assertIsNone(tracker.update([face], 0, 1))
        self.assertEqual(tracker.yaw, 0)
        target = tracker.update([face], 1.2, 1.2)
        self.assertIsNotNone(target)
        last = tracker.yaw
        self.assertIsNone(tracker.update([face], 1.2, 1.3))
        self.assertIsNone(tracker.update([face], 1.1, 1.4))
        self.assertEqual(tracker.yaw, last)

    def test_stop_requires_explicit_enable(self):
        tracker = FaceTracker()
        face = Face(.8, .4, .2, .2)
        self.assertIsNone(tracker.update([face], 0, 0))
        tracker.enable(0)
        tracker.update([face], .2, .2)
        tracker.stop()
        for i in range(10):
            self.assertIsNone(tracker.update([face], 1 + i, 1 + i))
        tracker.enable(20)
        self.assertIsNotNone(tracker.update([face], 20.2, 20.2))

    def test_bounds_and_bad_input(self):
        for bounds in [(math.nan, 0, .1, .1), (0, 0, 2, .1), (0, -1, .1, .1)]:
            with self.assertRaises(ValueError):
                Face(*bounds)
        for config in [dict(ttl_ms=10000), dict(degrees_per_second=200), dict(yaw_bias=100), dict(deadzone=math.nan)]:
            with self.assertRaises(ValueError):
                TrackingConfig(**config)
        tracker = FaceTracker()
        tracker.enable(1)
        with self.assertRaises(ValueError):
            tracker.update([], 2, 1)
        with self.assertRaises(ValueError):
            tracker.update([], .1, .2)
