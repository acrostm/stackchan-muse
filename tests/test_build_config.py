import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


class BuildConfigTests(unittest.TestCase):
    def test_rebuilding_without_relay_clears_existing_destination(self):
        path = Path(__file__).resolve().parents[1] / 'tools/build_firmware.py'
        spec = importlib.util.spec_from_file_location('build_firmware', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / '.private').mkdir()
            (root / '.private/config.json').write_text(json.dumps({'network': {'tls_relay_host': '192.168.1.5'}}))
            build = root / 'build-musestack-cores3'
            build.mkdir()
            config = build / 'sdkconfig'
            config.write_text('CONFIG_MUSE_TLS_RELAY_HOST=""\nCONFIG_UNRELATED=y\n')
            with patch.object(module, 'ROOT', root), patch.object(module.subprocess, 'run', return_value=SimpleNamespace(returncode=0)):
                for flags, expected in [(['--with-relay'], '192.168.1.5'), ([], '')]:
                    with patch('sys.argv', ['build_firmware.py', '--board', 'cores3', *flags]), self.assertRaises(SystemExit) as end:
                        module.main()
                    self.assertEqual(end.exception.code, 0)
                    text = config.read_text()
                    self.assertIn('CONFIG_MUSE_TLS_RELAY_HOST=' + json.dumps(expected), text)
                    self.assertEqual(text.count('CONFIG_MUSE_TLS_RELAY_HOST='), 1)
                    self.assertIn('CONFIG_UNRELATED=y', text)
