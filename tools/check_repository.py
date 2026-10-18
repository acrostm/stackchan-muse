#!/usr/bin/env python3
"""Inspect the Git index, never print matching credential values."""
import json
import hashlib
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [re.compile(rb'\b(?:mgst_|gho_|github_pat_)[A-Za-z0-9_\-]{20,}'),
            re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')]
PUBLIC_FIXTURE = 'firmware/esp32/dev_signing_key.pem'
PUBLIC_FIXTURE_SHA256 = 'e57311281ea0478a80be57036768ef71481804eab73182b2b70255311a2ded6a'


def inspect(path, content, local_secrets=()):
    parts = Path(path).parts
    errors = []
    if any(p in ('.private', '.toolchains', '.venv', 'backups', 'managed_components',
                 '__pycache__', '.git') or p.startswith('build-') for p in parts):
        errors.append('local-only directory')
    name = parts[-1]
    if name in ('sdkconfig', 'sdkconfig.old', '.env', 'config.json') or (
            name.startswith('.env.') and name != '.env.example'):
        errors.append('private configuration path')
    if path != PUBLIC_FIXTURE and (Path(path).suffix in ('.pem', '.key', '.bin', '.elf', '.map', '.log')):
        errors.append('private key, binary or diagnostic output')
    if len(content) > 10 * 1024 * 1024:
        errors.append('oversize tracked file')
    fixture_ok = path == PUBLIC_FIXTURE and hashlib.sha256(content).hexdigest() == PUBLIC_FIXTURE_SHA256
    if path == PUBLIC_FIXTURE and not fixture_ok:
        errors.append('upstream public signing fixture changed')
    scanned = content
    if path == 'firmware/esp32/tests/link_pairing_handshake_harness.c':
        scanned = scanned.replace(b'mgst_' + b'A' * 43, b'synthetic-test-token')
    if not fixture_ok and any(p.search(scanned) for p in PATTERNS):
        errors.append('credential-like content')
    if any(secret in content for secret in local_secrets):
        errors.append('matches a locally configured secret')
    return errors


def main():
    result = subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=ROOT)
    secrets = []
    private = ROOT / '.private/config.json'
    if private.exists():
        config = json.loads(private.read_text())
        values = [config.get('muse_sdk_token'), config.get('tts_proxy_token')]
        values += [config.get('doubao', {}).get(k) for k in ('api_key', 'access_token')]
        secrets = [v.encode() for v in values if isinstance(v, str) and len(v) >= 8]
    failures = []
    count = 0
    for item in result.split(b'\0'):
        if not item:
            continue
        metadata, raw_path = item.split(b'\t', 1)
        mode, oid, stage = metadata.decode().split()
        path = raw_path.decode()
        if mode in ('160000', '120000') or stage != '0':
            failures.append((path, ['nested repository, symlink or unresolved conflict']))
            continue
        content = subprocess.check_output(['git', 'cat-file', 'blob', oid], cwd=ROOT)
        reasons = inspect(path, content, secrets)
        if reasons:
            failures.append((path, reasons))
        count += 1
    for path, reasons in failures:
        print(path + ': ' + ', '.join(reasons))
    print(f'Inspected {count} indexed files; {len(failures)} policy violations. Values are never printed.')
    return bool(failures)


if __name__ == '__main__':
    sys.exit(main())
