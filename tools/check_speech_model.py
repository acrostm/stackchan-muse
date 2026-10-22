"""Verify the selected model assets against the reviewed official reference."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def validate_packed(content: bytes, lock: dict):
    # ESP-SR 2.6.0 model/pack_model.py: one 32-byte model name, then a
    # bounded file table of 32-byte names and uint32 little-endian spans.
    count = len(lock['assets'])
    header_bytes = 4 + 36 + count * 40
    if len(content) < header_bytes or struct.unpack_from('<I', content)[0] != 1:
        raise ValueError('Invalid packed model header')
    def name_at(offset):
        raw = content[offset:offset + 32]
        name, _, padding = raw.partition(b'\0')
        if any(padding): raise ValueError('Invalid packed model name padding')
        try: return name.decode('ascii')
        except UnicodeError: raise ValueError('Invalid packed model name') from None
    if name_at(4) != lock['model'] or struct.unpack_from('<I', content, 36)[0] != count:
        raise ValueError('Unexpected packed model selection')
    seen, spans = set(), []
    for index in range(count):
        entry = 40 + index * 40
        name = name_at(entry)
        if name in seen or name not in lock['assets']:
            raise ValueError('Unexpected packed model asset')
        seen.add(name)
        offset, length = struct.unpack_from('<II', content, entry + 32)
        expected = lock['assets'][name]
        if (offset < header_bytes or length != expected['bytes'] or
                offset + length > len(content) or
                hashlib.sha256(content[offset:offset + length]).hexdigest() != expected['sha256']):
            raise ValueError('Packed model content differs from the pinned reference')
        spans.append((offset, offset + length))
    end = header_bytes
    for start, stop in sorted(spans):
        if start != end: raise ValueError('Invalid packed model asset spans')
        end = stop
    if end != len(content): raise ValueError('Unexpected packed model trailing data')


def validate(build: Path, lock: dict):
    base = build / 'srmodels'
    model = lock['model']
    if {p.name for p in base.iterdir() if p.is_dir()} != {model}:
        raise ValueError('Unexpected speech models were selected')
    selected = base / model
    if {p.name for p in selected.iterdir()} != set(lock['assets']):
        raise ValueError('Unexpected model assets')
    for name, expected in lock['assets'].items():
        asset = selected / name
        if (not asset.is_file() or asset.is_symlink() or
                asset.stat().st_size != expected['bytes'] or
                hashlib.sha256(asset.read_bytes()).hexdigest() != expected['sha256']):
            raise ValueError('Speech model differs from the official pinned reference: ' + name)
    image = base / 'srmodels.bin'
    if image.is_symlink() or not image.is_file() or not 0 < image.stat().st_size <= lock['partition_bytes']:
        raise ValueError('Missing or oversized packed speech model')
    validate_packed(image.read_bytes(), lock)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', type=Path)
    args = parser.parse_args()
    validate(args.build, json.loads((ROOT / 'docs/speech-models.lock.json').read_text()))
    print('Selected speech model assets match the pinned official reference.')
