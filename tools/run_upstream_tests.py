#!/usr/bin/env python3
"""Run upstream tests and fail the CI gate on any failure or skip."""
from pathlib import Path
import sys
import unittest

root = Path(__file__).resolve().parents[1]
suite = unittest.defaultTestLoader.discover(str(root / 'firmware/esp32/tests'), pattern='test_*.py')
result = unittest.TextTestRunner(verbosity=2).run(suite)
if result.skipped:
    print('CI requires all upstream tests to run; skipped tests are a failed gate.')
sys.exit(not result.wasSuccessful() or bool(result.skipped))
