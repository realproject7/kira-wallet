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
from kira_research_tools import ResearchTools, compare_curve_states
from kira_agent import AgentStore
from test_kira_agent import settings, ready

class ResearchToolsTest(unittest.TestCase):
    def test_different_blocks_and_wallet_quotes_do_not_prove_curve_movement(self):
        from copy import deepcopy
        state={'reserve_token':'0x'+'a'*40,'reserve_balance':'100','current_supply':'10',
            'price_for_next_mint_in_reserve_token':'2','burn_royalty_bps':100,'block_number':'100'}
        positions=[{'wallet':'first','asset':{'curve_state':state,'exit_quote':{'output_amount':'1'}}},
            {'wallet':'second','asset':{'curve_state':{**state,'block_number':'101'},'exit_quote':{'output_amount':'50'}}}]
        self.assertEqual(compare_curve_states(positions)['comparisons'][0]['status'],'same_recorded_state')
        different=deepcopy(positions);different[1]['asset']['curve_state']['current_supply']='11'
        self.assertEqual(compare_curve_states(different)['comparisons'][0]['changed_fields'],['current_supply'])
        del different[1]['asset']['curve_state']['reserve_balance']
        self.assertEqual(compare_curve_states(different)['comparisons'][0]['status'],'unknown')
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

    def test_historical_read_preserves_native_observations_and_safe_price_references(self):
        snapshot=self.first['latest_snapshot']['directory'];file=self.root/self.first['latest_snapshot']['result']
        result=json.loads(file.read_text());chain=result['coverage'][0]
        chain.update(native_symbol='ETH',native_balance='0',rpc_status='available',
            native_observed_at='2026-10-05T01:00:00Z',native_block_number='101',
            provider_debug='SECRET-MARKER',mintclub_registry_scan={'block_number':'102','debug':'SECRET-MARKER'})
        result['price_references']={'ETH_USD':{'value':'2000','observed_at':'2026-10-05T00:59:00Z','source':'SECRET-MARKER'},
            'cbBTC_USD':{'value':'90000','observed_at':'2026-10-05T00:58:00Z','source':'SECRET-MARKER'}}
        atomic(file,result)
        projected=self.call('snapshot_read',{'snapshot_id':snapshot})
        wallet=projected['wallets'][0];native=wallet['chains'][0]
        self.assertEqual(native['native_balance'],'0');self.assertEqual(native['native_block_number'],'101')
        self.assertEqual(native['registry_block_number'],'102')
        self.assertEqual(native['native_observed_at'],'2026-10-05T01:00:00Z')
        self.assertEqual(wallet['snapshot_price_references']['ETH_USD']['value'],'2000')
        self.assertEqual(wallet['snapshot_price_references']['cbBTC_USD'],{'value':'90000','observed_at':'2026-10-05T00:58:00Z'})
        self.assertNotIn('SECRET-MARKER',json.dumps(projected));self.assertNotIn(self.other,json.dumps(projected))
        self.assertFalse(any(a['id']==str(chain['chain_id'])+':native' for a in wallet['assets']))
    def test_bounded_wallet_markets_can_be_retrieved_without_losing_recorded_counts(self):
        from copy import deepcopy
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parent/'viewer'))
        from model import load_state
        state,stamp,stale=load_state(self.root);wallet=state['wallets'][0];template=wallet['assets'][0]
        wallet['assets']=[]
        for index in range(100):
            asset=deepcopy(template);asset['id']=f'8453:0x{index:040x}'
            asset['market_pools']=[{'venue':'Uniswap','pool':'0x'+'3'*40,'url':'https://example.com/pool/'+str(pool),'liquidity_usd':100,'pair':[]} for pool in range(12)]
            wallet['assets'].append(asset)
        with patch('model.load_state',return_value=(state,stamp,stale)):
            summary=self.call('wallet_read',{'wallet':self.first['address_key'],'limit':20})
            self.assertEqual(summary['asset_count'],100);self.assertEqual(summary['next_offset'],20)
            pages=[self.call('wallet_read',{'wallet':self.first['address_key'],'offset':offset,'limit':20}) for offset in range(0,100,20)]
            self.assertEqual([a['id'] for page in pages for a in page['assets']],[a['id'] for a in wallet['assets']])
            self.assertIsNone(pages[-1]['next_offset'])
            for invalid in ({'offset':True},{'limit':101},{'limit':0},{'offset':-1}):
                with self.assertRaises(JobError):self.call('wallet_read',{'wallet':self.first['address_key'],**invalid})
            last=summary['assets'][-1]
            self.assertEqual(last['pools'],[]);self.assertEqual(last['pools_recorded'],12);self.assertEqual(last['pools_omitted'],12)
            self.assertIn('token_read',summary['note'])
            detail=self.call('token_read',{'chain_id':8453,'address':'0x'+format(99,'040x')})
            self.assertEqual(len(detail['positions'][0]['asset']['pools']),12)
            self.assertEqual(detail['positions'][0]['asset']['pools_omitted'],0)
    def test_duplicate_refresh_reuses_job_and_foreign_jobs_are_hidden(self):
        with patch.object(JobStore,'launch'):
            first=self.call('holdings_refresh',{'wallet':self.first['address_key']})
            second=self.call('holdings_refresh',{'wallet':self.first['address_key']})
            self.assertEqual(first['job_id'],second['job_id']);self.assertEqual(first['state'],'queued')
            self.assertEqual(first['wallet'],self.first['address_key'])
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

    def test_mixed_tool_protocol_is_repaired_before_any_tool_executes(self):
        outputs=['I will check. {"kira_tool":"portfolio_read","arguments":{}}',
                 '{"kira_tool":"portfolio_read","arguments":{}}','Recorded evidence only.']
        calls=[]
        def runner(config,prompt,cancel):calls.append(prompt);return outputs.pop(0)
        store=AgentStore(self.root,runner=runner,detector=ready);store.config=self.config
        key=str(uuid.uuid4());store.turns[key]={'id':key,'state':'running','cancel':threading.Event(),'test':False,'conversation_id':store.conversation};store.active=key
        with patch.object(ResearchTools,'call',return_value={'recorded':True}) as tool:
            store._run(key,self.config,'Inspect records.','Inspect records.',store.epoch)
        self.assertEqual(tool.call_count,1);self.assertIn('not executed',calls[1])
        self.assertEqual(store.turns[key]['answer'],'Recorded evidence only.')

    def test_repeated_mixed_tool_protocol_fails_without_leaking_or_executing_it(self):
        store=AgentStore(self.root,runner=lambda *args:'Prose {"kira_tool":"holdings_refresh","arguments":{}}',detector=ready);store.config=self.config
        key=str(uuid.uuid4());store.turns[key]={'id':key,'state':'running','cancel':threading.Event(),'test':False,'conversation_id':store.conversation};store.active=key
        with patch.object(ResearchTools,'call') as tool:
            store._run(key,self.config,'Refresh records.','Refresh records.',store.epoch)
        tool.assert_not_called();self.assertEqual(store.turns[key]['error']['code'],'invalid_tool_response')
        self.assertNotIn('answer',store.turns[key]);self.assertEqual(store.messages,[])

    def test_malformed_protocol_after_eight_tools_cannot_fall_through_as_answer(self):
        outputs=['{"kira_tool":"portfolio_read","arguments":{}}']*8+['Prose {"kira_tool":"portfolio_read","arguments":{}}']
        store=AgentStore(self.root,runner=lambda *args:outputs.pop(0),detector=ready);store.config=self.config
        key=str(uuid.uuid4());store.turns[key]={'id':key,'state':'running','cancel':threading.Event(),'test':False,'conversation_id':store.conversation};store.active=key
        with patch.object(ResearchTools,'call',return_value={}):
            store._run(key,self.config,'Inspect records.','Inspect records.',store.epoch)
        self.assertEqual(store.turns[key]['state'],'failed');self.assertEqual(store.messages,[])
        self.assertEqual(store.turns[key]['error']['code'],'invalid_tool_response')

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
        self.assertTrue(all(row['status']=='failed' for row in store.turns[key]['tool_calls']))
