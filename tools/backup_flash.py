#!/usr/bin/env python3
"""Read-only flash backup. Never writes flash, erases it, or changes eFuses."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone


def digest(path, expected_size):
    if path.stat().st_size != expected_size:
        raise ValueError('Backup size differs from identified flash size')
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--size-mib', type=int, choices=(4, 8, 16, 32), required=True,
                        help='Use the capacity reported by esptool flash-id')
    parser.add_argument('--output', type=Path, required=True,
                        help='New private directory; existing paths are refused')
    args = parser.parse_args()
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    size = args.size_mib * 1024 * 1024
    hashes = []
    for name in ('flash-a.bin', 'flash-b.bin'):
        path = args.output / name
        path.touch(mode=0o600, exist_ok=False)
        subprocess.run([sys.executable, '-m', 'esptool', '--port', args.port,
                        '--after', 'no-reset', 'read-flash', '0', str(size), str(path)],
                       check=True)
        hashes.append(digest(path, size))
    if hashes[0] != hashes[1]:
        raise RuntimeError('Two reads differ; do not flash. Keep files for diagnosis.')
    manifest = args.output / 'manifest.json'
    manifest.touch(mode=0o600, exist_ok=False)
    manifest.write_text(json.dumps({
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'port': args.port, 'bytes': size, 'sha256': hashes[0],
        'files': ['flash-a.bin', 'flash-b.bin'],
        'two_reads_match': True, 'restore_tested': False,
    }, indent=2) + '\n')
    print('Two complete reads match. Restore has NOT been tested.')


if __name__ == '__main__':
    main()
