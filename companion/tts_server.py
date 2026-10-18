"""Authenticated single-device bridge for the firmware's local TTS hook."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
from pathlib import Path
import socket

from .doubao import synthesize, TTSError


def make_handler(config, provider=synthesize):
    token = config.get('tts_proxy_token', '')
    if not isinstance(token, str) or len(token) < 24 or not token.isascii():
        raise ValueError('A private proxy token of at least 24 ASCII characters is required')

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, format, *args):
            pass  # Do not log request text, credentials or audio.

        def reply(self, status, body, content_type='application/json'):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            try:
                auth = self.headers.get('X-Tts-Auth', '')
                if not hmac.compare_digest(auth.encode('utf-8'), token.encode('ascii')):
                    self.reply(401, b'{"error":"unauthorized"}')
                    return
                if self.path != '/tts':
                    self.reply(404, b'{"error":"not_found"}')
                    return
                if self.headers.get('Transfer-Encoding'):
                    self.reply(400, b'{"error":"content_length_required"}')
                    return
                lengths = self.headers.get_all('Content-Length', [])
                if len(lengths) != 1:
                    raise ValueError()
                length = int(lengths[0])
                if not 0 < length <= 4096:
                    self.reply(413, b'{"error":"request_too_large"}')
                    return
                body = self.rfile.read(length)
                if len(body) != length:
                    raise ValueError()
                request = json.loads(body)
                if not isinstance(request, dict):
                    raise ValueError()
                text = request.get('text')
                if not isinstance(text, str) or not text.strip() or len(text) > 700:
                    raise ValueError()
                audio = provider(text, config['doubao'])
                self.reply(200, audio, 'audio/mpeg')
            except (ValueError, UnicodeError, socket.timeout):
                self.reply(400, b'{"error":"invalid_request"}')
            except TTSError:
                self.reply(502, b'{"error":"synthesis_failed"}')
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('.private/config.json'))
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    address = ipaddress.ip_address(args.bind)
    # Bind one explicit local IPv4 address. Never listen on all interfaces.
    if address.version != 4 or address.is_unspecified or not (address.is_loopback or address.is_private):
        parser.error('--bind must be a specific private or loopback IPv4 address')
    config = json.loads(args.config.read_text())
    server = HTTPServer((args.bind, args.port), make_handler(config))
    server.timeout = 1
    print('MuseStack TTS bridge ready', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
