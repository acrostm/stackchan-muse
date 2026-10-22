import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


class BuildConfigTests(unittest.TestCase):
    def _module(self):
        path = Path(__file__).resolve().parents[1] / 'tools/build_firmware.py'
        spec = importlib.util.spec_from_file_location('build_firmware', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_rebuilding_without_relay_clears_existing_destination(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / '.private').mkdir()
            (root / 'docs').mkdir()
            (root / 'docs/firmware-dependencies.lock.yml').write_text(
                (Path(__file__).resolve().parents[1] / 'docs/firmware-dependencies.lock.yml').read_text())
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

    def test_camera_profile_is_stackchan_only(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / '.private').mkdir()
            (root / 'docs').mkdir()
            (root / 'docs/firmware-dependencies.lock.yml').write_text(
                (Path(__file__).resolve().parents[1] / 'docs/firmware-dependencies.lock.yml').read_text())
            build = root / 'build-musestack-camera'
            build.mkdir()
            with patch.object(module, 'ROOT', root), patch.object(
                    module.subprocess, 'run',
                    return_value=SimpleNamespace(returncode=0)) as run:
                with patch('sys.argv', ['build_firmware.py', '--with-camera']), \
                        patch.dict('sys.modules', {'yaml': None}):
                    with self.assertRaises(SystemExit) as end:
                        module.main()
            self.assertEqual(end.exception.code, 0)
            overlay = root / '.private/sdkconfig-camera.defaults'
            self.assertIn('CONFIG_MUSE_STACKCHAN_CAMERA=y', overlay.read_text())
            generator = run.call_args_list[0].args[0]
            self.assertTrue(generator[0].endswith('idf6.0_py3.14_env/bin/python'))
            self.assertIn('--write-constraints', generator)
            command = run.call_args.args[0]
            self.assertTrue(any(value.endswith('sdkconfig-camera.defaults') for value in command))

        with patch('sys.argv', ['build_firmware.py', '--board', 'cores3', '--with-camera']), \
                self.assertRaises(SystemExit) as end:
            module.main()
        self.assertEqual(end.exception.code, 2)

    def test_handsfree_profile_has_separate_geometry_and_post_build_checks(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / '.private').mkdir()
            (root / 'docs').mkdir()
            (root / 'docs/firmware-dependencies.lock.yml').write_text(
                (Path(__file__).resolve().parents[1] / 'docs/firmware-dependencies.lock.yml').read_text())
            with patch.object(module, 'ROOT', root), patch.object(
                    module.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
                with patch('sys.argv', ['build_firmware.py', '--with-handsfree']), self.assertRaises(SystemExit) as end:
                    module.main()
            self.assertEqual(end.exception.code, 0)
            overlay = (root / '.private/sdkconfig-handsfree.defaults').read_text()
            self.assertIn('CONFIG_MUSE_HANDSFREE=y', overlay)
            self.assertIn('partitions_muse_handsfree.csv', overlay)
            build_env = run.call_args_list[0].kwargs['env']
            self.assertIn('IDF_COMPONENT_CONSTRAINT_FILES', build_env)
            self.assertNotIn('IDF_COMPONENT_CONSTRAINTS', build_env)
            commands = [call.args[0] for call in run.call_args_list]
            self.assertTrue(any(any(str(arg).endswith('check_speech_model.py') for arg in command) for command in commands))
            self.assertTrue(any(any(str(arg).endswith('check_dependency_lock.py') for arg in command) for command in commands))
        with patch('sys.argv', ['build_firmware.py', '--board', 'cores3', '--with-handsfree']), self.assertRaises(SystemExit) as end:
            module.main()
        self.assertEqual(end.exception.code, 2)
