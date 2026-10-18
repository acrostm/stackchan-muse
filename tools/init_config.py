#!/usr/bin/env python3
"""Create private configuration without overwriting existing credentials."""
import json
from pathlib import Path
import secrets


def initialize(root):
    directory = root / '.private'
    directory.mkdir(mode=0o700, exist_ok=True)
    directory.chmod(0o700)
    target = directory / 'config.json'
    config = json.loads((root / 'config.example.json').read_text())
    config['tts_proxy_token'] = secrets.token_urlsafe(32)
    with target.open('x') as stream:
        target.chmod(0o600)
        json.dump(config, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return target


if __name__ == '__main__':
    try:
        initialize(Path(__file__).resolve().parents[1])
        print('Created .private/config.json; enter credentials locally.')
    except FileExistsError:
        print('Existing configuration preserved; nothing changed.')
