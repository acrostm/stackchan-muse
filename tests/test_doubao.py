import base64
import json
import time
import unittest
from unittest.mock import patch
from companion.doubao import decode_audio, synthesize, TTSError, MAX_AUDIO


def event(code=0, data=b''):
    return json.dumps({'code': code, 'data': base64.b64encode(data).decode()}).encode()


class DoubaoTests(unittest.TestCase):
    def test_stream_assembles_in_order(self):
        self.assertEqual(decode_audio([event(data=b'ID3abc'), event(data=b'def'),
                                       event(20000000)]), b'ID3abcdef')

    def test_real_provider_null_usage_and_completion_events(self):
        self.assertEqual(decode_audio([event(data=b'ID3abc'),
            b'{"code":0,"data":null,"usage":{"text_words":2}}',
            b'{"code":20000000,"data":null}']), b'ID3abc')

    def test_errors_and_incomplete_audio_never_escape_to_player(self):
        for lines in ([event(data=b'ID3abc')],
                      [event(data=b'ID3abc'), event(401)],
                      [event(20000000)],
                      [event(20000000, b'not mp3')],
                      [b'bad json'], [b'{"code":0,"data":"!!!!"}'],
                      [b'[]'], [b'{"code":false}'],
                      [event(20000000, b'ID3'), event(data=b'abc')]):
            with self.subTest(lines=lines), self.assertRaises(TTSError):
                decode_audio(lines)

    def test_buffer_overflow_is_rejected(self):
        with self.assertRaises(TTSError):
            decode_audio([event(data=b'ID3' + b'x' * MAX_AUDIO), event(20000000)])

    def test_expired_request_is_rejected(self):
        with self.assertRaises(TTSError):
            decode_audio([event(20000000, b'ID3')], time.monotonic()-1)

    def test_invalid_input_never_contacts_provider(self):
        with patch('urllib.request.build_opener') as opener:
            for text in ('', 'x'*701, None):
                with self.assertRaises(TTSError):
                    synthesize(text, {})
            opener.assert_not_called()


if __name__ == '__main__':
    unittest.main()
