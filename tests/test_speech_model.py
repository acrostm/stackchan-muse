import csv
import hashlib
import importlib.util
import json
import re
from pathlib import Path
import tempfile
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('speech_model_check', ROOT / 'tools/check_speech_model.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class SpeechModelTests(unittest.TestCase):
    def test_exact_assets_and_bounded_image_are_required(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            model = build / 'srmodels' / 'known-model'
            model.mkdir(parents=True)
            asset = model / 'weights'
            asset.write_bytes(b'fixed-public-model')
            image = build / 'srmodels' / 'srmodels.bin'
            packed = (struct.pack('<I32sI32sII', 1, b'known-model', 1, b'weights',
                                  80, asset.stat().st_size) + asset.read_bytes())
            image.write_bytes(packed)
            lock = {'model': 'known-model', 'partition_bytes': 128,
                    'assets': {'weights': {'bytes': asset.stat().st_size,
                        'sha256': hashlib.sha256(asset.read_bytes()).hexdigest()}}}
            checker.validate(build, lock)
            original = asset.read_bytes()
            asset.write_bytes(b'x' * len(original))
            with self.assertRaises(ValueError): checker.validate(build, lock)
            asset.write_bytes(original)
            extra = model / 'unexpected'
            extra.write_bytes(b'other-data')
            with self.assertRaises(ValueError): checker.validate(build, lock)
            extra.unlink()
            extra_model = build / 'srmodels' / 'other-model'
            extra_model.mkdir()
            with self.assertRaises(ValueError): checker.validate(build, lock)
            extra_model.rmdir()
            asset.unlink()
            target = build / 'external-weights'
            target.write_bytes(original)
            asset.symlink_to(target)
            with self.assertRaises(ValueError): checker.validate(build, lock)
            asset.unlink(); asset.write_bytes(original)
            image.write_bytes(packed[:-1] + b'x')
            with self.assertRaises(ValueError): checker.validate(build, lock)
            image.write_bytes(packed + b'trailing')
            with self.assertRaises(ValueError): checker.validate(build, lock)
            image.write_bytes(b'x' * 129)
            with self.assertRaises(ValueError): checker.validate(build, lock)
            image.unlink()
            with self.assertRaises(ValueError): checker.validate(build, lock)

    def test_device_and_build_model_manifests_agree(self):
        lock = json.loads((ROOT / 'docs/speech-models.lock.json').read_text())
        source = (ROOT / 'firmware/esp32/components/muse/muse_sr_partition.c').read_text()
        rows = re.findall(r'\{"([^"\n]+)", (\d+)u, "([a-f0-9]{64})"\}', source)
        expected = {name: {'bytes': int(size), 'sha256': digest}
                    for name, size, digest in rows}
        self.assertEqual(expected, lock['assets'])
        self.assertIn('"' + lock['model'] + '"', source)
        self.assertIn(str(lock['partition_bytes']) + 'u', source)

    def test_model_partition_preserves_existing_geometry(self):
        def rows(path):
            return {r[0].strip(): [field.strip() for field in r] for r in csv.reader(
                line for line in path.read_text().splitlines() if line and not line.startswith('#'))}
        firmware = ROOT / 'firmware/esp32'
        old = rows(firmware / 'partitions_muse.csv')
        new = rows(firmware / 'partitions_muse_handsfree.csv')
        for name, row in old.items(): self.assertEqual(new[name], row)
        self.assertEqual(new['nvs'][3:5], ['0x11000', '0xC000'])
        self.assertEqual(new['ota_0'][3:5], ['0x20000', '4M'])
        self.assertEqual(new['ota_1'][3:5], ['0x420000', '4M'])
        self.assertEqual(new['prod_bak'][3:5], ['0x821000', '0x1000'])
        self.assertEqual(new['model'][3:5], ['0x830000', '2M'])
        self.assertLessEqual(int(new['model'][3], 16) + 2 * 1024**2, 16 * 1024**2)
