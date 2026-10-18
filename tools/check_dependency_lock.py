#!/usr/bin/env python3
"""Reject resolved packages absent from or different to the reviewed lock snapshot."""
import argparse
from pathlib import Path
import yaml


def validate(expected, actual):
    for name, dependency in actual['dependencies'].items():
        locked = expected['dependencies'].get(name)
        if locked is None or any(dependency.get(key) != locked.get(key)
                                 for key in ('version', 'component_hash')):
            raise ValueError('Unreviewed dependency version or hash: ' + name)
    if actual.get('target') != 'esp32s3':
        raise ValueError('Unexpected firmware target')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('actual', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    validate(yaml.safe_load((root / 'docs/firmware-dependencies.lock.yml').read_text()),
             yaml.safe_load(args.actual.read_text()))
    print('Resolved package versions and hashes match the reviewed snapshot.')
