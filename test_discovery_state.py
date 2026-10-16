"""Recovery from interrupted and corrupted discovery frontier writes."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import discovery_state as storage

WALLET = '0x' + '1' * 40


class DiscoveryStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / '1.json'
        self.state = {'schema_version': 2, 'wallet': WALLET, 'chain_id': 1,
                      'contracts': [], 'pending_ranges': [{'startblock': 0, 'endblock': 20, 'page': 1}]}

    def save(self, state):
        storage.save(self.path, state, WALLET, 1, 'etherscan_keyless')

    def load(self):
        return storage.load(self.path, WALLET, 1, 'etherscan_keyless')

    def test_large_candidate_set_roundtrips_in_bounded_verified_segments(self):
        self.state['contracts'] = ['0x' + format(i, '040x') for i in range(12001)]
        self.save(self.state)
        self.assertEqual(self.load(), {**self.state, 'provider': 'etherscan_keyless'})
        manifest = json.loads(self.path.read_text())
        self.assertNotIn('contracts', manifest['state'])
        self.assertEqual(len(manifest['sections']['contracts']), 24)
        self.assertLess(self.path.stat().st_size, 8000)
        self.assertTrue(all(d['count'] <= 512 for d in manifest['sections']['contracts']))

    def test_interruption_before_manifest_commit_keeps_previous_frontier_and_candidates(self):
        self.save(self.state)
        before = self.path.read_bytes()
        advanced = copy.deepcopy(self.state)
        advanced['pending_ranges'][0]['page'] = 2
        advanced['contracts'] = ['0x' + '2' * 40]
        replace = storage.os.replace
        def interrupt(source, destination):
            if Path(destination) == self.path:
                raise OSError('synthetic interruption')
            return replace(source, destination)
        with patch.object(storage.os, 'replace', side_effect=interrupt):
            with self.assertRaises(OSError):
                self.save(advanced)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.load()['pending_ranges'][0]['page'], 1)
        self.assertEqual(self.load()['contracts'], [])
        self.save(advanced)
        self.assertEqual(self.load()['contracts'], advanced['contracts'])
        self.assertEqual(self.load()['pending_ranges'][0]['page'], 2)

    def test_corrupt_missing_and_path_traversal_segments_fail_closed(self):
        self.state['contracts'] = ['0x' + '2' * 40]
        self.save(self.state)
        original = self.path.read_bytes()
        manifest = json.loads(original)
        digest = manifest['sections']['contracts'][0]['sha256']
        chunk = self.path.parent / '1.chunks' / (digest + '.json')
        content = chunk.read_bytes()
        chunk.write_text('[]')
        with self.assertRaisesRegex(ValueError, 'digest'):
            self.load()
        chunk.unlink()
        with self.assertRaises(OSError):
            self.load()
        chunk.write_bytes(content)
        manifest['sections']['contracts'][0]['sha256'] = '../../outside'
        self.path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'reference'):
            self.load()
        self.path.write_bytes(original)
        self.assertEqual(self.load()['contracts'], self.state['contracts'])

    def test_legacy_inline_migrates_without_discarding_candidates_or_accepting_foreign_identity(self):
        self.path.write_text(json.dumps(self.state))
        self.assertEqual(self.load(), self.state)
        self.save(self.load())
        for key, value in [('wallet', '0x' + '3' * 40), ('chain_id', 2), ('chain_id', True), ('provider', 'routescan')]:
            wrong = {**self.state, key: value}
            with self.assertRaisesRegex(ValueError, 'identity'):
                self.save(wrong)
        self.assertEqual(self.load()['wallet'], WALLET)


if __name__ == '__main__':
    unittest.main()
