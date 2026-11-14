"""Portfolio admission and indicative quote sums, with no provider requests."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from kira_batches import submit_batch
from kira_jobs import JobError, atomic
from sell_summary import summarize_sell_out
from test_jobs import JobFixtures, ADDRESS, OTHER


class SellSummaryTests(unittest.TestCase):
    def test_missing_shared_and_excluded_quotes(self):
        rows = [{'environment':'mainnet','sell_out':{'value_usd':12.5,'observed_at':'2026-11-01'}},
                {'environment':'mainnet','sell_out':{'value_usd':7.5,'observed_at':'2026-11-02'}},
                {'environment':'mainnet','sell_out':None},
                {'environment':'mainnet','quantity_retained':True,'sell_out':{'value_usd':100}},
                {'environment':'testnet','sell_out':{'value_usd':100}},
                {'environment':'mainnet','archived':True,'sell_out':{'value_usd':100}}]
        result = summarize_sell_out(rows)
        self.assertEqual((result['value_usd'],result['quoted_count'],result['position_count'],result['missing_count']),(20,2,4,2))
        self.assertEqual((result['observed_from'],result['observed_to']),('2026-11-01','2026-11-02'))
        self.assertEqual(result['basis'],'independent_saved_quotes')
        self.assertFalse(result['combined_execution_verified']);self.assertFalse(result['gas_included'])

    def test_zero_is_known_and_missing_stays_null(self):
        self.assertIsNone(summarize_sell_out([{'environment':'mainnet'}])['value_usd'])
        self.assertIsNone(summarize_sell_out([])['value_usd'])
        self.assertEqual(summarize_sell_out([{'environment':'mainnet','sell_out':{'value_usd':0}}])['value_usd'],0)


class PortfolioTests(JobFixtures,unittest.TestCase):
    def setUp(self):
        super().setUp()
        registry=json.loads((self.root/'wallets.json').read_text())
        other=deepcopy(registry['wallets'][0]);other.update(address=OTHER,address_key=OTHER,tags=['Savings wallet'])
        registry['wallets'].append(other);atomic(self.root/'wallets.json',registry)

    def batch(self,operation='portfolio.refresh',key='portfolio-request'):
        return submit_batch(self.store,{'schema_version':1,'operation':operation,'input':{},'idempotency_key':key})

    def baseline(self,address):
        job=self.store.submit(self.request(value={'wallet':address},key='baseline-'+address))
        job.update(state='partial',result={'snapshot_id':'snapshots/prior','status':'completed_with_coverage_gaps'})
        self.store.save(job)
        return job

    def test_all_wallets_keep_individual_receipts_and_old_snapshot(self):
        before=(self.root/'snapshots/prior/results.json').read_bytes()
        first=self.batch();again=self.batch()
        self.assertEqual(len(first['jobs']),2);self.assertFalse(first['errors'])
        self.assertEqual(first,again)
        self.assertEqual({j['wallet'] for j in first['jobs']},{ADDRESS,OTHER})
        self.assertEqual(len(self.store.list()),2)
        self.assertEqual((self.root/'snapshots/prior/results.json').read_bytes(),before)

    def test_hundred_wallet_batch_reads_history_once_not_for_every_admission(self):
        import uuid
        from collections import Counter
        template=self.baseline(ADDRESS)
        history=set()
        for index in range(50):
            identity=str(uuid.uuid4());history.add(identity)
            job={**deepcopy(template),'job_id':identity,'checkpoint':'snapshots/jobs/'+identity,'key_hash':f'{index:064x}'}
            atomic(self.store.jobs/(identity+'.json'),job)
        registry=json.loads((self.root/'wallets.json').read_text())
        registry['wallets']=[{'address':f'0x{index+1:040x}','address_key':f'0x{index+1:040x}',
                              'tags':[f'Wallet {index}']} for index in range(100)]
        atomic(self.root/'wallets.json',registry)
        reads=Counter();get=self.store.get
        def counted(identity):
            if identity in history:reads[identity]+=1
            return get(identity)
        with patch.object(self.store,'get',side_effect=counted):result=self.batch()
        self.assertEqual(len(result['jobs']),100);self.assertFalse(result['errors'])
        self.assertEqual(set(reads),history)
        self.assertTrue(all(count==1 for count in reads.values()))

    def test_refresh_recovers_the_rejected_preflight_instead_of_duplicating_it(self):
        failed=self.store.submit(self.request(key='failed-preflight'))
        failed.update(state='failed',errors=[{'code':'network_scope_changed','message':'Compatibility check failed.'}])
        self.store.save(failed)
        receipt=self.batch()
        self.assertEqual(len(receipt['jobs']),2)
        self.assertIn(failed['job_id'],[j['job_id'] for j in receipt['jobs']])
        self.assertEqual(self.store.get(failed['job_id'])['state'],'queued')
        self.assertEqual(len(self.store.list()),2)

    def test_retry_recovers_a_partially_admitted_plan_without_new_wallets(self):
        original=self.store.submit;calls=0
        def interrupt(*args,**kwargs):
            nonlocal calls
            calls+=1
            if calls==2:raise RuntimeError('synthetic admission interruption')
            return original(*args,**kwargs)
        with patch.object(self.store,'submit',side_effect=interrupt):
            with self.assertRaises(RuntimeError):self.batch()
        existing=self.store.list()[0]['job_id']
        again=self.batch()
        self.assertEqual(len(again['jobs']),2);self.assertIn(existing,[j['job_id'] for j in again['jobs']])
        self.assertEqual(len(self.store.list()),2)

    def test_concurrent_batches_do_not_queue_duplicate_wallet_work(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts=list(pool.map(lambda key:self.batch(key=key),['portfolio-one','portfolio-two']))
        self.assertEqual(sum(len(r['jobs']) for r in receipts),2)
        self.assertEqual(len(self.store.list()),2)

    def test_analysis_uses_latest_baseline_and_resumes_failed_child(self):
        first=self.baseline(ADDRESS);self.baseline(OTHER)
        child=self.store.submit(self.request('job.deepen',{'job_id':first['job_id']},'manual-deepen'))
        child.update(state='interrupted');self.store.save(child)
        result=self.batch('portfolio.analyzeSell')
        self.assertEqual(len(result['jobs']),2);self.assertFalse(result['errors'])
        self.assertIn(child['job_id'],[j['job_id'] for j in result['jobs']])
        self.assertEqual(self.store.get(child['job_id'])['state'],'queued')
        self.assertTrue(all(self.store.get(j['job_id'])['analysis_phase']=='enrichment' for j in result['jobs']))

    def test_already_analyzed_and_missing_baseline_are_explicit_skips(self):
        first=self.baseline(ADDRESS)
        child=self.store.submit(self.request('job.deepen',{'job_id':first['job_id']},'manual-deepen'))
        child.update(state='partial',result={'snapshot_id':'snapshots/prior','status':'completed_with_coverage_gaps'});self.store.save(child)
        result=self.batch('portfolio.analyzeSell')
        self.assertEqual(result['jobs'],[])
        self.assertEqual({r['reason'] for r in result['skipped']},{'unchanged_holdings','holdings_refresh_required'})

    def test_request_keys_cannot_cross_single_and_batch_operations(self):
        self.batch()
        with self.assertRaises(JobError) as caught:self.store.submit(self.request(key='portfolio-request'))
        self.assertEqual(caught.exception.code,'idempotency_conflict')
        with self.assertRaises(JobError):self.batch('portfolio.analyzeSell')
        self.store.submit(self.request(key='single-request'))
        with self.assertRaises(JobError):self.batch(key='single-request')

    def test_application_and_read_only_contract(self):
        from kira_service import Application,describe_tools
        app=Application(self.root)
        with self.assertRaises(JobError):app.call('portfolio_holdings_refresh',{'idempotency_key':'readonly-request'})
        names={t['name'] for t in describe_tools()['tools']}
        self.assertTrue({'portfolio_holdings_refresh','portfolio_sell_routes_analyze'}<=names)
        with patch.object(app.jobs,'launch') as launch:
            result=app.call('portfolio_holdings_refresh',{'idempotency_key':'application-request'},allow_write=True)
            self.assertEqual(len(result['jobs']),2);launch.assert_called_once()
        registry=json.loads((self.root/'wallets.json').read_text());registry['demo']=True;atomic(self.root/'wallets.json',registry)
        with self.assertRaises(JobError) as caught:app.submit({'schema_version':1,'operation':'portfolio.refresh','input':{},'idempotency_key':'demo-request'})
        self.assertEqual(caught.exception.code,'demo_read_only')
