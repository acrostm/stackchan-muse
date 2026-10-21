"""Bounded face selection and head targets; no camera, identity or hardware I/O."""
from dataclasses import dataclass
import math
from typing import Iterable


def finite(value: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class Face:
    # Normalized image bounds, independent of resolution. No identity features.
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self):
        if (not all(finite(v) for v in (self.x, self.y, self.width, self.height))
                or self.x < 0 or self.y < 0 or self.width <= 0 or self.height <= 0
                or self.x + self.width > 1 or self.y + self.height > 1):
            raise ValueError("人脸边界必须位于归一化画面内")

    @property
    def center(self):
        return self.x + self.width / 2, self.y + self.height / 2


@dataclass(frozen=True)
class TrackingConfig:
    yaw_span: float = 20
    pitch_span: float = 15
    yaw_bias: float = 0
    pitch_bias: float = 10
    degrees_per_second: float = 20
    deadzone: float = 0.08
    smoothing_seconds: float = 0.25
    lost_seconds: float = 1
    max_frame_age: float = 0.5
    max_step_seconds: float = 0.25
    association_radius: float = 0.3
    ttl_ms: int = 500

    def __post_init__(self):
        values = vars(self)
        if not all(finite(value) for value in values.values()):
            raise ValueError("跟踪配置必须是有限数值")
        if (not 0 < self.yaw_span <= 40 or not 0 < self.pitch_span <= 25
                or abs(self.yaw_bias) + self.yaw_span > 60
                or not 0 <= self.pitch_bias <= 40
                or self.pitch_bias + self.pitch_span > 60
                or not 0 < self.degrees_per_second <= 30
                or not 0 <= self.deadzone < 0.5
                or not 0.05 <= self.smoothing_seconds <= 2
                or not 0.2 <= self.lost_seconds <= 5
                or not 0.05 <= self.max_frame_age <= 1
                or not 0.01 <= self.max_step_seconds <= 0.25
                or not 0 < self.association_radius <= 0.5
                or not isinstance(self.ttl_ms, int) or not 100 <= self.ttl_ms <= 1000):
            raise ValueError("跟踪配置超出允许范围")


@dataclass(frozen=True)
class HeadTarget:
    yaw: float
    pitch: float
    ttl_ms: int
    returning: bool


class FaceTracker:
    """Explicit enable is required after stop; stale frames never select a face.

    This produces intents only. A device adapter must enforce its own calibrated
    limits, tracking priority, generation and TTL before moving hardware.
    """

    def __init__(self, config: TrackingConfig = TrackingConfig()):
        self.config = config
        self.enabled = False
        self._last_time = None
        self._last_frame = None
        self._last_seen = None
        self._center = None
        self.yaw = config.yaw_bias
        self.pitch = config.pitch_bias

    def enable(self, now: float, yaw: float = 0, pitch: float = 10):
        if (not all(finite(v) for v in (now, yaw, pitch)) or now < 0
                or not -60 <= yaw <= 60 or not 0 <= pitch <= 60):
            raise ValueError("跟踪起点无效")
        self.enabled = True
        self._last_time = now
        self._last_frame = self._last_seen = self._center = None
        self.yaw, self.pitch = yaw, pitch

    def stop(self):
        self.enabled = False
        self._center = self._last_seen = self._last_frame = None

    def update(self, faces: Iterable[Face], captured_at: float, now: float):
        if not self.enabled:
            return None
        if (not finite(now) or not finite(captured_at) or captured_at < 0
                or now < self._last_time or captured_at > now):
            raise ValueError("帧时间必须来自同一单调时钟")
        dt = min(now - self._last_time, self.config.max_step_seconds)
        self._last_time = now
        if self._last_frame is not None and captured_at <= self._last_frame:
            return None
        if now - captured_at > self.config.max_frame_age:
            return None  # Never renew a device lease from stale imagery.
        self._last_frame = captured_at
        candidates = list(faces)
        if len(candidates) > 64 or any(not isinstance(face, Face) for face in candidates):
            raise ValueError("人脸候选无效或过多")
        chosen = None
        if candidates and self._center is not None:
            chosen = min(candidates, key=lambda f: math.dist(f.center, self._center))
            if math.dist(chosen.center, self._center) > self.config.association_radius:
                chosen = None
        elif candidates:
            chosen = max(candidates, key=lambda f: f.width * f.height)
        returning = chosen is None
        if chosen is not None:
            self._center = chosen.center
            self._last_seen = captured_at
            x, y = (2 * v - 1 for v in chosen.center)
            x = 0 if abs(x) <= self.config.deadzone else x
            y = 0 if abs(y) <= self.config.deadzone else y
            target_yaw = self.config.yaw_bias + x * self.config.yaw_span
            target_pitch = clamp(self.config.pitch_bias - y * self.config.pitch_span, 0, 60)
        else:
            if self._last_seen is None:
                return None
            if now - self._last_seen < self.config.lost_seconds:
                # A fresh frame without a face holds the last bounded target.
                # This renews the device lease without chasing stale imagery.
                return HeadTarget(self.yaw, self.pitch, self.config.ttl_ms, False)
            self._center = None
            target_yaw, target_pitch = self.config.yaw_bias, self.config.pitch_bias
        alpha = -math.expm1(-dt / self.config.smoothing_seconds)
        step = self.config.degrees_per_second * dt
        self.yaw += clamp((target_yaw - self.yaw) * alpha, -step, step)
        self.pitch += clamp((target_pitch - self.pitch) * alpha, -step, step)
        return HeadTarget(self.yaw, self.pitch, self.config.ttl_ms, returning)
