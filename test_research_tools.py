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
from test_records import settings

class ResearchToolsTest(unittest.TestCase):
    def test_cached_full_balance_sale_reaches_details_and_compact_quote_indicator(self):
        from copy import deepcopy
        from test_sell_quotes import fixture, STAMP
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parent/'viewer'))
        from model import load_state
        snapshot,market,record=fixture()
        snapshot.update(schema_version=1,wallet_address=self.first['address'],tags=['Demo wallet'],
                        compiled_at=STAMP,status='completed_with_coverage_gaps',counts={})
        snapshot['coverage'][0].update(name='Base',native_symbol='ETH',native_balance='0',
                                      general_erc20_discovery='indexer_checked',rpc_status='available')
        token=snapshot['tokens'][0]
        token.update(network='base',symbol='HUNT',name='Synthetic HUNT',decimals=0,mintclub=None)
        market.update(observed_at=STAMP,sell_quotes={'version':1,'wallet_address':self.first['address_key'],'records':[record]})
        folder=self.root/self.first['latest_snapshot']['directory']
        atomic(folder/'results.json',snapshot);atomic(folder/'market-prices.json',market)
        expected=load_state(self.root)[0]['wallets'][0]['assets'][0]['sell_out']
        self.assertEqual(expected['value_usd'],4000)
        self.assertEqual(expected['valuation'],'terminal_reference')
        detail=self.call('token_read',{'chain_id':8453,'address':token['token_address']})['positions'][0]['asset']
        self.assertEqual(detail['sell_out'],expected)
        self.assertTrue(detail['exit_quote_recorded'])
        self.assertIsNone(detail['exit_quote'])  # No Mint Club burn record.
        search=self.call('holdings_query',{'mode':'search','query':'HUNT'})['results'][0]['positions'][0]['asset']
        self.assertEqual(search['sell_out'],expected)
        compact=self.call('wallet_read',{'wallet':self.first['address_key']})['assets'][0]
        self.assertTrue(compact['exit_quote_recorded'])
        self.assertNotIn('sell_out',compact)
        self.assertNotIn('exit_quote',compact)
        for change in ('wrong_wallet','partial_input','testnet'):
            altered=deepcopy(market);saved=deepcopy(snapshot)
            if change=='wrong_wallet':altered['sell_quotes']['wallet_address']=self.other
            elif change=='partial_input':altered['sell_quotes']['records'][0]['quote']['partial_input']=True
            else:saved['coverage'][0]['environment']='testnet'
            atomic(folder/'results.json',saved);atomic(folder/'market-prices.json',altered)
            detail=self.call('token_read',{'chain_id':8453,'address':token['token_address']})['positions'][0]['asset']
            self.assertIsNone(detail['sell_out'],change)
            self.assertFalse(detail['exit_quote_recorded'],change)
        self.assertEqual(JobStore(self.root).list(),[])

    def test_burn_sell_out_keeps_reserve_valuation_and_independent_clocks(self):
        from test_sell_quotes import fixture, STAMP
        snapshot,market,_=fixture()
        snapshot.update(schema_version=1,wallet_address=self.first['address'],tags=['Demo wallet'],
                        compiled_at=STAMP,status='completed_with_coverage_gaps',counts={})
        snapshot['coverage'][0].update(name='Base',native_symbol='ETH',native_balance='0',
                                      general_erc20_discovery='indexer_checked',rpc_status='available')
        reserve='0x'+'9'*40;quoted='2026-10-01T00:00:00Z';token=snapshot['tokens'][0]
        token.update(network='base',symbol='CURVE',name='Synthetic curve',decimals=0,
                     mintclub={'reserve_token':reserve,'reserve_symbol':'RESERVE','reserve_balance':'100',
                               'funded':True,'price_for_next_mint_in_reserve_token':'1',
                               'source_url':'https://example.com/curve','observed_at':quoted,'block_number':'7',
                               'wallet_full_burn':{'net_refund':'12','gas_included':False}})
        market['tokens'].append({**market['tokens'][0],'address':reserve,'usd':'2'})
        folder=self.root/self.first['latest_snapshot']['directory']
        atomic(folder/'results.json',snapshot);atomic(folder/'market-prices.json',market)
        asset=self.call('token_read',{'chain_id':8453,'address':token['token_address']})['positions'][0]['asset']
        estimate=asset['sell_out']
        self.assertEqual(estimate['valuation'],'reserve_reference')
        self.assertEqual(estimate['value_usd'],24)
        self.assertEqual(estimate['observed_at'],quoted)
        self.assertEqual(estimate['output_price']['observed_at'],STAMP)
        self.assertFalse(estimate['execution_verified']);self.assertFalse(estimate['gas_included'])
        self.assertEqual(asset['exit_quote']['output_amount'],'12')

    def test_large_inventory_queries_search_rank_aggregate_without_dumping_pages(self):
        from copy import deepcopy
        import model
        state,stamp,stale=model.load_state(self.root)
        wallet=state['wallets'][0];base=deepcopy(wallet['assets'][0])
        wallet['assets']=[{**deepcopy(base),'id':f'8453:0x{i:040x}','address':f'0x{i:040x}',
            'symbol':'PLOT' if i in (1500,1600) else 'FIX','name':'Fixture '+str(i),'chain_id':8453,
            'value_usd':i,'environment':'mainnet','archived':False} for i in range(1722)]
        wallet['assets'][-1]['value_usd']=None
        wallet['assets'][-2].update(environment='testnet',value_usd=999999)
        wallet['assets'][-3].update(archived=True,value_usd=999999)
        with patch('model.load_state',return_value=(state,stamp,stale)):
            result=self.call('holdings_query',{'mode':'rank','limit':5})
            self.assertEqual([r['value_usd'] for r in result['results']],['1718','1717','1716','1715','1714'])
            self.assertEqual(result['scanned_position_count'],1722)
            self.assertEqual(result['unpriced_position_count'],1);self.assertEqual(result['outside_scope_count'],2)
            self.assertLess(len(json.dumps(result)),30000)
            search=self.call('holdings_query',{'mode':'search','query':'PLOT','chain_id':8453})
            self.assertTrue(search['ambiguous']);self.assertEqual(search['matched_asset_count'],2)
            self.assertEqual(search['match_type'],'exact')
            wallet['assets'][10]['name']='PLOT fan token'
            self.assertEqual(self.call('holdings_query',{'mode':'search','query':'PLOT'})['matched_asset_count'],2)
            pages=[self.call('holdings_query',{'mode':'search','query':'PLOT','limit':1,'offset':offset}) for offset in (0,1)]
            self.assertEqual([p['next_offset'] for p in pages],[1,None])
            self.assertEqual(len({r['identity'] for p in pages for r in p['results']}),2)
            aggregate=self.call('holdings_query',{'mode':'aggregate','minimum_value_usd':1700})
            self.assertEqual(aggregate['matched_position_count'],19)
            self.assertEqual(aggregate['valuation']['all_priced_positions']['estimated_value_usd'],str(sum(range(1700,1719))))
            page=self.call('wallet_read',{'wallet':self.first['address_key'],'limit':100})
            self.assertEqual(page['next_offset'],100)
            with self.assertRaises(JobError):self.call('holdings_query',{'mode':'rank','wallet':self.other})
        for args in ({'mode':'search'},{'mode':'rank','limit':100},{'mode':'rank','environment':'other'},{'mode':'rank','group_by':'symbol'}):
            with self.assertRaises(JobError):self.call('holdings_query',args)
        self.assertEqual(JobStore(self.root).list(),[])

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




    def test_read_plan_returns_precise_receipts_and_cannot_enqueue(self):
        reads=[{'name':'portfolio_read','arguments':{}},{'name':'wallet_read','arguments':{'wallet':self.first['address_key']}},{'name':'wallet_read','arguments':{'wallet':self.other}}]
        result=self.call('records_read',{'reads':reads})
        self.assertEqual(result['completion'],'partial');self.assertEqual(result['completed_reads'],2)
        self.assertEqual([r['status'] for r in result['reads']],['completed','completed','failed'])
        with self.assertRaises(JobError):self.call('records_read',{'reads':[{'name':'holdings_refresh','arguments':{'wallet':self.first['address_key']}}]})
        self.assertEqual(JobStore(self.root).list(),[])
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
    def test_native_rows_keep_a_null_address_in_every_read(self):
        from copy import deepcopy
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parent/'viewer'))
        import model
        state,stamp,stale=model.load_state(self.root)
        wallet=state['wallets'][0]
        wallet['assets']=[{**deepcopy(wallet['assets'][0]),'id':'8453:native','chain_id':8453,'address':None,'is_native':True,
                           'environment':'mainnet','balance':'1','value_usd':2000,'symbol':'ETH'}]
        with patch('model.load_state',return_value=(state,stamp,stale)):
            listed=self.call('wallet_read',{'wallet':self.first['address_key']})['assets'][0]
            ranked=self.call('holdings_query',{'mode':'rank','limit':1})['results'][0]['positions'][0]['asset']
        self.assertIn('address',listed);self.assertIsNone(listed['address']);self.assertIsNone(ranked['address'])
    def test_snapshot_list_separates_progress_publications_from_finished_lookups(self):
        store=JobStore(self.root);registry=json.loads((self.root/'wallets.json').read_text())
        final=self.first['latest_snapshot']['directory'];progress=final+'/holdings-initial-0001'
        source=json.loads((self.root/final/'results.json').read_text())
        atomic(self.root/progress/'results.json',{**source,'compiled_at':'2026-01-01T00:00:00Z','pipeline':{'version':2,'phase':'initial'}})
        atomic(self.root/final/'results.json',{**source,'pipeline':{'version':2,'phase':'holdings'}})
        registry.setdefault('research_runs',[]).append({'address_key':self.first['address_key'],'snapshot':progress});atomic(self.root/'wallets.json',registry)
        rows={row['snapshot_id']:row['phase'] for row in self.call('snapshots_list',{'wallet':self.first['address_key']})}
        self.assertEqual(rows,{progress:'initial',final:'holdings'})
        self.assertEqual(rows,{row['snapshot_id']:row['phase'] for row in store.snapshots(self.first['address_key'])})
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
