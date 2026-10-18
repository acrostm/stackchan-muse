import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


policy = module('check_repository')
release = module('check_release')
config = module('init_config')
bundle = module('package_firmware')


class RepositoryTests(unittest.TestCase):
    def test_private_paths_and_secret_values_are_rejected(self):
        for path in ('.private/config.json', 'backups/original.bin', 'firmware/esp32/sdkconfig',
                     '.env', 'build-test/anything', 'some/signing.pem'):
            self.assertTrue(policy.inspect(path, b''), path)
        self.assertTrue(policy.inspect('normal.txt', b'mgst_' + b'A'*43))
        self.assertTrue(policy.inspect('normal.txt', b'prefix-private-value', [b'private-value']))

    def test_public_fixture_exception_does_not_exempt_other_paths(self):
        key = b'-----BEGIN ' + b'PRIVATE KEY-----'
        self.assertEqual(policy.inspect(policy.PUBLIC_FIXTURE, (ROOT / policy.PUBLIC_FIXTURE).read_bytes()), [])
        self.assertTrue(policy.inspect(policy.PUBLIC_FIXTURE, key))
        self.assertTrue(policy.inspect('other.txt', key))
        self.assertTrue(policy.inspect(policy.PUBLIC_FIXTURE, b'personal-secret', [b'personal-secret']))

    def test_initialization_preserves_existing_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'config.example.json').write_text((ROOT / 'config.example.json').read_text())
            target = config.initialize(root)
            original = target.read_bytes()
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual(target.parent.stat().st_mode & 0o777, 0o700)
            with self.assertRaises(FileExistsError):
                config.initialize(root)
            self.assertEqual(target.read_bytes(), original)

    def test_hardware_evidence_must_match_sources_and_all_checks(self):
        trees = {key: 'tree-' + key for key in ('firmware', 'companion', 'tools')}
        report = {'board': 'stackchan', 'evidence': 'docs/hardware-test.md',
                  **{key + '_tree': value for key, value in trees.items()},
                  'checks': {key: True for key in release.CHECKS}}
        release.validate(report, trees)
        report['tools_tree'] = 'stale'
        with self.assertRaises(ValueError):
            release.validate(report, trees)
        report['tools_tree'] = trees['tools']
        report['checks']['head_limits'] = False
        with self.assertRaises(ValueError):
            release.validate(report, trees)
        report['checks']['head_limits'] = 'true'
        with self.assertRaises(ValueError):
            release.validate(report, trees)

    def test_packaging_refuses_account_and_network_secrets_before_reading_binaries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for sdkconfig in ('CONFIG_GADGET_SDK_TOKEN="personal"\n',
                              'CONFIG_GADGET_SDK_TOKEN=""\nCONFIG_MUSE_LOCAL_TTS_TOKEN="personal"\n',
                              'CONFIG_GADGET_SDK_TOKEN=""\nCONFIG_HOMEHUB_WIFI_PASSWORD="personal"\n', ''):
                (root / 'sdkconfig').write_text(sdkconfig)
                with self.assertRaises(ValueError):
                    bundle.package(root, root / 'output', 'stackchan')

    def test_packaging_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'sdkconfig').write_text('CONFIG_GADGET_SDK_TOKEN=""\n')
            (root / 'flasher_args.json').write_text(json.dumps({
                'flash_settings': {}, 'flash_files': {'0': '../outside.bin'}}))
            with patch.object(bundle.subprocess, 'check_output', return_value=b'a'*40):
                with self.assertRaises(ValueError):
                    bundle.package(root, root / 'out', 'stackchan')


if __name__ == '__main__':
    unittest.main()
