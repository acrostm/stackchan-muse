"""Bounded Doubao HTTP TTS client; credentials and provider errors are never logged."""
import base64
import binascii
import json
import time
import urllib.error
import urllib.request
import uuid

ENDPOINT = 'https://openspeech.bytedance.com/api/v3/tts/unidirectional'
MAX_AUDIO = 512 * 1024
MAX_WIRE = 2 * 1024 * 1024
MAX_LINE = 1024 * 1024


class TTSError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def decode_audio(lines, deadline=None):
    """Accept newline-delimited JSON; reject errors even after audio arrived."""
    audio = bytearray()
    consumed = 0
    finished = False
    for line in lines:
        if deadline is not None and time.monotonic() > deadline:
            raise TTSError('TTS deadline exceeded')
        consumed += len(line)
        if len(line) > MAX_LINE or consumed > MAX_WIRE:
            raise TTSError('TTS response too large')
        if not line.strip():
            continue
        if finished:
            raise TTSError('TTS data after completion')
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError()
            code = event.get('code')
            if type(code) is not int or code not in (0, 20000000):
                raise TTSError('TTS provider rejected synthesis')
            data = event.get('data', '')
            if data is None:
                data = ''  # Usage-only and completion events carry JSON null.
            if not isinstance(data, str):
                raise ValueError()
            audio.extend(base64.b64decode(data, validate=True))
            if len(audio) > MAX_AUDIO:
                raise TTSError('TTS audio exceeds device buffer')
            finished = code == 20000000
        except (ValueError, TypeError, binascii.Error):
            raise TTSError('Invalid TTS response') from None
    if not finished or not audio:
        raise TTSError('Incomplete TTS response')
    # MP3 stream must start with ID3 metadata or an MPEG frame sync.
    if not (audio.startswith(b'ID3') or
            (len(audio) >= 2 and audio[0] == 0xff and audio[1] & 0xe0 == 0xe0)):
        raise TTSError('Provider did not return MP3')
    return bytes(audio)


def synthesize(text, config):
    if not isinstance(text, str) or not text.strip() or len(text) > 700:
        raise TTSError('Text must contain 1 to 700 characters')
    if any(not isinstance(config.get(key), str) or not config[key].strip()
           for key in ('api_key', 'resource_id', 'speaker')):
        raise TTSError('Missing Doubao configuration')
    payload = {'req_params': {
        'text': text, 'speaker': config['speaker'],
        'audio_params': {'format': 'mp3', 'sample_rate': 24000, 'bit_rate': 64000},
    }}
    request = urllib.request.Request(ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json',
                 'X-Api-Key': config['api_key'],
                 'X-Api-Resource-Id': config['resource_id'],
                 'X-Api-Request-Id': str(uuid.uuid4())}, method='POST')
    opener = urllib.request.build_opener(NoRedirect())
    deadline = time.monotonic() + 35
    try:
        with opener.open(request, timeout=10) as response:
            if response.status != 200:
                raise TTSError('TTS HTTP failure')
            def lines():
                while True:
                    line = response.readline(MAX_LINE + 1)
                    if not line:
                        return
                    yield line
            return decode_audio(lines(), deadline)
    except urllib.error.HTTPError as error:
        raise TTSError(f'TTS HTTP {error.code}') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise TTSError('TTS network unavailable or timed out') from None
