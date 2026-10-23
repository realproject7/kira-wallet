"""Shared API preservation, bounded views, cross-process invalidation and lifecycle."""
import contextlib
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch
from kira_cli import initialize, sample
from kira_jobs import atomic, JobError
from kira_service import Application
from kira_state import StateCache

class ApplicationTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'KIRA_DATA_DIR':str(self.root),'KIRA_CONFIG':str(self.root/'.kira.local.json')});self.env.start()
        initialize(self.root);sample(self.root);self.app=Application(self.root)
        self.no_network=patch.object(socket.socket,'connect',side_effect=AssertionError('Offline test contacted a provider'));self.no_network.start()
    def tearDown(self):self.no_network.stop();self.env.stop();self.temp.cleanup()
    def test_idle_summary_and_etag_reuse_without_reprojection(self):
        body,revision=self.app.views.summary()
        self.assertTrue(json.loads(body)['paged'])
        with patch('kira_state.load_state',side_effect=AssertionError('Idle data was recomputed')):
            for _ in range(20):
                self.assertEqual(self.app.views.summary(),(body,revision));self.assertEqual(self.app.status()['data_revision'],revision)
        self.assertEqual(self.app.views.builds,1)
    def test_external_atomic_changes_invalidate_same_snapshot_and_tags(self):
        before=self.app.views.summary()[1]
        folder=self.root/'snapshots/demo/initial';market=json.loads((folder/'market-prices.json').read_text())
        market['tokens'][0]['usd']=2;atomic(folder/'market-prices.json',market)
        self.assertNotEqual(self.app.views.summary()[1],before)
        self.assertEqual(self.app.views.wallet('Demo wallet')['known_value_usd'],200)
        registry=json.loads((self.root/'wallets.json').read_text());registry['wallets'][0]['tags']=['Renamed'];atomic(self.root/'wallets.json',registry)
        self.assertEqual(self.app.views.wallet('Renamed')['name'],'Renamed')
    def test_private_checkpoint_does_not_invalidate_published_projection(self):
        _,revision=self.app.views.summary()
        atomic(self.root/'snapshots/demo/initial/private-checkpoint.json',{'phase':'unpublished'})
        self.assertEqual(self.app.views.summary()[1],revision)
        self.assertEqual(self.app.views.builds,1)
    def test_partial_write_keeps_last_good_summary_and_retries(self):
        body,revision=self.app.views.summary();file=self.root/'snapshots/demo/initial/results.json';old=file.read_bytes()
        file.write_text('{')
        self.assertEqual(self.app.views.summary(),(body,revision))
        file.write_bytes(old)
        self.assertEqual(self.app.views.wallet('Demo wallet')['known_value_usd'],125)
    def test_filters_apply_before_paging_and_first_response_is_bounded(self):
        file=self.root/'snapshots/demo/initial/results.json';snapshot=json.loads(file.read_text());template=snapshot['tokens'][0]
        snapshot['tokens']=[{**template,'token_address':f'0x{i+1:040x}','symbol':f'TOKEN{i:04}','wallet_balance':str(i+1)} for i in range(5000)]
        atomic(file,snapshot)
        body,_=self.app.views.summary();self.assertLess(len(body),500000)
        self.assertEqual(json.loads(body)['wallets'][0]['asset_count'],5000)
        result=self.app.views.wallet('Demo wallet',query='TOKEN49',limit=20,sort='name')
        self.assertEqual(result['matched_count'],100);self.assertEqual(len(result['assets']),20);self.assertEqual(result['next_offset'],20)
        self.assertEqual(result['assets'][0]['symbol'],'TOKEN4900')
        page=self.app.views.holdings(query='TOKEN49',offset=80,limit=20,sort='name')
        self.assertIsNone(page['next_offset']);self.assertEqual(page['assets'][-1]['symbol'],'TOKEN4999')
        self.assertEqual(self.app.call('holdings_query',{'mode':'search','query':'TOKEN4999'})['matched_position_count'],1)
    def test_mutation_parity_preserves_history_and_can_be_waited_for(self):
        before=(self.root/'snapshots/demo/initial/results.json').read_bytes()
        with patch.object(self.app.jobs,'launch'):
            job=self.app.call('wallet_tags',{'wallet':'Demo wallet','tags':['New','Old'],'idempotency_key':'new-tags-once'},allow_write=True)
        self.assertFalse(self.app.wait(job['job_id'],0)['completed'])
        self.app.jobs.worker();self.assertTrue(self.app.wait(job['job_id'],0)['completed'])
        self.assertEqual((self.root/'snapshots/demo/initial/results.json').read_bytes(),before)
        self.assertEqual(self.app.call('wallet_read',{'wallet':'New'})['tags'],['New','Old'])
        self.assertTrue(json.loads((self.root/'wallets.json').read_text())['tag_history'])
        with self.assertRaises(JobError):self.app.wait(job['job_id'],121)
    def test_jobs_status_does_not_rebuild_data_or_reread_unchanged_history(self):
        self.app.views.summary()
        with patch.object(self.app.jobs,'launch'):
            job=self.app.call('wallet_tags',{'wallet':'Demo wallet','tags':['New'],'idempotency_key':'jobs-only-tags'},allow_write=True)
        first=self.app.status();self.assertEqual(first['active_job_count'],1)
        with patch.object(self.app.jobs,'get',side_effect=AssertionError('Idle history reread')):
            self.assertEqual(self.app.status(),first)
        self.assertEqual(self.app.views.builds,1)
        self.app.jobs.worker();self.assertEqual(self.app.status()['active_job_count'],0)
        self.assertNotEqual(first['jobs_revision'],self.app.status()['jobs_revision'])
    def test_cli_machine_output_and_shared_data_survive_new_cwd(self):
        import subprocess
        executable=Path(__file__).resolve().parent/'kira_cli.py'
        command=[sys.executable,str(executable),'--data-dir',str(self.root),'call','holdings_query','--arguments','{"mode":"aggregate"}','--json']
        with tempfile.TemporaryDirectory() as cwd:
            result=subprocess.run(command,capture_output=True,text=True,cwd=cwd,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['scanned_position_count'],1)
        command[-3:-1]=['--arguments','{"mode":"invalid"}']
        result=subprocess.run(command,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,1);self.assertIn('error',json.loads(result.stdout))
    def test_upgrade_initialization_preserves_every_existing_record(self):
        atomic(self.root/'.kira-agent.json',{'legacy':'preserved'});atomic(self.root/'.kira-agent-resume.json',{'legacy':'preserved'})
        before={p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        initialize(self.root)
        for name,body in before.items():self.assertEqual((self.root/name).read_bytes(),body)
    def test_selection_is_available_without_browser_or_agent_runtime(self):
        self.app.select({'view':'token','token':'8453:0x'+'0'*39+'2','chain_id':8453,'wallet':None})
        self.assertEqual(Application(self.root).call('ui_context')['token'],'8453:0x'+'0'*39+'2')
        with self.assertRaises(JobError):self.app.select({'view':'wallet','wallet':'not-registered'})
        with self.assertRaises(JobError):self.app.select({'shell':'command'})
