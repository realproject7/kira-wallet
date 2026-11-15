"""Sell estimate batch: shared lookups, no-pool evidence and job checks. No provider calls."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import wallet as engine

BASE = 'https://api.dexscreener.com/tokens/v1/base/'
A, B, C, D = ('0x' + c * 40 for c in 'abcd')
WETH = '0x4200000000000000000000000000000000000006'


def stamp(hours):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


class UnlistedTokensTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()
        engine.BATCH.clear()

    def test_only_recent_answers_without_any_pool_count(self):
        pair = {'chainId': 'base', 'pairAddress': '0x' + 'e' * 40, 'baseToken': {'address': A}, 'quoteToken': {'address': WETH}}
        found = engine.unlisted_tokens([
            {'source': BASE + ','.join([A, B, C]), 'observed_at': stamp(0.1), 'response': [pair]},
            {'source': BASE + D, 'observed_at': stamp(2), 'response': []},
            {'source': BASE + '0x' + 'f' * 40, 'observed_at': stamp(0.1), 'response': {'transport_error': {'status': 429}}},
            {'source': 'https://api.dexscreener.com/tokens/v1/unknownchain/' + '0x' + '9' * 40, 'observed_at': stamp(0.1), 'response': []},
            {'source': BASE + '0x' + '8' * 40, 'observed_at': 'not a time', 'response': []},
        ])
        self.assertEqual(sorted(found), [(8453, B), (8453, C)], 'Listed, old, failed and unreadable answers never count as no pool.')
        self.assertEqual(found[(8453, B)]['source'], BASE + ','.join([A, B, C]))

    def test_a_token_seen_as_the_other_side_of_a_pair_is_listed(self):
        pair = {'chainId': 'base', 'pairAddress': '0x' + 'e' * 40, 'baseToken': {'address': A}, 'quoteToken': {'address': B}}
        self.assertEqual(engine.unlisted_tokens([{'source': BASE + ','.join([A, B]), 'observed_at': stamp(0.2), 'response': [pair]}]), {})

    def test_kept_answers_become_evidence_that_needs_no_lookup(self):
        records = [{'source': BASE + ','.join([A, B]), 'observed_at': stamp(0.1), 'response': []}]
        tokens = [{'chain_id': 8453, 'token_address': A, 'token_type': 'ERC20'},
                  {'chain_id': 8453, 'token_address': B, 'token_type': 'ERC1155'},
                  {'chain_id': 1, 'token_address': C, 'token_type': 'ERC20'}]
        existing = self.folder / f'dex-8453-{A}.json'
        self.assertEqual(engine.keep_unlisted(self.folder, tokens, records), 1)
        self.assertEqual(sorted(p.name for p in self.folder.glob('dex-*.json')), [existing.name])
        saved = json.loads(existing.read_text())
        self.assertEqual((saved['response'], saved['basis'], saved['source']), ([], 'dex_listing', BASE + ','.join([A, B])))
        with patch.object(engine, 'fetch', side_effect=AssertionError('no lookup expected')):
            row = engine.dex_fetch(tokens[0], self.folder, time.monotonic() + 5, attempt_limit=2)
        self.assertEqual(row['response'], [])
        existing.write_text(json.dumps({**saved, 'response': [{'kept': True}]}))
        self.assertEqual(engine.keep_unlisted(self.folder, tokens, records), 0, 'Saved evidence is never replaced.')

    def test_listings_come_from_the_batch_or_a_fresh_request_and_are_reused_for_an_hour(self):
        tokens = [{'chain_id': 8453, 'token_address': A, 'token_type': 'ERC20'}, {'chain_id': 8453, 'token_address': B, 'token_type': 'ERC20'},
                  {'chain_id': 1, 'token_address': C, 'token_type': 'ERC20'}, {'chain_id': 84532, 'token_address': D, 'token_type': 'ERC20'}]
        batch_record = {'source': BASE + ','.join([A, B]), 'observed_at': stamp(0), 'response': []}
        engine.BATCH.update(listings={'records': [{'chain_id': 8453, 'record': batch_record}], 'by_token': {(8453, A): 0, (8453, B): 0}})
        asked = []
        with patch.object(engine, 'shared_lookup', side_effect=lambda url, deadline=None: asked.append(url) or []):
            records = engine.listing_records(self.folder, tokens)
        self.assertEqual(asked, ['https://api.dexscreener.com/tokens/v1/ethereum/' + C], 'Only tokens the batch did not cover are asked; test networks never.')
        self.assertEqual(records[0], batch_record)
        with patch.object(engine, 'shared_lookup', side_effect=AssertionError('saved answers are reused')):
            self.assertEqual(engine.listing_records(self.folder, tokens), records)
        saved = json.loads((self.folder / 'token-listings.json').read_text())
        (self.folder / 'token-listings.json').write_text(json.dumps({**saved, 'saved_at': time.time() - 7200}))
        engine.BATCH.clear()
        with patch.object(engine, 'shared_lookup', return_value=[]) as fresh:
            engine.listing_records(self.folder, tokens)
        self.assertEqual(fresh.call_count, 2, 'An answer older than an hour is asked again.')


class SharedLookupTest(unittest.TestCase):
    def tearDown(self):
        engine.BATCH.clear()

    def test_a_batch_asks_each_url_once_and_shares_only_answers(self):
        engine.BATCH.update(active=True, pace=lambda: paced.append(1))
        paced, calls, gate = [], [], threading.Event()

        def fetch(url, deadline=None):
            calls.append(url)
            gate.wait(2)
            return [{'pairAddress': url[-4:]}]
        with patch.object(engine, 'fetch', side_effect=fetch):
            results = []
            threads = [threading.Thread(target=lambda: results.append(engine.shared_lookup('https://x/one', time.monotonic() + 5))) for _ in range(4)]
            for thread in threads:
                thread.start()
            time.sleep(.1)
            gate.set()
            for thread in threads:
                thread.join(5)
        self.assertEqual(calls, ['https://x/one'])
        self.assertEqual(len(paced), 1)
        self.assertEqual(results, [[{'pairAddress': '/one'}]] * 4)
        with patch.object(engine, 'fetch', side_effect=[{'transport_error': {'status': 429}}, [{'pairAddress': 'ok'}]]) as failing:
            self.assertIn('transport_error', engine.shared_lookup('https://x/two', time.monotonic() + 5))
            self.assertEqual(engine.shared_lookup('https://x/two', time.monotonic() + 5), [{'pairAddress': 'ok'}])
        self.assertEqual(failing.call_count, 2, 'A failed answer is asked again by the next wallet.')

    def test_without_a_batch_each_call_asks(self):
        with patch.object(engine, 'fetch', return_value=[]) as fetch:
            engine.shared_lookup('https://x/three')
            engine.shared_lookup('https://x/three')
        self.assertEqual(fetch.call_count, 2)


class SellBatchTest(unittest.TestCase):
    def test_pacer_spaces_starts_across_threads(self):
        import batch_sell
        pace, starts = batch_sell.Pacer(0.05), []

        def start():
            pace()
            starts.append(time.monotonic())
        began = time.monotonic()
        threads = [threading.Thread(target=start) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
        self.assertGreaterEqual(max(starts) - began, 0.145, 'Four starts take at least three intervals.')

    def test_only_sell_estimate_jobs_with_saved_holdings_join(self):
        import batch_sell
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'jobs').mkdir()
            wallet = '0x' + '1' * 40
            registry = {'wallets': [{'address': wallet, 'address_key': wallet, 'tags': ['One']}]}
            parent = {'job_id': 'p', 'result': {'snapshot_id': 'snapshots/jobs/p'}}
            sell = {'job_id': 's', 'operation': 'wallet.refresh', 'analysis_phase': 'enrichment', 'checkpoint': 'snapshots/jobs/s',
                    'parent_job_id': 'p', 'input': {'wallet': wallet}}
            holdings = {**sell, 'job_id': 'h', 'checkpoint': 'snapshots/jobs/h', 'analysis_phase': 'baseline'}
            for job in (parent, sell, holdings):
                (root / 'jobs' / f"{job['job_id']}.json").write_text(json.dumps(job))
            with patch.object(batch_sell, 'ROOT', root):
                items = batch_sell.items_for(['s', 's'], registry)
                self.assertEqual([(i.job_id, i.source, i.generation) for i in items], [('s', 'snapshots/jobs/p', 'p')])
                with self.assertRaises(SystemExit):
                    batch_sell.items_for(['h'], registry)
                removed = {**registry, 'removed_wallets': {wallet: {}}}
                self.assertEqual(batch_sell.items_for(['s'], removed), [])


if __name__ == '__main__':
    unittest.main()
