import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from onboarding import readiness


class OnboardingReadinessTests(unittest.TestCase):
    def test_no_discovery_is_limited_even_if_an_unused_key_exists(self):
        config = {'rpc': {'mode': 'public'}, 'discovery': {'provider': 'none', 'key_env': 'TEST_INDEXER_KEY'}}
        with patch('onboarding.load_config', return_value=config), patch('onboarding.secret_values', return_value={'TEST_INDEXER_KEY': 'private-test-value'}):
            self.assertFalse(readiness()['discovery_key_available'])

    def test_indexer_key_readiness_never_returns_values_or_reference_names(self):
        config = {'rpc': {'mode': 'custom'}, 'discovery': {'provider': 'alchemy', 'key_env': 'TEST_INDEXER_KEY'}}
        for values, expected in [({}, False), ({'TEST_INDEXER_KEY': 'private-test-value'}, True)]:
            with patch('onboarding.load_config', return_value=config), patch('onboarding.secret_values', return_value=values):
                result = readiness()
                self.assertEqual(result['discovery_key_available'], expected)
                self.assertTrue(result['discovery_configured'])
                self.assertNotIn('private-test-value', json.dumps(result))
                self.assertNotIn('TEST_INDEXER_KEY', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
