#!/usr/bin/env python3
"""Validate recorded hardware evidence against the exact source trees."""
import argparse
import json
from pathlib import Path
import re
import subprocess

CHECKS = ('muse_pairing', 'voice_roundtrip', 'tts_playback', 'touch_stop',
          'head_limits', 'head_emergency_stop', 'reconnect', 'twenty_turns',
          'two_hour_stability', 'recovery')


def validate(report, trees):
    if report.get('board') != 'stackchan':
        raise ValueError('Hardware report must identify the StackChan profile')
    evidence = report.get('evidence')
    if not isinstance(evidence, str) or not evidence.strip() or '<' in evidence:
        raise ValueError('Real evidence reference required')
    for component, tree in trees.items():
        if report.get(component + '_tree') != tree:
            raise ValueError('Hardware report source trees do not match')
    if any(report.get('checks', {}).get(check) is not True for check in CHECKS):
        raise ValueError('Hardware acceptance incomplete')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'v\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', args.version):
        parser.error('Expected a version such as v0.1.0')
    root = Path(__file__).resolve().parents[1]
    path = (root / args.report).resolve()
    if not path.is_relative_to(root / 'docs/hardware-validation') or path.suffix != '.json':
        parser.error('Report must be a JSON file under docs/hardware-validation/')
    trees = {key: subprocess.check_output(['git', 'rev-parse', 'HEAD:' + key], cwd=root).decode().strip()
             for key in ('firmware', 'companion', 'tools')}
    validate(json.loads(path.read_text()), trees)
    print('Recorded hardware acceptance matches the current source trees.')
