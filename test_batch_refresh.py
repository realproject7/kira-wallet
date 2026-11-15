"""Batch refresh orchestration: each wallet keeps its own job, folder and outcome."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import batch_refresh
import wallet as engine

sys.path.insert(0, str(Path(__file__).parent / 'viewer'))

WALLETS = ['0x' + format(0xc0 + i, '040x') for i in range(4)]


class BatchRefreshTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        engine.atomic(self.root / 'wallets.json', {'wallets': [{'address': w, 'address_key': w, 'tags': [f'W{i}']} for i, w in enumerate(WALLETS)], 'research_runs': []})
        engine.atomic(self.root / 'networks.json', {'networks': [{'chain_id': 8453, 'network': 'base', 'name': 'Base', 'environment': 'mainnet',
                                                                  'mintclub_bond_address': '0x' + '9' * 40}]})
        self.jobs = []
        for i, w in enumerate(WALLETS):
            job_id = f'00000000-0000-4000-8000-00000000000{i}'
            engine.atomic(self.root / 'jobs' / f'{job_id}.json', {'job_id': job_id, 'operation': 'wallet.refresh', 'checkpoint': 'snapshots/jobs/' + job_id,
                                                                  'input': {'wallet': w, 'scope': 'fast'}, 'cancel_requested': i == 3})
            self.jobs.append(job_id)
        self.patches = [patch.object(batch_refresh, 'ROOT', self.root), patch.object(engine, 'ROOT', self.root)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    def test_wallets_share_the_run_but_keep_their_own_outcome(self):
        seen = {'prepare': [], 'finish': [], 'fallback': [], 'events': []}

        def prepare(wallet, folder, networks, scope):
            seen['prepare'].append((engine.CONTEXT.job_id, wallet['address']))
            engine.atomic(folder / 'scan-input.json', {'wallet': wallet['address'], 'candidates': []})
            return {'plan': {'retained': {}, 'chains': {}}, 'discovered': [], 'scope': scope}

        class Helper:
            def __init__(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def call(self, mode, source, destination=None, timeout=None):
                assert mode == 'batch-scan'
                batch = json.loads(Path(source).read_text())
                # The second wallet's read does not finish in the batch; it is read on its own.
                for row in batch['wallets'][:1] + batch['wallets'][2:]:
                    engine.atomic(Path(row['folder']) / 'onchain-summary.json', {'chains': []})

        def fallback(mode, source, destination, on_chain=None, deadline=None):
            seen['fallback'].append(engine.CONTEXT.job_id)
            engine.atomic(Path(destination) / 'onchain-summary.json', {'chains': []})

        def finish(wallet, folder, networks, prepared, pipeline=None):
            seen['finish'].append((engine.CONTEXT.job_id, engine.CONTEXT.generation))
            self.assertEqual(pipeline, {'batch_size': 4})
            self.assertTrue(engine.BATCH.get('active'))
            if wallet['address'] == WALLETS[2]:
                raise ValueError('synthetic pricing stop')
            return {'status': 'completed', 'counts': {}}

        def source_check(networks, folder):
            engine.atomic(folder / 'mintclub-support.json', {'checked': True})

        output = io.StringIO()
        with patch.object(engine, 'prepare_holdings', side_effect=prepare), patch.object(engine, 'NodeHelper', Helper), \
                patch.object(engine, 'run_node', side_effect=fallback), patch.object(engine, 'finish_holdings', side_effect=finish), \
                patch.object(engine, 'source_check', side_effect=source_check), patch.object(batch_refresh, 'held_tokens', return_value=({}, set())), \
                patch.object(batch_refresh.MarketLookups, 'fetch', return_value=None), patch.object(engine, 'prune_resume_checkpoints') as prune, \
                patch('token_images.refresh_catalog') as artwork, contextlib.redirect_stdout(output):
            code = batch_refresh.run(self.jobs, 'fast')
        self.assertEqual(code, 1, 'A failed wallet is reported.')
        # The batch names its jobs in the usage ledger, and its id does not outlive the run.
        usage = [json.loads(line) for path in (self.root / 'usage').glob('alchemy-*.jsonl') for line in path.read_text().splitlines()]
        self.assertEqual([(row['source'], row['jobs'], row['scope']) for row in usage], [('batch', self.jobs, 'fast')])
        self.assertTrue(usage[0]['batch'].startswith('batch-'))
        self.assertNotIn('KIRA_BATCH_ID', os.environ)
        lines = [json.loads(line) for line in output.getvalue().splitlines()]
        folders = [self.root / 'snapshots/jobs' / job for job in self.jobs]
        # The cancelled wallet was not prepared; every other wallet ran under its own job.
        self.assertEqual(sorted(seen['prepare']), sorted((self.jobs[i], WALLETS[i]) for i in range(3)))
        self.assertEqual(seen['fallback'], [self.jobs[1]])
        self.assertEqual(sorted(job for job, _ in seen['finish']), sorted(self.jobs[:3]))
        self.assertTrue(all(job == generation for job, generation in seen['finish']), 'A wallet publishes under its own research generation.')
        runs = [json.loads((folder / 'run.json').read_text()) for folder in folders]
        self.assertEqual([r['status'] for r in runs], ['completed', 'completed', 'failed', 'running'])
        self.assertEqual(runs[2]['error_code'], 'engine_failed')
        self.assertTrue(all((folder / 'mintclub-support.json').exists() for folder in folders))
        published = [line['job_id'] for line in lines if line.get('stage') == 'published']
        self.assertEqual(sorted(published), sorted(self.jobs[:2]))
        self.assertEqual([line['job_id'] for line in lines if line.get('stage') == 'failed'], [self.jobs[2]])
        summary = next(line for line in lines if line.get('stage') == 'batch_summary')
        self.assertEqual((summary['wallets'], summary['failed'], summary['cancelled']), (4, 1, 1))
        self.assertTrue((self.root / 'cache/batch-refresh-last.json').exists())
        self.assertEqual(prune.call_count, 4)
        artwork.assert_called_once()
        self.assertEqual(engine.BATCH, {});self.assertIsNone(engine.NODE_HELPER)
        self.assertEqual(list((self.root / 'cache/batch-refresh').iterdir()), [], 'The batch work folder is removed.')

    def test_a_failed_catalogue_check_fails_every_wallet_with_its_code(self):
        def source_check(networks, folder):
            raise engine.NetworkScopeError('Mint Club SDK network/deployment scope changed. Reconcile networks.json before analysis.')
        with patch.object(engine, 'source_check', side_effect=source_check), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(batch_refresh.run(self.jobs[:2], 'full'), 1)
        for job in self.jobs[:2]:
            run = json.loads((self.root / 'snapshots/jobs' / job / 'run.json').read_text())
            self.assertEqual((run['status'], run['error_code']), ('failed', 'network_scope_changed'))

    def test_only_holdings_refresh_jobs_are_accepted(self):
        job = json.loads((self.root / 'jobs' / f'{self.jobs[0]}.json').read_text())
        engine.atomic(self.root / 'jobs' / f'{self.jobs[0]}.json', {**job, 'operation': 'prices.refresh'})
        with self.assertRaises(SystemExit):
            batch_refresh.run(self.jobs[:1], 'fast')


class SharedLookupTest(unittest.TestCase):
    def test_pricing_uses_the_batch_records_for_its_tokens_and_the_index_for_unlisted_ones(self):
        token = lambda address, **extra: {'chain_id': 8453, 'token_address': address, 'token_type': 'ERC20', 'wallet_balance_raw': '1', **extra}
        listed, unlisted = '0x' + '1' * 40, '0x' + '2' * 40
        pair = {'chainId': 'base', 'pairAddress': '0x' + '3' * 40, 'baseToken': {'address': listed, 'symbol': 'L'}, 'quoteToken': {'address': '0x' + '4' * 40, 'symbol': 'Q'},
                'priceUsd': '2.5', 'liquidity': {'usd': 500000, 'base': 1000}, 'url': 'https://dexscreener.com/base/' + '3' * 40, 'dexId': 'uniswap'}
        record = {'source': 'https://api.dexscreener.com/tokens/v1/base/' + listed + ',' + unlisted, 'observed_at': '2026-11-15T00:00:00Z', 'response': [pair]}
        snapshot = {'tokens': [token(listed), token(unlisted)], 'coverage': [{'chain_id': 8453, 'environment': 'mainnet'}]}
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            engine.BATCH.update(active=True, images=True, dex={'records': [{'chain_id': 8453, 'record': record}], 'by_token': {(8453, listed): 0, (8453, unlisted): 0}},
                                index={'prices': {(8453, unlisted): {'chain_id': 8453, 'address': unlisted, 'usd': 0.5, 'basis': 'Market index', 'quality': 'estimated'}},
                                       'asked': {(8453, unlisted)}, 'observed_at': '2026-11-15T00:00:00Z'})
            try:
                with patch.object(engine, 'fetch', side_effect=AssertionError('Batch records answer every token.')), \
                        patch('curve_pricing.index_prices', side_effect=AssertionError('The batch asked the index already.')), \
                        contextlib.redirect_stdout(io.StringIO()):
                    market = engine.refresh_metadata(snapshot, {'tokens': []}, folder, discover_prices=True)
            finally:
                engine.BATCH.clear()
            prices = {p['address']: p for p in market['tokens']}
            self.assertEqual(prices[unlisted]['basis'], 'Market index')
            self.assertIn(listed, prices)
            evidence = json.loads((folder / 'token-market-metadata.json').read_text())
            self.assertEqual([r['source'] for r in evidence], [record['source']])
            self.assertEqual(json.loads((folder / 'index-prices.json').read_text())['tokens'][0]['address'], unlisted)

    def test_a_token_the_index_answered_without_a_price_waits_a_day(self):
        missing, priced = (8453, '0x' + '5' * 40), (8453, '0x' + '6' * 40)
        with tempfile.TemporaryDirectory() as temp, patch.object(engine, 'ROOT', Path(temp)):
            calls = []
            def answer(keys, folder, deadline=None):
                calls.append(sorted(keys))
                return {'tokens': [{'chain_id': 8453, 'address': priced[1], 'usd': 1.0, 'basis': 'Market index'}] if priced in keys else [],
                        'status': 'checked', 'answered': set(keys)}
            with patch('curve_pricing.index_prices', side_effect=answer):
                first = engine.index_lookup([missing, priced], Path(temp), None)
                second = engine.index_lookup([missing, priced], Path(temp), None)
            self.assertEqual([p['address'] for p in first], [priced[1]])
            self.assertEqual(calls, [sorted([missing, priced]), [priced]], 'The unpriced token is skipped for a day; the priced one is asked again.')
            saved = json.loads((Path(temp) / 'cache/index-price-misses.json').read_text())['tokens']
            self.assertEqual(list(saved), [f'{missing[0]}:{missing[1]}'])

    def test_the_index_is_asked_only_about_tokens_it_priced_before_or_new_ones(self):
        kept, spam, fresh = (8453, '0x' + '7' * 40), (8453, '0x' + '8' * 40), (8453, '0x' + '9' * 40)
        hint = {'held': {kept, spam}, 'priced': {kept}}
        self.assertEqual(sorted(engine.worth_asking([kept, spam, fresh], hint)), sorted([kept, fresh]))
        self.assertEqual(sorted(engine.worth_asking([kept, spam, fresh], None)), sorted([kept, spam, fresh]), 'Without a saved snapshot every token is asked.')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            engine.atomic(root / 'snapshots/w/results.json', {'tokens': [{'chain_id': 8453, 'token_address': kept[1].upper().replace('0X', '0x'), 'indexer_price_references': [{'value': '1'}]},
                                                                        {'chain_id': 8453, 'token_address': spam[1]}]})
            engine.atomic(root / 'snapshots/w/market-prices.json', {'tokens': [{'chain_id': 8453, 'address': fresh[1], 'basis': 'Market index'}]})
            with patch.object(engine, 'ROOT', root):
                found = engine.index_hint({'latest_snapshot': {'directory': 'snapshots/w'}})
            self.assertEqual(found['held'], {kept, spam})
            self.assertEqual(found['priced'], {kept, fresh})
            with patch.object(engine, 'ROOT', root):
                self.assertIsNone(engine.index_hint({'latest_snapshot': {'directory': 'snapshots/missing'}}))

    def test_each_explorer_host_keeps_its_own_pace(self):
        import time
        import public_discovery
        starts = []
        with patch.object(public_discovery, '_last', {}), patch.object(public_discovery, 'fetch_bounded', side_effect=lambda url, *a, **k: starts.append((url, time.monotonic())) or {}):
            began = time.monotonic()
            for url in ('https://shibariumscan.io/a', 'https://cyberscan.co/a', 'https://shibariumscan.io/b', 'https://api.example.org/a', 'https://api.example.org/b'):
                public_discovery.fetch_page(url, 5)
        at = {url: moment - began for url, moment in starts}
        self.assertLess(at['https://cyberscan.co/a'], .1, 'Another host does not wait.')
        self.assertGreaterEqual(at['https://shibariumscan.io/b'] - at['https://shibariumscan.io/a'], .24)
        self.assertGreaterEqual(at['https://api.example.org/b'] - at['https://api.example.org/a'], .99, 'Keyless indexers keep one request a second.')

    def test_explorer_pacing_hosts_match_the_explorer_catalogue(self):
        from urllib.parse import urlparse
        import explorer_discovery
        import public_discovery
        self.assertEqual(public_discovery.EXPLORER_HOSTS, {urlparse(url).hostname for url in explorer_discovery.HOSTS.values()})


class NodeHelperTest(unittest.TestCase):
    def test_requests_answer_in_any_order_and_progress_reaches_its_job(self):
        script = """
const readline=require('node:readline');
readline.createInterface({input:process.stdin}).on('line',line=>{
  const r=JSON.parse(line);
  if(r.mode==='slow')setTimeout(()=>process.stdout.write(JSON.stringify({helper_id:r.id,ok:true})+'\\n'),300);
  else if(r.mode==='fail')process.stdout.write(JSON.stringify({helper_id:r.id,ok:false,error:{message:'synthetic failure'}})+'\\n');
  else if(r.mode==='never'){}
  else{process.stdout.write(JSON.stringify({job_id:'job-1',stage:'chain',chain_id:1})+'\\n');process.stdout.write(JSON.stringify({stage:'untagged'})+'\\n');
       process.stdout.write(JSON.stringify({helper_id:r.id,ok:true})+'\\n');}
}).on('close',()=>process.exit(0));
"""
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'node-helper.cjs').write_text(script)
            output = io.StringIO()
            with patch.object(engine, 'ASSETS', Path(temp)), contextlib.redirect_stdout(output):
                with engine.NodeHelper() as helper:
                    import threading
                    done = []
                    slow = threading.Thread(target=lambda: (helper.call('slow', 'in.json', timeout=5), done.append('slow')))
                    slow.start()
                    helper.call('fast', 'in.json', timeout=5)
                    done.append('fast')
                    slow.join()
                    with self.assertRaisesRegex(ValueError, 'synthetic failure'):
                        helper.call('fail', 'in.json', timeout=5)
                    with self.assertRaises(TimeoutError):
                        helper.call('never', 'in.json', timeout=.2)
            self.assertEqual(done, ['fast', 'slow'], 'A quick request is not held behind a slow one.')
            lines = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(lines, [{'job_id': 'job-1', 'stage': 'chain', 'chain_id': 1}], 'Only job progress is passed on.')


if __name__ == '__main__':
    unittest.main()
