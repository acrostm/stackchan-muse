"""Explicit, USB-only host camera tracking. Frames remain in memory."""
import argparse
from dataclasses import asdict
import json
import sys
import time

from companion.tracking import Face, FaceTracker, TrackingConfig
from companion.tracking_usb import TrackingError, TrackingUSB


def detect_faces(cv, classifier, frame):
    if frame is None or len(frame.shape) < 2 or not frame.shape[0] or not frame.shape[1]:
        raise TrackingError('摄像头帧无效')
    gray = cv.equalizeHist(cv.cvtColor(frame, cv.COLOR_BGR2GRAY))
    rectangles = classifier.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5,
                                            minSize=(40, 40))
    height, width = frame.shape[:2]
    # Bound the detector result before handing it to the control core.
    return [Face(float(x) / width, float(y) / height,
                 float(w) / width, float(h) / height)
            for x, y, w, h in list(rectangles)[:64]
            if x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= width and y + h <= height]


def main(argv=None):
    parser = argparse.ArgumentParser(description='MuseStack 本机人脸跟踪；默认仅输出目标，不移动设备')
    parser.add_argument('--camera', type=int, default=0, help='本机摄像头编号')
    parser.add_argument('--move', action='store_true', help='显式允许申请已校准设备的跟踪会话')
    parser.add_argument('--port', help='USB 串口；移动设备时必填')
    parser.add_argument('--seconds', type=float, default=0, help='运行秒数；0 表示按 Ctrl-C 停止')
    parser.add_argument('--yaw-bias', type=float, default=0, help='电脑与机器人位置的水平偏置角度')
    parser.add_argument('--pitch-bias', type=float, default=10, help='垂直偏置角度')
    args = parser.parse_args(argv)
    if args.move and not args.port:
        parser.error('--move 必须显式指定 --port')
    if not 0 <= args.seconds <= 86400 or args.camera < 0:
        parser.error('运行时长或摄像头编号无效')
    try:
        config = TrackingConfig(yaw_bias=args.yaw_bias, pitch_bias=args.pitch_bias)
    except ValueError as error:
        parser.error(str(error))
    try:
        import cv2 as cv
    except ImportError:
        print('请先安装 companion/requirements-tracking.txt 中锁定的依赖', file=sys.stderr)
        return 2
    capture = stream = client = None
    try:
        classifier = cv.CascadeClassifier(cv.data.haarcascades + 'haarcascade_frontalface_default.xml')
        if classifier.empty():
            raise TrackingError('本地人脸检测模型加载失败')
        capture = cv.VideoCapture(args.camera)
        if not capture.isOpened():
            raise TrackingError('无法打开摄像头，请检查系统权限和摄像头编号')
        capture.set(cv.CAP_PROP_FRAME_WIDTH, 640)
        capture.set(cv.CAP_PROP_FRAME_HEIGHT, 480)
        capture.set(cv.CAP_PROP_BUFFERSIZE, 1)  # best effort; driver support varies
        if args.move:
            import serial
            stream = serial.Serial()
            # Set reset lines before opening; tracking never resets the board.
            stream.port = args.port
            stream.baudrate = 115200
            stream.timeout = .05
            stream.write_timeout = .5
            stream.dtr = stream.rts = False
            stream.open()
            stream.reset_input_buffer()
            client = TrackingUSB(stream)
        tracker = FaceTracker(config)
        started = time.monotonic()
        tracker.enable(started, config.yaw_bias, config.pitch_bias)
        while not args.seconds or time.monotonic() - started < args.seconds:
            captured_at = time.monotonic()
            ok, frame = capture.read()
            if not ok:
                raise TrackingError('摄像头取帧失败，跟踪已停止')
            faces = detect_faces(cv, classifier, frame)
            target = tracker.update(faces, captured_at, time.monotonic())
            if target is not None:
                if client is not None:
                    if not client.generation:
                        client.begin()  # once, on first detected face; never auto-rearm
                    client.send(target)
                else:
                    print(json.dumps(asdict(target)), flush=True)
            time.sleep(max(0, .2 - (time.monotonic() - captured_at)))
        return 0
    except KeyboardInterrupt:
        return 0
    except (TrackingError, OSError, ImportError, ValueError, cv.error) as error:
        print(f'跟踪停止：{error}', file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.stop()
        if stream is not None:
            stream.close()
        if capture is not None:
            capture.release()


if __name__ == '__main__':
    raise SystemExit(main())
