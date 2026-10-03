"""Synthetic persistence and crash-boundary acceptance. No provider calls."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

from kira_jobs import JobStore, JobError, atomic, digest
ADDRESS='0x'+'1'*40
OTHER='0x'+'2'*40
TOKEN='0x'+'a'*40

class JobFixtures:

    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.root=Path(self.directory.name);self.store=JobStore(self.root)
        atomic(self.root/'wallets.json',{'schema_version':1,'wallets':[{'address':ADDRESS,'address_key':ADDRESS,'tags':['Original'],
            'latest_snapshot':{'directory':'snapshots/prior','result':'snapshots/prior/results.json'}}],'research_runs':[]})
        self.snapshot('snapshots/prior','1.000000000000000001')
        self.env=patch.dict(os.environ,{'KIRA_DATA_DIR':str(self.root),'KIRA_CONFIG':str(self.root/'.kira.local.json')});self.env.start()
    def tearDown(self):self.env.stop();self.directory.cleanup()
    def snapshot(self,path,balance,status='completed_with_coverage_gaps'):
        atomic(self.root/path/'results.json',{'schema_version':1,'wallet_address':ADDRESS,'compiled_at':'2026-10-03T00:00:00Z','status':status,
            'coverage':[{'chain_id':1,'complete':False}],'tokens':[{'chain_id':1,'token_address':TOKEN,'wallet_balance':balance,'symbol':'SYNTHETIC','dex_pools':[],
                'mintclub':None,'indexer_price_references':[]}],'price_references':{}})
    def request(self,operation='wallet.refresh',value=None,key='synthetic-request'):
        return {'schema_version':1,'operation':operation,'input':value or {'wallet':ADDRESS},'idempotency_key':key}
    def running(self):
        job=self.store.submit(self.request());job['state']='running';job['attempt']=1;self.store.save(job);return job
    def publish(self,job,completed_manifest=True):
        self.snapshot(job['checkpoint'],'2.0')
        atomic(self.root/job['checkpoint']/'run.json',{'wallet_address':ADDRESS,**({'completed_at':'now'} if completed_manifest else {'status':'running'})})
        registry=json.loads((self.root/'wallets.json').read_text());registry['wallets'][0]['latest_snapshot']={'directory':job['checkpoint']};atomic(self.root/'wallets.json',registry)
class JobsTest(JobFixtures, unittest.TestCase):
    def test_duplicate_and_key_conflict(self):
        a=self.store.submit(self.request());b=self.store.submit(self.request());self.assertEqual(a['job_id'],b['job_id'])
        with self.assertRaises(JobError) as error:self.store.submit(self.request('prices.refresh'))
        self.assertEqual(error.exception.code,'idempotency_conflict')
        self.assertNotIn('synthetic-request',(self.store.jobs/(a['job_id']+'.json')).read_text())
    def test_concurrent_duplicate(self):
        with ThreadPoolExecutor(max_workers=8) as executor:jobs=list(executor.map(lambda _:self.store.submit(self.request()),range(16)))
        self.assertEqual(len({j['job_id'] for j in jobs}),1)
    def test_schema_and_unknown_fields(self):
        for request in [{**self.request(),'schema_version':2},{**self.request(),'schema_version':True},{**self.request(),'unexpected':1},self.request(value={'wallet':ADDRESS,'shell':'do something'})]:
            with self.assertRaises(JobError):self.store.submit(request)
    def test_address_and_exact_tags(self):
        with self.assertRaises(JobError):self.store.submit(self.request('wallet.add',{'address':'not-a-wallet','tag':'Synthetic'}))
        job=self.store.submit(self.request('wallet.add',{'address':OTHER,'tag':'  Exact tag  '}));self.assertEqual(job['input']['tag'],'  Exact tag  ')
    def test_ambiguous_tag_rejected(self):
        value=json.loads((self.root/'wallets.json').read_text());value['wallets'].append({'address_key':OTHER,'tags':['Original']});atomic(self.root/'wallets.json',value)
        with self.assertRaises(JobError):self.store.submit(self.request(value={'wallet':'Original'}))
    def test_restart_queued_never_replays_provider(self):
        job=self.store.submit(self.request());self.store.recover();self.assertEqual(self.store.get(job['job_id'])['state'],'queued')
    def test_restart_interrupted_and_explicit_resume(self):
        job=self.running();self.store.recover();self.assertEqual(self.store.get(job['job_id'])['state'],'interrupted')
        resumed=self.store.submit(self.request('job.resume',{'job_id':job['job_id']},'resume-test'))
        self.assertEqual(resumed['state'],'queued');self.assertEqual(resumed['previous_result']['directory'],'snapshots/prior')
        self.assertEqual(self.store.submit(self.request('job.resume',{'job_id':job['job_id']},'resume-test'))['attempt'],1)
    def test_partial_publication_recovers_without_rerun(self):
        job=self.running();self.publish(job);self.store.recover();saved=self.store.get(job['job_id'])
        self.assertEqual(saved['state'],'partial');self.assertEqual(saved['attempt'],1)
        with self.assertRaises(JobError):self.store.submit(self.request('job.resume',{'job_id':job['job_id']},'resume-partial'))
        self.assertEqual(self.store.submit(self.request())['job_id'],job['job_id'])
    def test_crash_between_registry_and_manifest(self):
        job=self.running();self.publish(job,completed_manifest=False);self.store.recover();self.assertEqual(self.store.get(job['job_id'])['state'],'partial')
    def test_cancel_queued_and_resume(self):
        job=self.store.submit(self.request());cancel=self.request('job.cancel',{'job_id':job['job_id']},'cancel-test');self.assertEqual(self.store.submit(cancel)['state'],'cancelled')
        self.assertEqual(self.store.submit(cancel)['state'],'cancelled')
        self.assertEqual(self.store.submit(self.request('job.resume',{'job_id':job['job_id']},'resume-test'))['state'],'queued')
    def test_request_receipt_crash(self):
        job=self.store.submit(self.request());(self.store.jobs/'requests'/(digest('synthetic-request')+'.json')).unlink()
        self.assertEqual(self.store.submit(self.request())['job_id'],job['job_id'])
    def test_control_receipt_crash(self):
        job=self.store.submit(self.request());cancel=self.request('job.cancel',{'job_id':job['job_id']},'cancel-test');self.store.submit(cancel)
        (self.store.jobs/'requests'/(digest('cancel-test')+'.json')).unlink();self.assertEqual(self.store.submit(cancel)['state'],'cancelled')
    def test_tag_duplicate_after_selector_changed(self):
        request=self.request('wallet.setTags',{'wallet':'Original','tags':['Renamed']});job=self.store.submit(request);self.store.worker()
        self.assertEqual(self.store.get(job['job_id'])['state'],'succeeded');self.assertEqual(self.store.submit(request)['job_id'],job['job_id'])
        self.assertEqual(self.store.wallet(ADDRESS)['tags'],['Renamed'])
    def test_comparison_precision_missing_not_zero_chain_identity(self):
        self.snapshot('snapshots/new','1.000000000000000002');value=json.loads((self.root/'snapshots/new/results.json').read_text())
        value['tokens'].append({**value['tokens'][0],'chain_id':8453,'wallet_balance':'999'});atomic(self.root/'snapshots/new/results.json',value)
        result=self.store.compare('snapshots/prior','snapshots/new');rows={r['chain_id']:r for r in result['positions']}
        self.assertEqual(rows[1]['balance_delta'],'1E-18');self.assertIsNone(rows[8453]['balance_delta']);self.assertIsNone(rows[8453]['before_balance'])
    def test_snapshot_path_escape_and_foreign_wallet(self):
        for path in ['../wallets.json','snapshots/../../wallets.json','/etc/passwd']:
            with self.assertRaises(JobError):self.store.snapshot(path)
        self.snapshot('snapshots/new','1');value=json.loads((self.root/'snapshots/new/results.json').read_text());value['wallet_address']=OTHER;atomic(self.root/'snapshots/new/results.json',value)
        with self.assertRaises(JobError):self.store.compare('snapshots/prior','snapshots/new')
    def test_safe_errors_and_evidence_links(self):
        value=json.loads((self.root/'snapshots/prior/results.json').read_text());value['tokens'][0].update(source_url='https://mint.club/token/base/'+TOKEN,mintclub_error={'message':'https://provider.test/secret-key'})
        atomic(self.root/'snapshots/prior/results.json',value);saved=self.store.snapshot('snapshots/prior')
        self.assertEqual(saved['tokens'][0]['source_url'],value['tokens'][0]['source_url']);self.assertNotIn('secret-key',json.dumps(saved))
    def test_price_receipt_before_projection_recovered(self):
        job=self.store.submit(self.request('prices.refresh'));job['state']='running';self.store.save(job)
        value={'observed_at':'2026-10-03T01:00:00Z','tokens':[],'snapshot_id':'snapshots/prior','job_result_status':'completed_with_coverage_gaps'}
        atomic(self.root/job['checkpoint']/'prices.json',value);self.store.recover()
        self.assertEqual(self.store.get(job['job_id'])['state'],'partial');self.assertEqual(json.loads((self.root/'snapshots/prior/market-prices.json').read_text()),value)
    def test_failed_engine_preserves_prior_result(self):
        job=self.store.submit(self.request())
        with patch.object(self.store,'execute',side_effect=JobError('engine_failed','Synthetic failure.')):self.store.worker()
        saved=self.store.get(job['job_id']);self.assertEqual(saved['state'],'failed');self.assertEqual(saved['previous_result']['directory'],'snapshots/prior')
        self.assertEqual(self.store.wallet(ADDRESS)['latest_snapshot']['directory'],'snapshots/prior')
    def test_settings_reference_validation_and_write(self):
        value={'mode':'custom','chains':[{'chain_id':8453,'url_env':'KIRA_BASE_RPC'}],'allow_public_fallback':False}
        job=self.store.submit(self.request('settings.rpc',value));self.store.worker();self.assertEqual(self.store.get(job['job_id'])['state'],'succeeded')
        config=json.loads((self.root/'.kira.local.json').read_text());self.assertEqual(config['rpc']['chains']['8453']['url_env'],'KIRA_BASE_RPC')
        value['chains'][0]['url_env']='https://secret-endpoint.test/key'
        with self.assertRaises(JobError):self.store.submit(self.request('settings.rpc',value,'invalid-settings'))


class WorkerProcessTest(JobFixtures, unittest.TestCase):
    # Inherit the synthetic fixture setup, but only run process-specific cases.
    def worker_process(self,case):
        env={k:v for k,v in os.environ.items() if not k.startswith(('KIRA_','ALCHEMY_'))}
        env.update(KIRA_DATA_DIR=str(self.root),KIRA_CONFIG=str(self.root/'.kira.local.json'))
        return subprocess.Popen([sys.executable,str(Path(__file__).parent/'fixtures/jobs/worker.py'),str(self.root),case],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    def wait_for(self,condition):
        import time
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            if condition():return
            time.sleep(.03)
        self.fail('Synthetic process did not reach its expected state.')
    def test_supervisor_restart_waits_for_engine_lease(self):
        job=self.store.submit(self.request());first=self.worker_process('publish');second=None
        try:
            self.wait_for(lambda:(self.root/'invocations').exists());first.kill();first.wait()
            second=self.worker_process('publish');second.wait(timeout=8)
            saved=self.store.get(job['job_id']);self.assertEqual(saved['state'],'partial');self.assertEqual(saved['attempt'],1)
            self.assertEqual((self.root/'invocations').read_text().splitlines(),['engine'])
            self.assertEqual(saved['chains']['1']['block_number'],'123')
        finally:
            if first.poll() is None:first.terminate();first.wait(timeout=8)
            if second and second.poll() is None:second.terminate();second.wait(timeout=8)
    def test_publication_wins_cancel_race(self):
        job=self.store.submit(self.request());worker=self.worker_process('publish-wait')
        try:
            self.wait_for(lambda:(self.root/'published-marker').exists())
            self.store.submit(self.request('job.cancel',{'job_id':job['job_id']},'cancel-published'))
            worker.wait(timeout=8);saved=self.store.get(job['job_id'])
            self.assertEqual(saved['state'],'partial');self.assertEqual(saved['result']['snapshot_id'],job['checkpoint'])
            self.assertEqual((self.root/'invocations').read_text().splitlines(),['engine'])
        finally:
            if worker.poll() is None:worker.terminate();worker.wait(timeout=8)
    def test_cancel_stops_descendants_and_preserves_evidence(self):
        import time
        job=self.store.submit(self.request());worker=self.worker_process('wait')
        try:
            self.wait_for(lambda:(self.root/'heartbeat').exists())
            self.store.submit(self.request('job.cancel',{'job_id':job['job_id']},'cancel-worker'))
            worker.wait(timeout=8);self.assertEqual(self.store.get(job['job_id'])['state'],'cancelled')
            heartbeat=(self.root/'heartbeat').read_text();time.sleep(.2);self.assertEqual((self.root/'heartbeat').read_text(),heartbeat)
            self.assertTrue((self.root/job['checkpoint']/'run.json').exists());self.assertEqual(self.store.wallet(ADDRESS)['latest_snapshot']['directory'],'snapshots/prior')
        finally:
            if worker.poll() is None:worker.terminate();worker.wait(timeout=8)

if __name__=='__main__':unittest.main()
