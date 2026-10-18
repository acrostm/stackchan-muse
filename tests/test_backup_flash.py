import importlib.util
from pathlib import Path
import tempfile
import unittest
import hashlib

spec = importlib.util.spec_from_file_location('backup', Path(__file__).resolve().parents[1] / 'tools/backup_flash.py')
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class BackupTests(unittest.TestCase):
    def test_truncated_read_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'flash.bin'
            path.write_bytes(b'partial')
            with self.assertRaises(ValueError):
                backup.digest(path, 4096)

    def test_hash_checks_entire_file(self):
        data = b'flash' * 300000
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'flash.bin'
            path.write_bytes(data)
            self.assertEqual(backup.digest(path, len(data)), hashlib.sha256(data).hexdigest())
            path.write_bytes(data[:-1] + b'!')
            self.assertNotEqual(backup.digest(path, len(data)), hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    unittest.main()
