"""USB-only tracking adapter. No credentials, network listener or auto-reconnect."""
import json
import time

from companion.tracking import HeadTarget, finite


class TrackingError(RuntimeError):
    pass


class TrackingUSB:
    def __init__(self, stream, clock=time.monotonic, timeout=1):
        self.stream = stream
        self.clock = clock
        self.timeout = timeout
        self.generation = 0
        self.sequence = 0
        self.failed = False
        self._rx = bytearray()

    def _read_line(self, deadline):
        # pyserial readline() may return a fragment at its short read timeout.
        # Keep fragments (including split prefixes) until a real line ending.
        while self.clock() < deadline:
            newline = self._rx.find(b'\n')
            if newline >= 0:
                if newline >= 511:
                    raise TrackingError('设备响应过长')
                line = bytes(self._rx[:newline + 1])
                del self._rx[:newline + 1]
                return line
            remaining = 512 - len(self._rx)
            if remaining <= 0:
                raise TrackingError('设备响应过长')
            chunk = self.stream.readline(remaining)
            if not isinstance(chunk, (bytes, bytearray)) or len(chunk) > remaining:
                raise TrackingError('设备响应格式错误或过长')
            self._rx.extend(chunk)
        return None

    def _request(self, command, prefix, matches=lambda message: True):
        data = ('>' + command + '\n').encode('ascii')
        if self.stream.write(data) != len(data):
            raise TrackingError('设备指令写入不完整')
        deadline = self.clock() + self.timeout
        while self.clock() < deadline:
            raw = self._read_line(deadline)
            if raw is None:
                break
            if not raw.startswith(prefix):
                continue
            try:
                result = json.loads(raw[len(prefix):])
            except (ValueError, UnicodeError):
                raise TrackingError('设备响应格式错误') from None
            if (not isinstance(result, dict) or type(result.get('version')) is not int
                    or result.get('version') != 1):
                raise TrackingError('设备跟踪协议版本不兼容')
            if matches(result):
                return result
        raise TrackingError('设备跟踪响应超时')

    def begin(self):
        # A failed client must be replaced through a fresh user invocation.
        if self.failed or self.generation:
            raise TrackingError('请停止并重新显式开启跟踪')
        try:
            result = self._request('head.track.begin', b'@head.track.begin ')
            token = result.get('generation')
            if type(token) is not int or not 0 < token <= 0xffffffff:
                raise TrackingError('设备未校准或当前动作不允许跟踪')
            self.generation = token
        except Exception:
            self._fail()
            raise

    def send(self, target: HeadTarget):
        if self.failed or not self.generation:
            raise TrackingError('跟踪未开启或已停止')
        if (not isinstance(target, HeadTarget)
                or not all(finite(v) for v in (target.yaw, target.pitch))
                or not -60 <= target.yaw <= 60 or not 0 <= target.pitch <= 60
                or type(target.ttl_ms) is not int or not 100 <= target.ttl_ms <= 1000):
            self._fail()
            raise TrackingError('跟踪目标无效')
        self.sequence += 1
        if self.sequence > 0xffffffff:
            self._fail()
            raise TrackingError('跟踪序号已用尽，请重新开启')
        command = (f'head.track=1,{self.generation},{self.sequence},'
                   f'{round(target.yaw * 10)},{round(target.pitch * 10)},{target.ttl_ms}')
        try:
            result = self._request(command, b'@head.track ', lambda message: (
                type(message.get('generation')) is int
                and type(message.get('sequence')) is int
                and message.get('generation') == self.generation
                and message.get('sequence') == self.sequence))
            if result.get('accepted') is not True:
                raise TrackingError('设备拒绝跟踪目标，跟踪已停止')
        except Exception:
            self._fail()
            raise

    def _fail(self):
        self.failed = True
        token, self.generation = self.generation, 0
        # Stop only this lease: a stale client must not stop a newer user command.
        # If USB is gone the device-local TTL is the fallback.
        if token:
            try:
                self.stream.write(f'>head.track.stop={token}\n'.encode('ascii'))
            except Exception:
                pass

    def stop(self):
        self._fail()
