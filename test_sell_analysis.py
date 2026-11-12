"""Saved quantity reuse and admission safety. All fixtures are offline."""
from copy import deepcopy
import json
import socket
import unittest
from unittest.mock import patch
from kira_jobs import atomic, JobError
from kira_batches import submit_batch
from sell_analysis import assess, analysis_index, quantities, reuse_estimates
from test_jobs import JobFixtures, ADDRESS, OTHER, TOKEN


class SellAnalysisTests(JobFixtures, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.offline=patch.object(socket.socket,'connect',side_effect=AssertionError('Unexpected provider request'))
        self.offline.start()

    def tearDown(self):
        self.offline.stop()
        super().tearDown()

    def saved_analysis(self):
        baseline=self.store.submit(self.request(key='first-baseline'))
        baseline.update(state='partial',result={'snapshot_id':'snapshots/prior'})
        self.store.save(baseline)
        child=self.store.submit(self.request('job.deepen',{'job_id':baseline['job_id']},'first-analysis'))
        self.snapshot(child['checkpoint'],'1.000000000000000001')
        path=self.root/child['checkpoint']/'results.json'
        value=json.loads(path.read_text())
        value['coverage']=[{'chain_id':1,'environment':'mainnet','native_balance':'0','rpc_status':'available','indexer_complete':True}]
        atomic(path,value)
        child.update(state='partial',result={'snapshot_id':child['checkpoint']})
        self.store.save(child)
        return child

    def refreshed(self, balance='1.000000000000000001'):
        self.snapshot('snapshots/current',balance)
        path=self.root/'snapshots/current/results.json';value=json.loads(path.read_text())
        value['compiled_at']='2026-11-12T00:00:00Z'
        value['coverage']=[{'chain_id':1,'environment':'mainnet','native_balance':'0','rpc_status':'available','indexer_complete':True}]
        atomic(path,value)
        baseline=self.store.submit(self.request(key='second-baseline'))
        baseline.update(state='partial',result={'snapshot_id':'snapshots/current'});self.store.save(baseline)
        registry=json.loads((self.root/'wallets.json').read_text())
        registry['wallets'][0]['latest_snapshot']={'directory':'snapshots/current','result':'snapshots/current/results.json'}
        atomic(self.root/'wallets.json',registry)
        return registry['wallets'][0],baseline

    def portfolio_request(self, key):
        return {'schema_version':1,'operation':'portfolio.analyzeSell','input':{},'idempotency_key':key}

    def edit(self, change):
        path=self.root/'snapshots/current/results.json';value=json.loads(path.read_text());change(value);atomic(path,value)

    def test_price_block_time_and_decimal_format_do_not_require_analysis(self):
        child=self.saved_analysis();entry,_=self.refreshed()
        self.edit(lambda v:v.update(price_references={'ETH_USD':{'value':9000}},compiled_at='2026-11-13T00:00:00Z'))
        self.edit(lambda v:v['tokens'][0].update(wallet_balance='1.0000000000000000010',balance_block_number='999',symbol='NEW NAME'))
        result=assess(self.root,entry)
        self.assertEqual(result['status'],'current');self.assertFalse(result['needs_analysis'])
        self.assertEqual(result['job_id'],child['job_id'])
        self.assertEqual(result['last_analyzed_at'],'2026-10-03T00:00:00Z')

    def test_one_wei_difference_and_large_raw_integers_are_exact(self):
        self.saved_analysis();entry,_=self.refreshed('1.000000000000000002')
        self.assertEqual(assess(self.root,entry)['changed_count'],1)
        analysis=analysis_index(self.root)[ADDRESS]
        path=self.root/analysis['snapshot_id']/'results.json';value=json.loads(path.read_text())
        value['tokens'][0]['wallet_balance_raw']='900719925474099300000000000000001';atomic(path,value)
        self.edit(lambda v:v['tokens'][0].update(wallet_balance_raw='900719925474099300000000000000002'))
        self.assertEqual(assess(self.root,entry)['status'],'changed')

    def test_balance_retention_or_missing_chain_is_unverified_not_a_sale(self):
        self.saved_analysis();entry,_=self.refreshed()
        self.edit(lambda v:v['tokens'][0].update(balance_evidence_retained=True))
        self.assertEqual(assess(self.root,entry)['status'],'unverified')
        self.edit(lambda v:v.update(tokens=[],coverage=[{'chain_id':1,'rpc_status':'unavailable'}]))
        result=assess(self.root,entry)
        self.assertEqual(result['status'],'unverified');self.assertFalse(result['needs_analysis'])
        self.edit(lambda v:v.update(coverage=[{'chain_id':1,'native_balance':'0','rpc_status':'available','indexer_complete':True}]))
        self.assertEqual(assess(self.root,entry)['status'],'changed')

    def test_native_and_new_contract_or_chain_changes_require_analysis(self):
        self.saved_analysis();entry,_=self.refreshed()
        self.edit(lambda v:v['coverage'][0].update(native_balance='0.000000000000000001'))
        self.assertEqual(assess(self.root,entry)['changed_count'],1)
        self.edit(lambda v:v['tokens'][0].update(token_address='0x'+'b'*40))
        self.assertEqual(assess(self.root,entry)['changed_count'],3)

    def test_wallet_identity_and_snapshot_path_cannot_cross(self):
        self.saved_analysis();entry,_=self.refreshed()
        self.assertIsNone(quantities(self.root,'snapshots/current',OTHER))
        self.assertIsNone(quantities(self.root,'snapshots/../../other',ADDRESS))
        self.assertIsNone(quantities(self.root,'/etc/passwd',ADDRESS))
        entry={**entry,'address_key':OTHER}
        self.assertEqual(assess(self.root,entry)['status'],'holdings_required')

    def test_single_and_global_admission_reuse_without_new_provider_work(self):
        child=self.saved_analysis();entry,baseline=self.refreshed()
        before=(self.root/child['checkpoint']/'results.json').read_bytes()
        again=self.store.submit(self.request('job.deepen',{'job_id':baseline['job_id']},'same-balances'))
        self.assertEqual(again['job_id'],child['job_id']);self.assertEqual(again['state'],'partial')
        self.assertEqual(len(self.store.list()),3)
        self.assertEqual(self.store.submit(self.request('job.deepen',{'job_id':baseline['job_id']},'same-balances'))['job_id'],child['job_id'])
        result=submit_batch(self.store,self.portfolio_request('portfolio-same'))
        self.assertEqual(result['jobs'],[]);self.assertEqual(result['skipped'][0]['reason'],'unchanged_holdings')
        self.assertEqual((self.root/child['checkpoint']/'results.json').read_bytes(),before)

    def test_changed_balances_admit_once_and_unverified_balances_wait(self):
        child=self.saved_analysis();entry,baseline=self.refreshed('2')
        result=submit_batch(self.store,self.portfolio_request('portfolio-changed'))
        self.assertEqual(len(result['jobs']),1)
        self.assertNotEqual(result['jobs'][0]['job_id'],child['job_id'])
        self.assertEqual(self.store.get(result['jobs'][0]['job_id'])['parent_job_id'],baseline['job_id'])
        retry=submit_batch(self.store,self.portfolio_request('portfolio-changed'))
        self.assertEqual(retry,result)

    def test_unverified_single_and_global_actions_cannot_queue_again(self):
        self.saved_analysis();entry,baseline=self.refreshed()
        self.edit(lambda v:v['tokens'][0].update(balance_evidence_retained=True))
        with self.assertRaises(JobError) as raised:
            self.store.submit(self.request('job.deepen',{'job_id':baseline['job_id']},'unverified-balances'))
        self.assertEqual(raised.exception.code,'holdings_unverified')
        result=submit_batch(self.store,self.portfolio_request('portfolio-unverified'))
        self.assertEqual(result['jobs'],[]);self.assertEqual(result['skipped'][0]['reason'],'holdings_unverified')

    def test_matching_positions_keep_old_quote_times_not_new_prices(self):
        self.saved_analysis();entry,_=self.refreshed()
        summary=assess(self.root,entry);current=quantities(self.root,'snapshots/current',ADDRESS)
        old=quantities(self.root,summary['snapshot_id'],ADDRESS)
        identity='1:'+TOKEN
        prior={'assets':[{'id':identity,'sell_out':{'value_usd':12,'observed_at':'old-quote-time','price_observed_at':'old-price-time'},'exit_quote':{'block_number':'100'}}]}
        wallet={'assets':[{'id':identity,'value_usd':999,'sell_out':None}]}
        reuse_estimates(wallet,prior,current,old,summary)
        self.assertEqual(wallet['assets'][0]['value_usd'],999)
        self.assertEqual(wallet['assets'][0]['sell_out']['observed_at'],'old-quote-time')
        self.assertEqual(wallet['assets'][0]['sell_out']['price_observed_at'],'old-price-time')
        self.assertTrue(wallet['assets'][0]['sell_analysis_provenance']['reused'])
        self.edit(lambda v:v['tokens'][0].update(wallet_balance='2'))
        changed={'assets':[{'id':identity,'sell_out':None}]}
        reuse_estimates(changed,prior,quantities(self.root,'snapshots/current',ADDRESS),old,summary)
        self.assertIsNone(changed['assets'][0]['sell_out'])
