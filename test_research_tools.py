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
    def test_value_filter_counts_saved_matches_without_turning_unknowns_into_zero(self):
        from copy import deepcopy
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parent/'viewer'))
        import model
        state,stamp,stale=model.load_state(self.root)
        template=deepcopy(state['wallets'][0]['assets'][0])
        for wallet,value in zip(state['wallets'],(10,9.999)):
            wallet['assets']=[{**deepcopy(template),'id':'1:native','chain_id':1,'address':None,'is_native':True,
                               'environment':'mainnet','balance':'1','value_usd':value}]
        tools=ResearchTools(self.root,{**self.config,'scope':'portfolio','wallet':None})
        args={'chain_id':1,'address':'native','minimum_value_usd':10}
        with patch('model.load_state',return_value=(state,stamp,stale)):
            result=tools.call('token_read',args,str(uuid.uuid4()))
            self.assertEqual(result['position_count'],1);self.assertEqual(result['unfiltered_position_count'],2)
            self.assertEqual(result['positions'][0]['asset']['value_usd'],10)
            state['wallets'][1]['assets'][0]['value_usd']=None
            result=tools.call('token_read',{**args,'minimum_value_usd':'0'},str(uuid.uuid4()))
            self.assertEqual(result['position_count'],1);self.assertEqual(result['unpriced_position_count'],1)
            state['wallets'][1]['assets'][0].update(environment='testnet',value_usd=100)
            result=tools.call('token_read',args,str(uuid.uuid4()))
            self.assertEqual(result['position_count'],1);self.assertEqual(result['outside_usd_scope_count'],1)
            batch=tools.call('records_read',{'reads':[{'name':'token_read','arguments':args}]*2},str(uuid.uuid4()))
            self.assertEqual(batch['position_count'],1);self.assertEqual(batch['completed_reads'],2)
            from kira_agent import read_completion,read_receipt
            failed=read_receipt('token_read',{**args,'minimum_value_usd':'10.0'},{'error':'Temporary read failure'})
            recovered=read_receipt('token_read',args,result)
            self.assertEqual(read_completion('Read '+json.dumps({'name':'token_read','arguments':failed['arguments']}),[failed,recovered],tools)['status'],'complete')
        for invalid in (True,-1,'NaN','Infinity',{},'1'*81):
            with self.assertRaises(JobError):tools.call('token_read',{**args,'minimum_value_usd':invalid},str(uuid.uuid4()))

    def test_read_plan_covers_more_than_eight_sources_and_rejects_actions_before_reading(self):
        reads=[{'name':'token_read','arguments':{'chain_id':chain,'address':'native'}} for chain in range(1,10)]
        result=self.call('records_read',{'reads':reads})
        self.assertEqual(result['completed_reads'],9);self.assertEqual(result['completion'],'complete')
        self.assertEqual(self.call('records_read',{'reads':[]})['reads'],[])
        for invalid in (reads*4,reads+[{'name':'holdings_refresh','arguments':{'wallet':self.first['address_key']}}]):
            with patch.object(self.tools,'allowed',side_effect=AssertionError('Invalid plans must not read data')):
                with self.assertRaises(JobError):self.call('records_read',{'reads':invalid})
        self.assertEqual(JobStore(self.root).list(),[])

    def test_natural_question_requires_a_complete_plan_before_answering(self):
        reads=[{'name':'token_read','arguments':{'chain_id':chain,'address':'native'}} for chain in range(1,10)]
        outputs=['Tools are unavailable.',json.dumps({'kira_tool':'records_read','arguments':{'reads':reads}}),'Nine sources were read.']
        store=AgentStore(self.root,runner=lambda *args:outputs.pop(0),detector=ready);store.config=self.config
        key=str(uuid.uuid4());store.turns[key]={'id':key,'state':'running','cancel':threading.Event(),'test':False,'conversation_id':store.conversation};store.active=key
        store._run(key,self.config,'Read nine requested chains.','아홉 체인의 저장된 ETH 기록을 각각 읽어줘.',store.epoch)
        turn=store.turns[key]
        self.assertEqual(turn['state'],'succeeded');self.assertEqual(turn['answer'],'Nine sources were read.')
        self.assertEqual(len(turn['tool_calls'][0]['reads']),9)
        self.assertEqual(turn['read_completion']['status'],'complete')
        self.assertEqual(turn['read_completion']['completed_reads'],9)

    def test_natural_plan_failure_cannot_become_successful_prose(self):
        reads=[{'name':'token_read','arguments':{'chain_id':chain,'address':'native'}} for chain in (8453,0)]
        prompts=[]
        def runner(config,prompt,cancel):
            prompts.append(prompt)
            return json.dumps({'kira_tool':'records_read','arguments':{'reads':reads}}) if len(prompts)==1 else 'Everything is complete.'
        store=AgentStore(self.root,runner=runner,detector=ready);store.config=self.config
        key=str(uuid.uuid4());store.turns[key]={'id':key,'state':'running','cancel':threading.Event(),'test':False,'conversation_id':store.conversation};store.active=key
        store._run(key,self.config,'Read the requested sources.','요청한 두 체인의 저장 기록을 읽어줘.',store.epoch)
        turn=store.turns[key]
        self.assertEqual(turn['state'],'partial');self.assertEqual(len(prompts),3)
        self.assertIn('unfinished requested reads',prompts[-1]);self.assertIn('token_read',turn['answer'])
        self.assertTrue(turn['read_completion']['failed'])

    def test_planning_cannot_enqueue_and_action_runs_once_after_empty_plan(self):
        refresh={'kira_tool':'prices_refresh','arguments':{'wallet':self.first['address_key']}}
        outputs=[json.dumps(refresh),json.dumps({'kira_tool':'records_read','arguments':{'reads':[]}}),json.dumps(refresh),'Price update queued.']
        store=AgentStore(self.root,runner=lambda *args:outputs.pop(0),detector=ready);store.config=self.config
        key=str(uuid.uuid4());store.turns[key]={'id':key,'state':'running','cancel':threading.Event(),'test':False,'conversation_id':store.conversation};store.active=key
        with patch.object(JobStore,'launch') as launch:
            store._run(key,self.config,'Refresh this wallet once.','가격만 한 번 새로고침해줘.',store.epoch)
        self.assertEqual(store.turns[key]['state'],'succeeded');self.assertEqual(len(JobStore(self.root).list()),1)
        self.assertEqual(launch.call_count,1)

    def test_read_plan_returns_precise_receipts_and_cannot_enqueue(self):
        reads=[{'name':'portfolio_read','arguments':{}},{'name':'wallet_read','arguments':{'wallet':self.first['address_key']}},{'name':'wallet_read','arguments':{'wallet':self.other}}]
        result=self.call('records_read',{'reads':reads})
        self.assertEqual(result['completion'],'partial');self.assertEqual(result['completed_reads'],2)
        self.assertEqual([r['status'] for r in result['reads']],['completed','completed','failed'])
        with self.assertRaises(JobError):self.call('records_read',{'reads':[{'name':'holdings_refresh','arguments':{'wallet':self.first['address_key']}}]})
        self.assertEqual(JobStore(self.root).list(),[])
    def test_literal_multiple_reads_are_partial_when_native_skips_one(self):
        from kira_agent import read_completion
        config={**self.config,'scope':'portfolio','wallet':None};tools=ResearchTools(self.root,config)
        receipts=[{'name':'portfolio_read','arguments':{},'status':'completed'}]
        result=read_completion('Run portfolio_read + wallet_read for all wallets.',receipts,tools)
        self.assertEqual(result['status'],'partial');self.assertIn('wallet_read Other wallet',result['missing'])
        receipts.append({'name':'records_read','arguments':{},'status':'completed','reads':[{'name':'wallet_read','arguments':{'wallet':key},'status':'completed'} for key in (self.first['address_key'],self.other)]})
        self.assertEqual(read_completion('Run portfolio_read + wallet_read for all wallets.',receipts,tools)['status'],'complete')
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

    def test_delivered_retry_recovers_only_the_same_requested_read(self):
        from kira_agent import read_completion,read_receipt
        args={'wallet':self.first['address_key'],'offset':0,'limit':1}
        failed=read_receipt('wallet_read',args,{'error':'context limit'})
        message='Run '+json.dumps({'name':'wallet_read','arguments':args})
        other=read_receipt('wallet_read',{**args,'offset':1},{'assets':[{}],'offset':1,'next_offset':2})
        self.assertEqual(read_completion(message,[failed,other],self.tools)['status'],'partial')
        retry=read_receipt('wallet_read',args,{'assets':[{}],'offset':0,'next_offset':1})
        result=read_completion(message,[failed,retry],self.tools)
        self.assertEqual(result['status'],'complete');self.assertEqual(result['failed'],[])
        self.assertEqual(failed['status'],'failed')
        retry['status']='failed'
        self.assertEqual(read_completion(message,[failed,retry],self.tools)['status'],'partial')
        defaults={'wallet':self.first['address_key']}
        failed=read_receipt('wallet_read',defaults,{'error':'temporary failure'})
        message='Run '+json.dumps({'name':'wallet_read','arguments':defaults})
        for changed in ({'offset':100},{'limit':1}):
            retry=read_receipt('wallet_read',{**defaults,**changed},{'assets':[{}],'offset':changed.get('offset',0),'next_offset':None})
            self.assertEqual(read_completion(message,[failed,retry],self.tools)['status'],'partial')
        retry=read_receipt('wallet_read',{**defaults,'offset':0,'limit':100},{'snapshot_id':'snapshots/current','assets':[{}],'offset':0,'next_offset':None})
        result=read_completion('Run wallet_read for the full inventory.',[failed,retry],self.tools)
        self.assertEqual(result['status'],'complete');self.assertEqual(result['unread_pages'],[])
        for malformed in (None,[],7):
            for name,valid in (('wallet_read',defaults),('token_read',{'chain_id':1,'address':'0x'+'a'*40})):
                bad=read_receipt(name,malformed,{'error':'invalid arguments'})
                good=read_receipt(name,valid,{'assets':[],'offset':0,'next_offset':None})
                result=read_completion('Run '+name+'.',[bad,good],self.tools)
                self.assertEqual(result['status'],'partial');self.assertEqual(result['failed'][0]['arguments'],malformed)
        for name,valid in (('wallet_read',defaults),('token_read',{'chain_id':1,'address':'0x'+'a'*40}),('snapshot_read',{'snapshot_id':'snapshots/current'})):
            for malformed in ({},{'chain_id':1}):
                bad=read_receipt(name,malformed,{'error':'missing required arguments'})
                good=read_receipt(name,valid,{'assets':[],'offset':0,'next_offset':None})
                result=read_completion('Run '+name+'.',[bad,good],self.tools)
                self.assertEqual(result['status'],'partial');self.assertTrue(result['failed'])

    def test_completion_matches_token_arguments_and_contiguous_inventory_pages(self):
        from kira_agent import read_completion,read_receipt
        token='0x'+'a'*40
        message='Run token_read '+json.dumps({'reads':[{'name':'token_read','arguments':{'chain_id':cid,'address':token}} for cid in (1,8453)]})
        receipt=read_receipt('token_read',{'chain_id':1,'address':token},{'positions':[],'offset':0,'next_offset':None})
        completion=read_completion(message,[receipt],self.tools)
        self.assertEqual(completion['status'],'partial');self.assertIn('8453',completion['missing'][0])
        receipts=[read_receipt('wallet_read',{'wallet':self.first['address_key'],'offset':offset},{'assets':[{}]*20,'asset_count':60,'offset':offset,'next_offset':offset+20 if offset<40 else None}) for offset in (0,40)]
        completion=read_completion('Run wallet_read for the full inventory.',receipts,self.tools)
        self.assertEqual(completion['status'],'partial');self.assertEqual(completion['unread_pages'][0]['arguments']['offset'],20)
        receipts.append(read_receipt('wallet_read',{'wallet':self.first['address_key'],'offset':20},{'assets':[{}]*20,'offset':20,'next_offset':40}))
        self.assertEqual(read_completion('Run wallet_read for the full inventory.',receipts,self.tools)['status'],'complete')
        receipts[-1]=read_receipt('wallet_read',{'wallet':self.first['address_key'],'offset':20},{'assets':[{}]*20,'offset':20,'next_offset':40},False)
        self.assertEqual(read_completion('Run wallet_read for the full inventory.',receipts,self.tools)['unread_pages'][0]['arguments']['offset'],20)
        args={'snapshot_id':'snapshots/sample','limit':100}
        receipt=read_receipt('snapshot_read',{'snapshot_id':args['snapshot_id']},{'offset':0,'next_offset':20})
        message='Run snapshot_read '+json.dumps({'name':'snapshot_read','arguments':args})
        self.assertEqual(read_completion(message,[receipt],self.tools)['status'],'partial')
        receipt=read_receipt('snapshot_read',{'snapshot_id':args['snapshot_id'],'limit':100},{'wallets':[{'assets':[{}],'asset_count':1,'offset':0,'next_offset':None}]})
        self.assertEqual(read_completion('Run snapshot_read for the full inventory.',[receipt],self.tools)['status'],'complete')
        portfolio=read_receipt('portfolio_read',{}, {'wallets':[{'address':self.first['address_key'],'snapshot_id':'snapshots/old','assets':[{}]*12,'asset_count':50,'offset':0,'next_offset':12}]})
        completion=read_completion('Run portfolio_read for the full inventory.',[portfolio],self.tools)
        self.assertEqual(completion['status'],'partial');self.assertEqual(completion['unread_pages'][0]['arguments']['offset'],12)
        pages=[read_receipt('wallet_read',{'wallet':self.first['address_key'],'offset':offset},{'assets':[{}]*20,'offset':offset,'next_offset':20 if offset==0 else None,'snapshot_id':snapshot}) for offset,snapshot in ((0,'snapshots/old'),(20,'snapshots/new'))]
        completion=read_completion('Run wallet_read for the full inventory.',pages,self.tools)
        self.assertEqual(completion['status'],'partial');self.assertEqual({p['snapshot_id'] for p in completion['unread_pages']},{'snapshots/old','snapshots/new'})
        self.assertEqual(read_completion(json.dumps({'name':'wallet_read','arguments':{'wallet':self.first['address_key']}}),[],self.tools)['status'],'partial')
        complete=read_receipt('wallet_read',{'wallet':self.first['address_key']},{'assets':[],'offset':0,'next_offset':None})
        token_receipt=read_receipt('token_read',{'chain_id':8453,'address':token},{'positions':[]})
        self.assertEqual(read_completion('Run wallet_read for the full inventory + token_read.',[complete,token_receipt],self.tools)['status'],'complete')
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);atomic(self.root/'wallets.json',{'schema_version':1,'wallets':[],'research_runs':[]});sample(self.root)
        registry=json.loads((self.root/'wallets.json').read_text());registry.pop('demo',None)
        self.first=registry['wallets'][0];self.other='0x'+'2'*40
        registry['wallets'].append({'address':self.other,'address_key':self.other,'tags':['Other wallet']});atomic(self.root/'wallets.json',registry)
        self.config=settings(scope='wallet',wallet=self.first['address_key'],wallet_tools=True)
        self.tools=ResearchTools(self.root,self.config)
        from kira_config import default_config,provider_config
        cfg=provider_config(default_config(),'alchemy','KIRA_FIXTURE_KEY');cfg['secret_env_file']=str(self.root/'fixture.env')
        atomic(self.root/'.kira.local.json',cfg);(self.root/'fixture.env').write_text('KIRA_FIXTURE_KEY=fixture-only-key\n')
    def tearDown(self):self.temp.cleanup()
    def call(self,name,arguments=None):return self.tools.call(name,arguments or {},str(uuid.uuid4()))
    def test_none_legacy_and_foreign_scopes_cannot_read_or_mutate(self):
        for config in (settings(wallet_tools=True),settings(scope='portfolio')):
            with self.assertRaises(JobError):ResearchTools(self.root,config).call('portfolio_read',{},str(uuid.uuid4()))
        for name in ('wallet_read','snapshots_list','holdings_refresh'):
            with self.assertRaises(JobError):self.call(name,{'wallet':self.other})
    def test_comparison_chain_counts_cover_full_inventory_on_every_page(self):
        before=self.first['latest_snapshot']['directory'];file=self.root/self.first['latest_snapshot']['result']
        template=json.loads(file.read_text())
        template['coverage'].append({**template['coverage'][0],'chain_id':1,'network':'ethereum','name':'Ethereum'})
        def tokens(cid,count):
            return [{'chain_id':cid,'token_address':'0x'+format(i+1,'040x'),'token_type':'ERC20',
                'symbol':'SYNTHETIC','wallet_balance':'1','wallet_balance_raw':'1','decimals':0,
                'dex_pools':[],'mintclub':None,'indexer_price_references':[]} for i in range(count)]
        atomic(file,{**template,'tokens':tokens(1,11)+tokens(8453,2)})
        after='snapshots/comparison-after';atomic(self.root/after/'results.json',{**template,'tokens':tokens(1,25)+tokens(8453,122)})
        registry=json.loads((self.root/'wallets.json').read_text())
        registry.setdefault('research_runs',[]).append({'address_key':self.first['address_key'],'snapshot':after});atomic(self.root/'wallets.json',registry)
        pages=[self.call('snapshots_compare',{'before':before,'after':after,'offset':offset,'limit':100}) for offset in (0,100)]
        summary=pages[0]['comparison_summary']
        self.assertEqual(pages[1]['comparison_summary'],summary)
        self.assertEqual([len(p['positions']) for p in pages],[100,47])
        self.assertEqual(summary['totals']['position_count'],147)
        self.assertEqual(summary['totals']['missing_before_balance_count'],134)
        self.assertEqual(summary['totals']['unchanged_observation_count'],13)
        self.assertEqual([(r['chain_id'],r['missing_before_balance_count']) for r in summary['chains']],[(1,14),(8453,120)])
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
            return json.dumps({'kira_tool':'records_read','arguments':{'reads':[{'name':'snapshots_list','arguments':{'wallet':self.first['address_key']}}]}}) if len(calls)==1 else 'I found the saved analysis.'
        store=AgentStore(self.root,runner=runner,detector=ready);store.config=self.config
        key=str(uuid.uuid4());store.turns[key]={'id':key,'state':'running','cancel':threading.Event(),'test':False,'conversation_id':store.conversation};store.active=key
        store._run(key,self.config,'Inspect the saved wallet analysis.','Inspect the saved wallet analysis.',store.epoch)
        self.assertEqual(store.turns[key]['state'],'succeeded');self.assertIn('snapshot_id',calls[1]);self.assertEqual(store.turns[key]['answer'],'I found the saved analysis.')

    def test_mixed_tool_protocol_is_repaired_before_any_tool_executes(self):
        outputs=['I will check. {"kira_tool":"portfolio_read","arguments":{}}',
                 '{"kira_tool":"records_read","arguments":{"reads":[]}}','Recorded evidence only.']
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
        outputs=['{"kira_tool":"records_read","arguments":{"reads":[]}}']+['{"kira_tool":"portfolio_read","arguments":{}}']*7+['Prose {"kira_tool":"portfolio_read","arguments":{}}']
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
            return json.dumps({'kira_tool':'records_read','arguments':{'reads':[]}}) if len(prompts)==1 else json.dumps({'kira_tool':'portfolio_read','arguments':{}})
        store=AgentStore(self.root,runner=runner,detector=ready);store.config=self.config
        key=str(uuid.uuid4());store.turns[key]={'id':key,'state':'running','cancel':threading.Event(),'test':False,'conversation_id':store.conversation};store.active=key
        with patch.object(ResearchTools,'call',return_value={'data':'界'*100000}):
            store._run(key,self.config,'Inspect records.','Inspect records.',store.epoch)
        self.assertEqual(store.turns[key]['error']['code'],'tool_limit');self.assertEqual(len(prompts),9)
        self.assertTrue(all(len(p.encode())<=400000 for p in prompts));self.assertIn('context limit',prompts[1])
        self.assertTrue(all(row['status']=='failed' for row in store.turns[key]['tool_calls']))
