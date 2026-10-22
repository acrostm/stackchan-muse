import unittest
from tools.check_dependency_lock import constraints, validate


class ConstraintsTests(unittest.TestCase):
    def test_only_registry_versions_are_pinned_and_optional_stays_optional(self):
        expected = {'dependencies': {
            'vendor/optional': {'version': '1.2.3~2', 'component_hash': 'abc',
                                'source': {'type': 'service'}},
            'idf': {'version': '6.0.1', 'source': {'type': 'idf'}}}}
        self.assertEqual(constraints(expected), 'vendor/optional==1.2.3~2\n')
        validate(expected, {'dependencies': {}, 'target': 'esp32s3'})
        for version, digest in [('1.2.4', 'abc'), ('1.2.3~2', 'changed')]:
            with self.assertRaises(ValueError):
                validate(expected, {'dependencies': {'vendor/optional': {
                    'version': version, 'component_hash': digest}}, 'target': 'esp32s3'})
