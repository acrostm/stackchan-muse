from collections import deque
import json
import unittest

from companion.tracking import HeadTarget
from companion.tracking_usb import TrackingError, TrackingUSB


def begin(token=7):
    return b'@head.track.begin ' + json.dumps({'version': 1, 'generation': token}).encode() + b'\n'


def ack(sequence=1, accepted=True, token=7):
    return b'@head.track ' + json.dumps({'version': 1, 'generation': token,
                                       'sequence': sequence, 'accepted': accepted}).encode() + b'\n'


class Stream:
    def __init__(self, replies=()):
        self.replies = deque(replies)
        self.writes = []
        self.time = 0
        self.short = False

    def write(self, data):
        self.writes.append(data)
        return len(data) - int(self.short)

    def readline(self, cap):
        return self.replies.popleft() if self.replies else b''

    def clock(self):
        self.time += .05
        return self.time


class TrackingUSBTests(unittest.TestCase):
    def test_correlated_ack_and_token_scoped_stop(self):
        stream = Stream([begin(), ack(99), ack()])
        client = TrackingUSB(stream, stream.clock)
        client.begin()
        client.send(HeadTarget(1.2, 3.4, 500, False))
        self.assertEqual(stream.writes[-1], b'>head.track=1,7,1,12,34,500\n')
        client.stop()
        self.assertEqual(stream.writes[-1], b'>head.track.stop=7\n')
        self.assertNotIn(b'>head.stop\n', stream.writes)
        with self.assertRaises(TrackingError):
            client.begin()

    def test_rejection_latches_and_cannot_resume(self):
        stream = Stream([begin(), ack(accepted=False)])
        client = TrackingUSB(stream, stream.clock)
        client.begin()
        with self.assertRaises(TrackingError):
            client.send(HeadTarget(0, 10, 500, False))
        count = len(stream.writes)
        with self.assertRaises(TrackingError):
            client.send(HeadTarget(0, 10, 500, False))
        self.assertEqual(len(stream.writes), count)
        self.assertTrue(client.failed)
        self.assertEqual(client.generation, 0)

    def test_timeout_and_partial_write(self):
        stream = Stream([begin()])
        client = TrackingUSB(stream, stream.clock)
        client.begin()
        with self.assertRaises(TrackingError):
            client.send(HeadTarget(0, 10, 500, False))
        self.assertTrue(client.failed)
        stream = Stream([begin()])
        stream.short = True
        client = TrackingUSB(stream, stream.clock)
        with self.assertRaises(TrackingError):
            client.begin()
        self.assertTrue(client.failed)
        self.assertEqual(len(stream.writes), 1)

    def test_unready_or_malformed_begin_does_not_stop_other_motion(self):
        for response in [begin(0), begin(True), b'@head.track.begin invalid\n',
                         b'@head.track.begin {"version":true,"generation":7}\n']:
            stream = Stream([response])
            client = TrackingUSB(stream, stream.clock)
            with self.assertRaises(TrackingError):
                client.begin()
            self.assertEqual(stream.writes, [b'>head.track.begin\n'])

    def test_invalid_targets_stop_the_current_lease(self):
        for target in [HeadTarget(float('nan'), 10, 500, False),
                       HeadTarget('bad', 10, 500, False),
                       HeadTarget(0, -1, 500, False),
                       HeadTarget(0, 10, 5000, False)]:
            stream = Stream([begin()])
            client = TrackingUSB(stream, stream.clock)
            client.begin()
            with self.assertRaises(TrackingError):
                client.send(target)
            self.assertTrue(client.failed)
            self.assertEqual(stream.writes[-1], b'>head.track.stop=7\n')
