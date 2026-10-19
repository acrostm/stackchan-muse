#!/usr/bin/env python3
"""Package only account-free flash binaries and provenance, not build directories."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile


def package(build, output, board):
    root = Path(__file__).resolve().parents[1]
    sdkconfig = (build / 'sdkconfig').read_text()
    token = re.search(r'^CONFIG_GADGET_SDK_TOKEN=(.*)$', sdkconfig, re.M)
    if not token or token.group(1).strip() != '""':
        raise ValueError('Refusing to package a missing/unknown/nonempty account-token setting')
    for line in sdkconfig.splitlines():
        if re.match(r'^CONFIG_.*(?:TOKEN|PASSWORD|SECRET|API_KEY|WIFI_SSID)=', line):
            if line.partition('=')[2].strip() != '""':
                raise ValueError('Refusing to package personal network or provider configuration')
    args = json.loads((build / 'flasher_args.json').read_text())
    manifest = {'board': board, 'account_token_included': False,
                'hardware_verified': False, 'flash_files': {},
                # Actions containers may run as a different owner than checkout.
                # Trust only this source tree, for this command, never all paths.
                'commit': subprocess.check_output([
                    'git', '-c', f'safe.directory={root}', '-C', str(root),
                    'rev-parse', 'HEAD']).decode().strip(),
                'flash_settings': args['flash_settings']}
    output.mkdir(parents=True, exist_ok=True)
    target = output / f'musestack-{board}-no-account-token.tar.gz'
    with tempfile.TemporaryDirectory() as temp:
        staging = Path(temp)
        for offset, relative in args['flash_files'].items():
            source = (build / relative).resolve()
            if not source.is_relative_to(build.resolve()) or source.suffix != '.bin':
                raise ValueError('Unexpected flash artifact path')
            name = offset + '-' + source.name
            content = source.read_bytes()
            (staging / name).write_bytes(content)
            manifest['flash_files'][offset] = {'file': name, 'bytes': len(content),
                                             'sha256': hashlib.sha256(content).hexdigest()}
        (staging / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        (staging / 'README.txt').write_text(
            'Account-free development build, not a paired or hardware-approved image.\n'
            'Back up and identify hardware first. Never burn eFuses.\n'
            'Muse pairing needs your own locally configured SDK token.\n')
        for name in ('LICENSE', 'NOTICE'):
            (staging / name).write_bytes((root / name).read_bytes())
        (staging / 'minimp3-LICENSE.txt').write_bytes(
            (root / 'firmware/esp32/components/minimp3/LICENSE').read_bytes())
        with tarfile.open(target, 'w:gz') as archive:
            for path in sorted(staging.iterdir()):
                archive.add(path, arcname=path.name)
    target.with_suffix(target.suffix + '.sha256').write_text(
        hashlib.sha256(target.read_bytes()).hexdigest() + '  ' + target.name + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--board', choices=('stackchan', 'cores3'), required=True)
    args = parser.parse_args()
    package(args.build, args.output, args.board)
