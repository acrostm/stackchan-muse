from http.client import HTTPConnection
from http.server import HTTPServer
import json
import threading
import unittest

from companion.doubao import TTSError
from companion.tts_server import make_handler

TOKEN = 'test-only-token-with-at-least-24-characters'


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.fail = False
        def provider(text, config):
            self.calls.append(text)
            if self.fail:
                raise TTSError('private provider details')
            return b'ID3test'
        self.server = HTTPServer(('127.0.0.1', 0), make_handler(
            {'tts_proxy_token': TOKEN, 'doubao': {}}, provider))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.cleanup_server)

    def cleanup_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, text='你好', token=TOKEN, path='/tts', body=None):
        conn = HTTPConnection('127.0.0.1', self.server.server_port, timeout=2)
        try:
            conn.request('POST', path, body if body is not None else json.dumps({'text': text}),
                         {'X-Tts-Auth': token, 'Content-Type': 'application/json'})
            response = conn.getresponse()
            return response.status, response.getheader('Content-Type'), response.read()
        finally:
            conn.close()

    def test_authenticated_chinese_request_returns_mp3(self):
        self.assertEqual(self.request(), (200, 'audio/mpeg', b'ID3test'))
        self.assertEqual(self.calls, ['你好'])

    def test_unauthorized_request_never_calls_paid_provider(self):
        self.assertEqual(self.request(token='wrong')[0], 401)
        self.assertEqual(self.calls, [])

    def test_malformed_oversize_and_unknown_routes_do_not_call_provider(self):
        for params, status in (({'body': b'[]'}, 400), ({'body': b'broken'}, 400),
                               ({'body': b'x'*4097}, 413), ({'text': 'x'*701}, 400),
                               ({'text': ''}, 400), ({'path': '/other'}, 404)):
            with self.subTest(params=params):
                self.assertEqual(self.request(**params)[0], status)
        self.assertEqual(self.calls, [])

    def test_provider_error_is_sanitized(self):
        self.fail = True
        status, _, body = self.request()
        self.assertEqual(status, 502)
        self.assertNotIn(b'private provider', body)


if __name__ == '__main__':
    unittest.main()
