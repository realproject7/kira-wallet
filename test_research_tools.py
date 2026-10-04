"""Agent tool scopes, historical projection and truthful durable research receipts."""
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch
from kira_cli import sample
from kira_jobs import JobStore, JobError, atomic
from kira_research_tools import ResearchTools
from kira_agent import AgentStore
from test_kira_agent import settings, ready

class ResearchToolsTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);atomic(self.root/'wallets.json',{'schema_version':1,'wallets':[],'research_runs':[]});sample(self.root)
        registry=json.loads((self.root/'wallets.json').read_text());registry.pop('demo',None)
        self.first=registry['wallets'][0];self.other='0x'+'2'*40
        registry['wallets'].append({'address':self.other,'address_key':self.other,'tags':['Other wallet']});atomic(self.root/'wallets.json',registry)
        self.config=settings(scope='wallet',wallet=self.first['address_key'],wallet_tools=True)
        self.tools=ResearchTools(self.root,self.config)
    def tearDown(self):self.temp.cleanup()
    def call(self,name,arguments=None):return self.tools.call(name,arguments or {},str(uuid.uuid4()))
    def test_none_legacy_and_foreign_scopes_cannot_read_or_mutate(self):
        for config in (settings(wallet_tools=True),settings(scope='portfolio')):
            with self.assertRaises(JobError):ResearchTools(self.root,config).call('portfolio_read',{},str(uuid.uuid4()))
        for name in ('wallet_read','snapshots_list','holdings_refresh'):
            with self.assertRaises(JobError):self.call(name,{'wallet':self.other})
        with self.assertRaises(JobError):self.call('snapshot_read',{'snapshot_id':'snapshots/foreign'})
        with self.assertRaises(JobError):self.call('shell',{'command':'read secrets'})
        with self.assertRaises(JobError):self.call('token_read',{'chain_id':True,'address':'native'})
    def test_historical_read_projects_validated_facts_only(self):
        snapshot=self.first['latest_snapshot']['directory'];file=self.root/self.first['latest_snapshot']['result']
        result=json.loads(file.read_text());result['tokens'][0]['provider_debug']='SECRET-MARKER';result['tokens'][0]['wallet_full_burn']={'value_usd':999999,'source':'fabricated'};atomic(file,result)
        projected=self.call('snapshot_read',{'snapshot_id':snapshot})
        self.assertEqual(projected['snapshot_id'],snapshot)
        self.assertNotIn('SECRET-MARKER',json.dumps(projected));self.assertNotIn('fabricated',json.dumps(projected));self.assertNotIn('report_url',json.dumps(projected))
    def test_duplicate_refresh_reuses_job_and_foreign_jobs_are_hidden(self):
        with patch.object(JobStore,'launch'):
            first=self.call('holdings_refresh',{'wallet':self.first['address_key']})
            second=self.call('holdings_refresh',{'wallet':self.first['address_key']})
            self.assertEqual(first['job_id'],second['job_id']);self.assertEqual(first['state'],'queued')
            foreign=JobStore(self.root).submit({'schema_version':1,'operation':'wallet.refresh','input':{'wallet':self.other},'idempotency_key':str(uuid.uuid4())})
        with self.assertRaises(JobError):self.call('job_read',{'job_id':foreign['job_id']})
        self.assertNotIn(foreign['job_id'],json.dumps(self.call('job_list')))
    def test_cancelled_guard_prevents_admission(self):
        @contextmanager
        def guard():raise JobError('cancelled','Permissions changed');yield
        tools=ResearchTools(self.root,self.config,guard)
        with self.assertRaises(JobError):tools.call('holdings_refresh',{'wallet':self.first['address_key']},str(uuid.uuid4()))
        self.assertFalse(JobStore(self.root).list())
    def test_native_tool_loop_reads_then_answers_without_execution_tools(self):
        calls=[]
        def runner(config,prompt,cancel):
            calls.append(prompt)
            return json.dumps({'kira_tool':'snapshots_list','arguments':{'wallet':self.first['address_key']}}) if len(calls)==1 else 'I found the saved analysis.'
        store=AgentStore(self.root,runner=runner,detector=ready);store.config=self.config
        key=str(uuid.uuid4());store.turns[key]={'id':key,'state':'running','cancel':threading.Event(),'test':False,'conversation_id':store.conversation};store.active=key
        store._run(key,self.config,'Inspect the saved wallet analysis.','Inspect the saved wallet analysis.',store.epoch)
        self.assertEqual(store.turns[key]['state'],'succeeded');self.assertIn('snapshot_id',calls[1]);self.assertEqual(store.turns[key]['answer'],'I found the saved analysis.')

    def test_permissions_changed_during_model_turn_prevent_job_admission(self):
        store=None
        def runner(config,prompt,cancel):
            store.config={**config,'scope':'none'}
            return json.dumps({'kira_tool':'holdings_refresh','arguments':{'wallet':self.first['address_key']}})
        store=AgentStore(self.root,runner=runner,detector=ready);store.config=self.config
        key=str(uuid.uuid4());store.turns[key]={'id':key,'state':'running','cancel':threading.Event(),'test':False,'conversation_id':store.conversation};store.active=key
        store._run(key,self.config,'Refresh my holdings.','Refresh my holdings.',store.epoch)
        self.assertEqual(store.turns[key]['state'],'cancelled');self.assertFalse(JobStore(self.root).list())
    def test_accumulated_tool_context_and_step_limit_are_bounded(self):
        prompts=[]
        def runner(config,prompt,cancel):
            prompts.append(prompt)
            return json.dumps({'kira_tool':'portfolio_read','arguments':{}})
        store=AgentStore(self.root,runner=runner,detector=ready);store.config=self.config
        key=str(uuid.uuid4());store.turns[key]={'id':key,'state':'running','cancel':threading.Event(),'test':False,'conversation_id':store.conversation};store.active=key
        with patch.object(ResearchTools,'call',return_value={'data':'界'*80000}):
            store._run(key,self.config,'Inspect records.','Inspect records.',store.epoch)
        self.assertEqual(store.turns[key]['error']['code'],'tool_limit');self.assertEqual(len(prompts),9)
        self.assertTrue(all(len(p.encode())<=400000 for p in prompts));self.assertIn('context limit',prompts[1])
