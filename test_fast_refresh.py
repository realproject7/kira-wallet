"""Fast refresh: what it builds on, how it is requested, and what it leaves unchanged."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import kira_cli
from kira_batches import submit_batch
from kira_config import default_config, provider_config
from kira_jobs import JobError, JobStore, atomic, read
import wallet

ADDRESS = '0x' + '1' * 40
OTHER = '0x' + '2' * 40
TOKEN = '0x' + '3' * 40
NFT = '0x' + '4' * 40
NETWORKS = [{'chain_id': 8453, 'environment': 'mainnet'}, {'chain_id': 10, 'environment': 'mainnet'},
            {'chain_id': 84532, 'environment': 'testnet'}, {'chain_id': 11155111, 'environment': 'testnet'}]


class FastRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        kira_cli.initialize(self.root)
        self.env = patch.dict(os.environ, {'KIRA_DATA_DIR': str(self.root), 'KIRA_CONFIG': str(self.root / '.kira.local.json')})
        self.env.start(); self.addCleanup(self.env.stop); self.addCleanup(self.temp.cleanup)
        config = provider_config(default_config(), 'alchemy', 'KIRA_FAST_FIXTURE')
        config['secret_env_file'] = str(self.root / 'fixture.env')
        atomic(self.root / '.kira.local.json', config)
        (self.root / 'fixture.env').write_text('KIRA_FAST_FIXTURE=fixture-only-key\n')

    def saved(self, chains, wallet_address=ADDRESS, discovery=True):
        """A latest snapshot with the given chain rows, like a published holdings run."""
        folder = self.root / 'snapshots/fixture/previous'
        atomic(folder / 'onchain-summary.json', {'wallet': wallet_address, 'chains': chains})
        atomic(folder / 'results.json', {'wallet_address': wallet_address, 'pipeline': {'phase': 'holdings'}, 'tokens': []})
        if discovery:
            for row in chains:
                atomic(folder / f"discovery-{row['chain_id']}.json", {'wallet': wallet_address, 'chain_id': row['chain_id'], 'complete': True, 'tokens': []})
        entry = {'address': ADDRESS, 'address_key': ADDRESS, 'tags': ['Fixture'],
                 'latest_snapshot': {'directory': 'snapshots/fixture/previous', 'result': 'snapshots/fixture/previous/results.json'}}
        atomic(self.root / 'wallets.json', {'wallets': [entry], 'research_runs': []})
        return entry

    def row(self, chain_id, *, complete=True, block='100', tokens=(), **extra):
        return {'wallet': ADDRESS, 'chain_id': chain_id, 'rpc_status': 'available', 'observed_at': '2026-11-14T01:00:00Z',
                'registry_scan': {'complete': complete, 'block_number': block, **extra}, 'tokens': list(tokens)}

    def test_plan_reads_history_after_a_complete_check_and_keeps_test_networks(self):
        held = [{'token_address': TOKEN, 'token_type': 'ERC20'}, {'token_address': NFT, 'token_type': 'ERC1155'},
                {'token_address': 'not-an-address', 'token_type': 'ERC20'}, {'token_address': OTHER, 'token_type': 'ERC721'}]
        entry = self.saved([self.row(8453, block='5000', tokens=held), self.row(10, complete=False), self.row(84532)])
        with patch.object(wallet, 'ROOT', self.root):
            plan = wallet.fast_plan(entry, NETWORKS)
        # The window starts 1,000 blocks before the saved check, for transfers the index had not listed yet.
        self.assertEqual(plan['chains']['8453'], {'from_block': '4001', 'full_check_block': '5000', 'full_checked_at': '2026-11-14T01:00:00Z',
                                                  'prior': [{'address': TOKEN, 'token_type': 'ERC20'}, {'address': NFT, 'token_type': 'ERC1155'}]})
        self.assertNotIn('10', plan['chains'], 'An incomplete saved check is read in full.')
        self.assertEqual(set(plan['retained']), {84532}, 'Only saved test networks are kept.')
        kept, found = plan['retained'][84532]
        self.assertEqual(kept['retained_from'], 'snapshots/fixture/previous'); self.assertEqual(found['chain_id'], 84532)

    def test_plan_carries_the_last_full_check_through_fast_refreshes(self):
        entry = self.saved([self.row(8453, block='200', method='transfer_delta', full_check_block='100', full_checked_at='2026-11-01T00:00:00Z')])
        with patch.object(wallet, 'ROOT', self.root):
            chain = wallet.fast_plan(entry, NETWORKS)['chains']['8453']
        self.assertEqual((chain['from_block'], chain['full_check_block'], chain['full_checked_at']), ('0', '100', '2026-11-01T00:00:00Z'), 'Early blocks start at zero.')

    def test_no_saved_holdings_or_another_wallet_means_a_full_check(self):
        with patch.object(wallet, 'ROOT', self.root):
            self.assertEqual(wallet.fast_plan({'address_key': ADDRESS}, NETWORKS), {'retained': {}, 'chains': {}})
            entry = self.saved([self.row(8453)], wallet_address=OTHER)
            self.assertEqual(wallet.fast_plan(entry, NETWORKS), {'retained': {}, 'chains': {}})
            entry = self.saved([{**self.row(8453), 'wallet': OTHER}])
            self.assertEqual(wallet.fast_plan(entry, NETWORKS)['chains'], {})
            entry = self.saved([self.row(84532)], discovery=False)
            self.assertEqual(wallet.fast_plan(entry, NETWORKS)['retained'], {}, 'A test network without saved discovery is read again.')
            entry['latest_snapshot']['directory'] = '../outside'
            self.assertEqual(wallet.fast_plan(entry, NETWORKS), {'retained': {}, 'chains': {}})

    def test_fast_holdings_skip_kept_networks_and_record_the_scope(self):
        entry = self.saved([self.row(8453), self.row(84532, tokens=[{'token_address': TOKEN, 'token_type': 'ERC20', 'chain_id': 84532}])])
        folder = self.root / 'snapshots/fixture/fast'; folder.mkdir(parents=True)
        seen = {}

        def scan(mode, source, destination, on_chain=None):
            data = read(source); seen.update(networks=[n['chain_id'] for n in data['networks']], fast=data.get('fast'))
            atomic(destination / 'onchain-summary.json', {'wallet': ADDRESS, 'chains': [self.row(n['chain_id']) for n in data['networks']]})

        captured = {}

        def result(wallet_entry, out, networks, discovered, chains, **options):
            captured.update(chains=chains, discovered=discovered, **options); return {'status': 'completed'}

        with patch.object(wallet, 'ROOT', self.root), patch.object(wallet, 'discover', side_effect=lambda address, n, out, **_: {'wallet': address, 'chain_id': n['chain_id'], 'complete': True, 'tokens': []}) as discover, \
                patch.object(wallet, 'prior_candidates', return_value=[]), patch.object(wallet, 'run_node', side_effect=scan), patch.object(wallet, 'initial_result', side_effect=result):
            wallet.research_holdings(entry, folder, NETWORKS[:3], scope='fast')
        self.assertEqual(sorted(call.args[1]['chain_id'] for call in discover.call_args_list), [10, 8453], 'Kept networks need no discovery.')
        self.assertEqual(seen['networks'], [8453, 10]); self.assertEqual(seen['fast']['chains']['8453']['from_block'], '0')
        self.assertEqual([c['chain_id'] for c in captured['chains']], [8453, 10, 84532])
        self.assertEqual(captured['chains'][2]['retained_from'], 'snapshots/fixture/previous')
        self.assertEqual(captured['pipeline'], {'refresh_scope': 'fast', 'retained_networks': [84532]})
        self.assertTrue((folder / 'discovery-84532.json').exists(), 'Sell analysis finds every network\'s discovery evidence.')
        # A full refresh reads everything and passes no fast plan.
        seen.clear(); captured.clear()
        with patch.object(wallet, 'ROOT', self.root), patch.object(wallet, 'discover', side_effect=lambda address, n, out, **_: {'wallet': address, 'chain_id': n['chain_id'], 'complete': True, 'tokens': []}), \
                patch.object(wallet, 'prior_candidates', return_value=[]), patch.object(wallet, 'run_node', side_effect=scan), patch.object(wallet, 'initial_result', side_effect=result):
            wallet.research_holdings(entry, self.root / 'snapshots/fixture/full', NETWORKS[:3])
        self.assertEqual(seen['networks'], [8453, 10, 84532]); self.assertIsNone(seen['fast'])
        self.assertEqual(captured['pipeline'], {'refresh_scope': 'full'})

    def test_refresh_requests_accept_scope_and_keep_full_fingerprints(self):
        atomic(self.root / 'wallets.json', {'wallets': [{'address': ADDRESS, 'address_key': ADDRESS, 'tags': ['Fixture']}], 'research_runs': []})
        store = JobStore(self.root)
        with patch.object(JobStore, 'launch'):
            full = store.submit({'schema_version': 1, 'operation': 'wallet.refresh', 'input': {'wallet': ADDRESS}, 'idempotency_key': 'full-refresh'})
            self.assertEqual(full['input'], {'wallet': ADDRESS}); self.assertNotIn('--scope', store.engine_command(full))
            same = store.submit({'schema_version': 1, 'operation': 'wallet.refresh', 'input': {'wallet': ADDRESS, 'scope': 'full'}, 'idempotency_key': 'full-explicit'})
            self.assertEqual(same['input'], {'wallet': ADDRESS}, 'An explicit full scope is the default request.')
            with self.assertRaises(JobError) as bad:
                store.submit({'schema_version': 1, 'operation': 'wallet.refresh', 'input': {'wallet': ADDRESS, 'scope': 'quick'}, 'idempotency_key': 'bad-scope'})
            self.assertEqual(bad.exception.code, 'invalid_scope')
            for job_id in [j['job_id'] for j in store.list()]:
                job = store.get(job_id); job.update(state='partial', stage='published'); store.save(job)
            fast = store.submit({'schema_version': 1, 'operation': 'wallet.refresh', 'input': {'wallet': 'Fixture', 'scope': 'fast'}, 'idempotency_key': 'fast-refresh'})
        self.assertEqual(fast['input'], {'wallet': ADDRESS, 'scope': 'fast'})
        command = store.engine_command(fast)
        self.assertEqual(command[command.index('--scope') + 1], 'fast'); self.assertIn('holdings', command)
        self.assertEqual(store.get(fast['job_id'])['input']['scope'], 'fast', 'The saved envelope keeps its scope.')
        # Sell analysis after a fast refresh reads that saved holdings run; scope does not apply.
        parent = store.get(fast['job_id']); parent.update(result={'snapshot_id': 'snapshots/fixture/fast'}); store.save(parent)
        sell = store.engine_command({**parent, 'analysis_phase': 'enrichment', 'parent_job_id': fast['job_id']})
        self.assertIn('sell', sell); self.assertNotIn('--scope', sell)

    def test_portfolio_fast_refresh_queues_fast_wallet_jobs(self):
        atomic(self.root / 'wallets.json', {'wallets': [{'address': a, 'address_key': a, 'tags': [name]} for a, name in ((ADDRESS, 'One'), (OTHER, 'Two'))], 'research_runs': []})
        store = JobStore(self.root)
        with patch.object(JobStore, 'launch'):
            receipt = submit_batch(store, {'schema_version': 1, 'operation': 'portfolio.refresh', 'input': {'scope': 'fast'}, 'idempotency_key': 'fast-portfolio'})
            self.assertEqual(len(receipt['jobs']), 2)
            self.assertTrue(all(store.get(row['job_id'])['input'].get('scope') == 'fast' for row in receipt['jobs']))
            for value in ({'scope': 'quick'}, {'scope': 'fast', 'discover': True}):
                with self.assertRaises(JobError):
                    submit_batch(store, {'schema_version': 1, 'operation': 'portfolio.refresh', 'input': value, 'idempotency_key': 'bad-' + str(len(value))})
            with self.assertRaises(JobError):
                submit_batch(store, {'schema_version': 1, 'operation': 'portfolio.analyzeSell', 'input': {'scope': 'fast'}, 'idempotency_key': 'sell-scope'})


if __name__ == '__main__':
    unittest.main()
