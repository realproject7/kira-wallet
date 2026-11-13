"""Ownership claims, scope, accounting, recovery and saved-view load limits."""
from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import tempfile
import time
import unittest
from unittest.mock import patch
from kira_cli import initialize
from kira_jobs import atomic, JobError
from kira_service import Application
from positions import allocation, valued, prices
from position_worker import projection, publish, prepare
from viewer.test_viewer import fixture_snapshot

A='0x'+'1'*40;B='0x'+'2'*40;TOKEN='0x'+'3'*40;RECEIPT='0x'+'4'*40
PRICE={'usd':2,'quality':'estimated','basis':'Market index','source':'https://example.com/price','observed_at':'2026-11-13T00:00:00Z'}


def position(identity='pool',platform='uniswap',amount='10',**kw):
    return {'id':identity,'platform':platform,'protocol':platform,'scope':'8453:'+platform,'chain_id':8453,'version':'v3','observed_at':'2026-11-13T00:00:00Z','block_number':'100','block_hash':'0x'+'a'*64,
            'assets':[{'address':TOKEN,'symbol':'SAMPLE','decimals':18,'amount':amount,'amount_raw':str(int(amount)*10**18)}],**kw}


def wallet(address=A):
    return {'key':address,'name':'Savings','positions':[],'position_coverage':[],'assets':[{'id':'8453:'+TOKEN,'chain_id':8453,'address':TOKEN,'environment':'mainnet','included_in_totals':True,'balance':'5','value_usd':10,'price':dict(PRICE)}]}


class PositionAccountingTests(unittest.TestCase):
    def test_receipt_excluded_once_and_underlying_not_duplicated(self):
        w=wallet();w['assets'].append({'id':'8453:'+RECEIPT,'chain_id':8453,'environment':'mainnet','included_in_totals':True,'value_usd':9999})
        p=valued(position(receipt={'address':RECEIPT,'custody':'wallet'}),prices([w]));w['positions']=[p,p]
        s=allocation([w]);self.assertEqual(s['known_value_usd'],30);self.assertEqual(s['position_count'],1)
        self.assertAlmostEqual(sum(g['percent'] for g in s['groups']),100)
        self.assertEqual(allocation([w],token_id='8453:'+TOKEN)['known_value_usd'],30)
        self.assertEqual(allocation([w],token_id='8453:'+RECEIPT)['known_value_usd'],20)

    def test_unpriced_principal_cannot_become_zero_or_inflate_total(self):
        p=position();p['assets'].append({'address':RECEIPT,'symbol':'OTHER','amount':'50'})
        p=valued(p,{'8453:'+TOKEN:PRICE});self.assertIsNone(p['value_usd']);self.assertEqual(p['known_component_value_usd'],20)
        w=wallet();w['positions']=[p];s=allocation([w]);self.assertEqual(s['known_value_usd'],10);self.assertEqual(s['unpriced_count'],1)
        p['assets'][1]['amount']='0';self.assertEqual(valued(p,{'8453:'+TOKEN:PRICE})['value_usd'],20)

    def test_nested_staked_vault_and_aeromax_are_exclusive(self):
        w=wallet();w['positions']=[valued(position(platform='lptoken',custody_platform='mintclub-staking'),prices([w])),valued(position('aero','aeromax',protocol='aerodrome'),prices([w]))]
        s=allocation([w]);self.assertEqual(s['known_value_usd'],50)
        self.assertEqual({g['id'] for g in s['groups']},{'wallet','lptoken','aeromax'})

    def test_invalid_and_testnet_prices_do_not_value_a_claim(self):
        w=wallet();w['assets'][0]['environment']='testnet';self.assertFalse(prices([w]))
        w['assets'][0]['environment']='mainnet';w['assets'][0]['price']['usd']=float('nan');self.assertFalse(prices([w]))
        w['assets'][0]['price']=dict(PRICE);w['assets'][0]['included_in_totals']=False;self.assertFalse(prices([w]))
        p=position();p['assets'][0]['amount']='NaN';self.assertIsNone(valued(p,{})['value_usd'])

    def test_excluded_receipt_cannot_reenter_totals_through_a_claim(self):
        w=wallet();w['assets'].append({'id':'8453:'+RECEIPT,'chain_id':8453,'included_in_totals':False})
        w['positions']=[valued(position(receipt={'address':RECEIPT,'custody':'wallet'}),prices([w]))]
        self.assertEqual(allocation([w])['known_value_usd'],10)
        self.assertEqual(allocation([w])['position_count'],0)

    def test_token_scope_counts_only_its_underlying(self):
        p=position();p['assets'].append({'address':RECEIPT,'amount':'50','symbol':'OTHER'})
        w=wallet();w['positions']=[valued(p,{'8453:'+TOKEN:PRICE,'8453:'+RECEIPT:{**PRICE,'usd':1}})]
        self.assertEqual(allocation([w])['known_value_usd'],80)
        self.assertEqual(allocation([w],token_id='8453:'+TOKEN)['known_value_usd'],30)
        self.assertEqual(allocation([w],chain_id=1)['groups'],[])


class PositionApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'KIRA_DATA_DIR':str(self.root),'KIRA_CONFIG':str(self.root/'.kira.local.json')});self.env.start();initialize(self.root)
        rows=[]
        for i,address in enumerate((A,B)):
            folder=f'snapshots/fixture/{i}';snapshot=fixture_snapshot();snapshot['wallet_address']=address;atomic(self.root/folder/'results.json',snapshot)
            rows.append({'address':address,'address_key':address,'tags':['Savings' if i==0 else 'Treasury'],'latest_snapshot':{'directory':folder,'result':folder+'/results.json'}})
        atomic(self.root/'wallets.json',{'schema_version':1,'wallets':rows,'research_runs':[]})
        self.app=Application(self.root);self.provider=patch.object(self.app.jobs,'require_connection');self.provider.start()
        self.no_network=patch.object(socket.socket,'connect',side_effect=AssertionError('Saved view contacted a provider'));self.no_network.start()
    def tearDown(self):self.no_network.stop();self.provider.stop();self.env.stop();self.temp.cleanup()
    def job(self,address=A,key='position-refresh-test'):
        return self.app.submit({'schema_version':1,'operation':'positions.refresh','input':{'wallet':address},'idempotency_key':key},launch=False)
    def state(self,rows=None,**kw):
        return {'wallet':A,'positions':{p['id']:p for p in rows or []},'coverage':{'8453:uniswap':{'id':'8453:uniswap','chain_id':8453,'status':'checked','errors':0}},'tasks':[],'cursor':0,'blocks':{},'complete':True,**kw}
    def test_job_coalesces_distinct_keys_without_changing_holdings_generation(self):
        before=(self.root/'wallets.json').read_bytes();a=self.job();b=self.job(key='position-refresh-second')
        self.assertEqual(a['job_id'],b['job_id']);self.assertEqual((self.root/'wallets.json').read_bytes(),before)
        self.assertIn('position_worker.py',self.app.jobs.engine_command(a)[1])
        self.assertEqual(self.app.jobs.get(a['job_id'])['operation'],'positions.refresh')

    def test_repeat_refresh_defaults_to_known_claims_and_full_discovery_is_explicit(self):
        job=self.job();job['attempt']=1;publish(self.root,job,self.state([position()]));job.update(state='succeeded',result=self.app.jobs.publication(job));self.app.jobs.save(job)
        known=self.job(key='refresh-known-positions');self.assertFalse(known['input']['discover'])
        full=self.app.submit({'schema_version':1,'operation':'positions.refresh','input':{'wallet':A,'discover':True},'idempotency_key':'find-new-positions'},launch=False)
        self.assertTrue(full['input']['discover']);self.assertNotEqual(known['job_id'],full['job_id'])

    def test_pause_resume_remove_guard_and_batch(self):
        a=self.job();revision=self.app.call('wallets_removed',{})['revision']
        with self.assertRaisesRegex(JobError,'work in progress'):
            self.app.submit({'schema_version':1,'operation':'wallet.remove','input':{'wallets':[A],'expected_revision':revision},'idempotency_key':'remove-active-positions'},launch=False)
        self.app.jobs.submit({'schema_version':1,'operation':'job.cancel','input':{'job_id':a['job_id']},'idempotency_key':'cancel-platform-scan'})
        resumed=self.app.jobs.submit({'schema_version':1,'operation':'job.resume','input':{'job_id':a['job_id']},'idempotency_key':'resume-platform-scan'})
        self.assertEqual(resumed['job_id'],a['job_id'])
        batch=self.app.submit({'schema_version':1,'operation':'portfolio.positionsRefresh','input':{},'idempotency_key':'batch-platform-refresh'},launch=False)
        self.assertEqual(len(batch['jobs']),2);self.assertEqual(len(batch['skipped']),0)
        self.assertIn(a['job_id'],[j['job_id'] for j in batch['jobs']])

    def test_global_scan_admits_wallets_waiting_for_holdings_and_coalesces_modes(self):
        baseline=self.app.submit({'schema_version':1,'operation':'wallet.refresh','input':{'wallet':A},'idempotency_key':'holdings-before-positions'},launch=False)
        known=self.app.submit({'schema_version':1,'operation':'positions.refresh','input':{'wallet':B,'discover':False},'idempotency_key':'known-before-full'},launch=False)
        batch=self.app.submit({'schema_version':1,'operation':'portfolio.positionsRefresh','input':{'discover':True},'idempotency_key':'all-wallet-platform-full'},launch=False)
        self.assertEqual(len(batch['jobs']),2);self.assertFalse(batch['skipped']);self.assertFalse(batch['errors'])
        self.assertEqual({j['wallet'] for j in batch['jobs']},{A,B})
        self.assertTrue(all(self.app.jobs.get(j['job_id'])['input']['discover'] for j in batch['jobs']))
        self.assertNotIn(known['job_id'],[j['job_id'] for j in batch['jobs']])
        self.assertEqual(self.app.jobs.get(baseline['job_id'])['state'],'queued')

    def test_exclusion_applies_to_staked_receipt_even_without_a_loose_balance(self):
        p=position(receipt={'address':RECEIPT,'custody':'mintclub-staking'})
        job=self.job();job['attempt']=1;publish(self.root,job,self.state([p]))
        atomic(self.root/'token-policy.json',{'overrides':{'8453:'+RECEIPT:{'mode':'exclude'}},'risk_checks':{}})
        saved=self.app.views.positions();self.assertFalse(saved['positions'][0]['included_in_totals'])
        self.assertEqual(saved['allocation']['position_count'],0)

    def test_retired_networks_are_not_reintroduced_by_platform_scans(self):
        job=self.job();inp=prepare(self.root,job)
        self.assertFalse({5112,54176,666666666}&{n['chain_id'] for n in inp['networks']})

    def test_partial_results_keep_prior_claims_and_completed_empty_removes_them(self):
        job=self.job();job['attempt']=1;publish(self.root,job,self.state([position()]))
        initial=self.app.views.positions();self.assertEqual(initial['matched_count'],1)
        partial=self.state(coverage={'8453:uniswap':{'id':'8453:uniswap','status':'partial','errors':1}})
        saved=publish(self.root,job,partial);self.assertTrue(saved['positions'][0]['retained'])
        saved=publish(self.root,job,self.state());self.assertEqual(saved['positions'],[])
        self.assertEqual(self.app.views.positions()['matched_count'],0)

    def test_progress_publication_is_visible_and_final_receipt_recovers(self):
        job=self.job();job['attempt']=1
        state=self.state([position()],complete=False,tasks=[{'scope':'8453:uniswap','chain_id':8453}],cursor=0)
        publish(self.root,job,state);self.assertEqual(self.app.views.positions()['matched_count'],1)
        self.assertEqual(self.app.views.refresh()['wallets'][0]['positions_scan_status'],'in_progress')
        self.assertIsNone(self.app.jobs.publication(job))
        publish(self.root,job,self.state([position()]));(self.root/job['checkpoint']/'positions-publication.json').unlink()
        self.assertEqual(self.app.jobs.publication(job)['position_count'],1)

    def test_scoped_api_pages_and_underlying_only_token_view(self):
        job=self.job();job['attempt']=1;publish(self.root,job,self.state([position(str(i)) for i in range(105)]))
        from kira_folders import action
        with self.app.jobs.locked():
            f=action(self.app.jobs,{'schema_version':1,'operation':'folder.create','input':{'name':'Treasury only'},'idempotency_key':'create-position-folder'})
        with self.app.jobs.locked():action(self.app.jobs,{'schema_version':1,'operation':'folder.assign','input':{'folder_id':f['folder_id'],'wallets':[B]},'idempotency_key':'assign-position-folder'})
        self.assertEqual(len(self.app.views.positions(limit=50)['positions']),50)
        self.assertEqual(self.app.views.positions(offset=100)['matched_count'],105)
        self.assertEqual(self.app.views.positions(folder_id=f['folder_id'])['matched_count'],0)
        token=self.app.views.token(8453,TOKEN);self.assertEqual(token['wallet_count'],0)
        self.assertEqual(token['capital_allocation']['position_count'],105)
        compact=self.app.views.overview();self.assertTrue(all(not w['positions'] for w in compact['wallets']))

    def test_continuation_stops_without_progress_and_metadata_removal_preserves_saved_files(self):
        job=self.job();job['attempt']=1;publish(self.root,job,self.state([position()]))
        atomic(self.root/job['checkpoint']/'continuation.json',{'fingerprint':'a'*64,'not_before':0})
        for _ in range(4):self.app.jobs.queue_continuation(job,JobError('research_pending','Saved a slice'))
        self.assertEqual(job['state'],'interrupted')
        self.assertEqual(job['errors'][0]['code'],'no_progress')

    def test_100_wallets_15000_claims_views_do_not_start_research(self):
        wallets=[]
        for i in range(100):
            w=wallet('0x'+format(i+10,'040x'));w['positions']=[valued(position(str(j)),{'8453:'+TOKEN:PRICE}) for j in range(150)];wallets.append(w)
        start=time.monotonic();s=allocation(wallets);elapsed=time.monotonic()-start
        self.assertEqual(s['position_count'],15000);self.assertEqual(s['known_value_usd'],301000)
        self.assertLess(elapsed,5)


if __name__=='__main__':unittest.main()
