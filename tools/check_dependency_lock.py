#!/usr/bin/env python3
"""Reject resolved packages absent from or different to the reviewed lock snapshot."""
import argparse
from pathlib import Path


def validate(expected, actual, target='esp32s3'):
    for name, dependency in actual['dependencies'].items():
        locked = expected['dependencies'].get(name)
        if locked is None or any(dependency.get(key) != locked.get(key)
                                 for key in ('version', 'component_hash')):
            raise ValueError('Unreviewed dependency version or hash: ' + name)
    if actual.get('target') != target:
        raise ValueError(f'Unexpected firmware target: {actual.get("target")} (wanted {target})')


def constraints(expected):
    """Pin registry packages without activating optional dependencies."""
    return ''.join(f'{name}=={dependency["version"]}\n'
                   for name, dependency in sorted(expected['dependencies'].items())
                   if dependency.get('source', {}).get('type') == 'service')


if __name__ == '__main__':
    import yaml  # CLI runs with ESP-IDF's configured Python environment.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('actual', type=Path, nargs='?')
    parser.add_argument('--write-constraints', type=Path)
    parser.add_argument('--target', default='esp32s3')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    expected = yaml.safe_load((root / 'docs/firmware-dependencies.lock.yml').read_text())
    if args.write_constraints:
        args.write_constraints.write_text(constraints(expected))
        raise SystemExit(0)
    if args.actual is None:
        parser.error('actual lock file is required for validation')
    validate(expected, yaml.safe_load(args.actual.read_text()), args.target)
    print('Resolved package versions and hashes match the reviewed snapshot.')
