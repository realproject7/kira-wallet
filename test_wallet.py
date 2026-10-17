"""Failure, pagination and identity checks for the reusable wallet pipeline."""
import json
from pathlib import Path
import tempfile
import unittest
import contextlib
import io
import runpy
import sys
import threading
from unittest.mock import patch
import wallet
sys.path.insert(0,str(wallet.ASSETS/'viewer'))


class WalletPipelineTests(unittest.TestCase):
    address='0x0000000000000000000000000000000000000011'
    network={'chain_id':8453,'environment':'mainnet'}

    def test_missing_prices_keep_original_dates_but_contrary_reads_invalidate_them(self):
        old={'chain_id':1,'address':self.address,'usd':2,'quality':'estimated','source':'https://example.org/quote','observed_at':'2026-10-01T00:00:00Z'}
        saved=wallet.retain_price_evidence({'tokens':[]},{'tokens':[old]})['tokens'][0]
        self.assertEqual(saved['observed_at'],old['observed_at']);self.assertEqual(saved['source'],old['source'])
        self.assertTrue(saved['retained_from_previous']);self.assertEqual(saved['latest_price_status'],'unavailable')
        for fresh in ({**old,'usd':3},{**old,'usd':None,'quality':'unfunded'},{**old,'usd':None,'quality':'unreliable'}):
            self.assertEqual(wallet.retain_price_evidence({'tokens':[fresh]},{'tokens':[old]})['tokens'][0],fresh)
        for bad in ({'observed_at':None},{'observed_at':'2026-10-01'},{'usd':'NaN'},{'usd':-1}):
            self.assertEqual(wallet.retain_price_evidence({'tokens':[]},{'tokens':[{**old,**bad}]}),{'tokens':[]})

    def test_market_discovery_bounds_failures_and_keeps_late_success(self):
        token={'chain_id':8453,'token_address':self.address,'token_type':'ERC20'}
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            with patch.object(wallet,'fetch',return_value={'research_pending':True}) as fetch:
                self.assertEqual(wallet.dex_fetch(token,folder,attempt_limit=2)['status'],'pending')
                self.assertEqual(wallet.dex_fetch(token,folder,attempt_limit=2)['status'],'unavailable')
                self.assertEqual(wallet.dex_fetch(token,folder,attempt_limit=2)['status'],'unavailable')
                self.assertEqual(fetch.call_count,2)
            for f in folder.iterdir():f.unlink()
            with patch.object(wallet,'time') as clock,patch.object(wallet,'fetch',return_value=[{'saved':'successful response'}]) as fetch:
                clock.monotonic.return_value=10
                self.assertEqual(wallet.dex_fetch(token,folder,deadline=5,attempt_limit=2)['status'],'pending');fetch.assert_not_called()
                clock.monotonic.side_effect=[1,10]
                row=wallet.dex_fetch(token,folder,deadline=5,attempt_limit=2)
                self.assertIsInstance(row['response'],list)
                self.assertEqual(wallet.dex_fetch(token,folder,attempt_limit=2),row)
                self.assertEqual(fetch.call_count,1)

    def test_ready_chain_is_scanned_before_slow_discovery_finishes_with_one_writer(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);started=threading.Event();order=[]
            networks=[{'chain_id':1},{'chain_id':8453}]
            def acquire(n):
                if n['chain_id']==1:
                    self.assertTrue(started.wait(2),'Ready chain blocked behind slow discovery')
                return {'chain_id':n['chain_id'],'tokens':[{'chain_id':n['chain_id'],'address':self.address}],
                        'mintclub_id0_discovery':{'tokens':[]}}
            def scan(mode,source,destination):
                self.assertEqual(mode,'scan-slice')
                data=wallet.read(source);self.assertEqual(len(data['networks']),1)
                cid=data['networks'][0]['chain_id'];order.append(cid)
                if cid==8453:started.set()
                wallet.atomic(destination/'onchain-summary.json',{'chains':[{'chain_id':cid,'research_pending':True}]})
            with patch.object(wallet,'run_node',side_effect=scan):
                discovered=wallet.acquire_candidate_slices(self.address,networks,folder,'wallet_candidates_v1',acquire,[],[])
            self.assertEqual(order,[8453,1])
            self.assertEqual([r['chain_id'] for r in discovered],[1,8453])
            summary=wallet.read(folder/'onchain-summary.json')
            self.assertEqual([r['chain_id'] for r in summary['chains']],[1,8453])
            self.assertTrue(all(r['research_pending'] for r in summary['chains']))
            self.assertEqual(len(wallet.read(folder/'scan-input.json')['candidates']),2)

    def test_script_and_imported_engine_share_the_same_pause_exception(self):
        namespace=runpy.run_path(wallet.__file__,run_name='synthetic_entrypoint')
        self.assertIs(namespace['MarketPause'],wallet.MarketPause)
        self.assertIs(namespace['ResearchPause'],wallet.ResearchPause)
        with self.assertRaises(namespace['MarketPause']):
            raise wallet.MarketPause('Synthetic reserve budget')

    def test_continuation_progress_ignores_timestamps_but_counts_new_evidence_and_quota(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            checkpoint={'balances':{'token:ERC20':'7'},'balance_times':{'token:ERC20':'first'},'observed_at':'first'}
            wallet.atomic(folder/'balance-checkpoint-1.json',checkpoint)
            discovery=[{'chain_id':1,'tokens':[],'discovery_status':'throttled','retry_not_before':1120,
                        'history_window':{'page':2,'started_at':1}}]
            first=wallet.continuation_checkpoint(folder,discovery,False)
            self.assertEqual(first['not_before'],1120)
            checkpoint['observed_at']='later';checkpoint['balance_times']['token:ERC20']='later'
            wallet.atomic(folder/'balance-checkpoint-1.json',checkpoint)
            discovery[0]['history_window']['started_at']=2
            second=wallet.continuation_checkpoint(folder,discovery,False)
            self.assertEqual(first['fingerprint'],second['fingerprint'])
            checkpoint['balances']['other:ERC1155']='3';wallet.atomic(folder/'balance-checkpoint-1.json',checkpoint)
            third=wallet.continuation_checkpoint(folder,discovery,True)
            self.assertNotEqual(first['fingerprint'],third['fingerprint']);self.assertEqual(third['not_before'],0)

    def test_inventory_resume_preserves_old_scope_and_rejects_policy_changes(self):
        self.assertEqual(wallet.inventory_policy(),'full_registry')
        self.assertEqual(wallet.inventory_policy('full'),'full_registry')
        self.assertEqual(wallet.inventory_policy(manifest={}), 'full_registry')
        self.assertEqual(wallet.inventory_policy(manifest={'inventory_policy':'wallet_candidates_v1'}),'wallet_candidates_v1')
        with self.assertRaisesRegex(ValueError,'scope mismatch'):wallet.inventory_policy('market',{})
        with self.assertRaisesRegex(ValueError,'Invalid saved'):wallet.inventory_policy(manifest={'inventory_policy':'unexpected'})

    def test_id0_source_respects_public_optout_and_continuation_counts_its_frontier(self):
        with patch.object(wallet,'load_config',return_value={'discovery':{'public':False}}),patch('transfer_discovery.discover') as discover:
            row=wallet.discover_mintclub_id0(self.address,self.network,self.folder)
        discover.assert_not_called();self.assertEqual(row['discovery_status'],'disabled')
        discovered=[{'chain_id':8453,'tokens':[],'complete':True,'mintclub_id0_discovery':{
            'tokens':[],'provider':'etherscan_keyless_erc1155_id0','complete':False,'discovery_status':'throttled','retry_not_before':1234,
            'history_window':{'page':2}}}]
        first=wallet.continuation_checkpoint(self.folder,discovered,False)
        self.assertEqual(first['not_before'],1234)
        discovered[0]['mintclub_id0_discovery']['tokens']=[{'address':'0x'+'2'*40}]
        second=wallet.continuation_checkpoint(self.folder,discovered,False)
        self.assertNotEqual(first['fingerprint'],second['fingerprint'])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.folder=Path(self.temp.name)
        self.secret=patch.object(wallet.h,'secrets',return_value={'ALCHEMY_CUSTOM_APY_KEY':'fixture-key'})
        self.secret.start()
        self.config=patch.object(wallet,'load_config',return_value={'discovery':{'provider':'alchemy','explorers':True}})
        self.config.start()

    def tearDown(self):
        self.secret.stop()
        self.config.stop()
        self.temp.cleanup()

    def token(self,address='0x0000000000000000000000000000000000000001',network='base-mainnet'):
        return {'address':self.address,'network':network,'tokenAddress':address,'tokenBalance':'0x1',
                'tokenMetadata':{'decimals':18,'symbol':'Fixture','name':'Fixture'},'tokenPrices':[]}

    def test_fresh_baseline_publishes_initial_and_final_without_enrichment_gate(self):
        from kira_cli import initialize
        initialize(self.folder)
        token={'chain_id':8453,'network':'base','token_address':'0x'+'2'*40,'token_type':'ERC20',
               'wallet_balance':'1','symbol':'TEST','mintclub':None,'dex_pools':[],'dex_liquidity_found':False}
        chain={'chain_id':8453,'rpc_status':'available','native_balance':'1','tokens':[token],
               'registry_scan':{'checked':0,'registry_count':None,'complete':False,'phase':'deferred'}}
        def scan(mode,source,destination,on_chain=None):
            self.assertEqual(mode,'scan')
            network_ids=[n['chain_id'] for n in wallet.read(source)['networks']]
            self.assertEqual(set(network_ids),{n['chain_id'] for n in wallet.read(self.folder/'networks.json')['networks']})
            self.assertEqual(wallet.read(source)['inventory_policy'],'full_registry')
            wallet.atomic(destination/'chain-8453.json',chain)
            on_chain({'stage':'chain','chain_id':8453})
            wallet.atomic(destination/'onchain-summary.json',{'chains':[chain]})
        with patch.object(wallet,'ROOT',self.folder),patch('kira_config.require_alchemy'),patch.object(wallet,'source_check'),patch.object(wallet,'validate_address',return_value=self.address),patch.object(wallet,'run_node',side_effect=scan),patch.object(wallet,'discover',return_value={'chain_id':8453,'complete':False,'tokens':[]}),patch('native_assets.market_metadata',return_value={'prices':{}}),patch.object(wallet,'fetch',return_value=[]),patch('token_images.refresh_catalog',return_value={}) as images,patch.object(sys,'argv',['wallet.py','add',self.address,'--tag','Fixture','--phase','baseline']),contextlib.redirect_stdout(io.StringIO()):
            wallet.main()
        entry=wallet.read(self.folder/'wallets.json')['wallets'][0]
        folder=self.folder/entry['latest_snapshot']['directory']
        self.assertIn('completed_at',wallet.read(folder/'run.json'))
        self.assertEqual(wallet.read(folder/'results.json')['pipeline']['phase'],'holdings')
        self.assertEqual(wallet.read(folder/'initial/results.json')['tokens'][0]['wallet_balance'],'1')
        self.assertEqual(len(wallet.read(self.folder/'wallets.json')['research_runs']),2)
        images.assert_called_once()
        self.assertTrue((folder/'token-market-metadata.json').exists())

    def test_basic_metadata_prices_a_curve_from_its_reserve_without_full_market_review(self):
        reserve='0x'+'2'*40;child='0x'+'3'*40;unpriced='0x'+'4'*40
        observed='2026-10-16T12:00:00Z'
        mint={'reserve_token':reserve,'reserve_symbol':'HUNT','price_for_next_mint_in_reserve_token':'0.25',
              'funded':True,'reserve_balance':'20','source_url':'https://mint.club/token/base/'+child,
              'observed_at':observed,'block_number':'123'}
        snapshot={'wallet_address':self.address,'coverage':[self.network],
                  'tokens':[{'chain_id':8453,'token_address':child,'token_type':'ERC20','wallet_balance':'7','mintclub':mint},
                            {'chain_id':8453,'token_address':unpriced,'token_type':'ERC20','mintclub':None}]}
        snapshot['coverage'].append({'chain_id':84532,'environment':'testnet'})
        snapshot['tokens'].append({'chain_id':84532,'token_address':child,'token_type':'ERC20','mintclub':mint})
        pair={'chainId':'base','pairAddress':'0x'+'5'*40,'dexId':'uniswap',
              'baseToken':{'address':reserve,'symbol':'HUNT'},'quoteToken':{'address':'0x'+'6'*40},
              'liquidity':{'usd':10000,'base':2000},'priceUsd':'2','url':'https://example.org/pool'}
        before=json.dumps(snapshot,sort_keys=True)
        with patch.object(wallet,'fetch',return_value=[pair,{**pair,'chainId':'ethereum','priceUsd':'999'}]),\
             patch.object(wallet.h,'now',return_value='2026-10-16T12:01:00Z'),\
             patch('curve_pricing.enrich') as enrich,patch('token_images.refresh_catalog',return_value={}) as images,\
             patch.object(wallet,'event'):
            market=wallet.refresh_metadata(snapshot,{'tokens':[]},self.folder,discover_prices=True)
        rows={(p['chain_id'],p['address']):p for p in market['tokens']}
        self.assertEqual(rows[(8453,child)]['usd'],0.5)
        self.assertEqual(rows[(8453,child)]['observed_at'],observed)
        self.assertEqual(rows[(8453,reserve)]['usd'],2)
        self.assertNotIn((8453,unpriced),rows)
        self.assertNotIn((84532,child),rows)
        self.assertNotIn((84532,reserve),rows)
        self.assertEqual(json.dumps(snapshot,sort_keys=True),before)
        enrich.assert_not_called();images.assert_called_once()
        self.assertEqual(images.call_args.kwargs['market_metadata'],wallet.read(self.folder/'token-market-metadata.json'))

    def test_metadata_provider_gap_keeps_saved_price_and_still_refreshes_artwork(self):
        address='0x'+'2'*40
        snapshot={'wallet_address':self.address,'coverage':[self.network],
                  'tokens':[{'chain_id':8453,'token_address':address,'token_type':'ERC20','mintclub':None}]}
        old={'chain_id':8453,'address':address,'usd':2,'quality':'estimated','observed_at':'2026-10-01T00:00:00Z'}
        with patch.object(wallet,'fetch',return_value={'transport_error':{'status':429}}),\
             patch('token_images.refresh_catalog',return_value={}) as images,patch.object(wallet,'event'):
            market=wallet.refresh_metadata(snapshot,{'tokens':[old]},self.folder,discover_prices=True)
        self.assertEqual(market['tokens'],[old]);images.assert_called_once()

    def test_basic_metadata_keeps_completed_reserve_paths_when_the_slice_pauses(self):
        child='0x'+'2'*40;parent='0x'+'3'*40;reserve='0x'+'4'*40
        observed='2026-10-16T12:00:00Z'
        mint={'reserve_token':parent,'reserve_symbol':'PARENT','price_for_next_mint_in_reserve_token':'0.5',
              'funded':True,'reserve_balance':'20','source_url':'https://mint.club/token/base/'+child,
              'observed_at':observed,'block_number':'123'}
        snapshot={'wallet_address':self.address,'coverage':[self.network],
                  'tokens':[{'chain_id':8453,'token_address':child,'token_type':'ERC20','mintclub':mint}]}
        original=json.dumps(snapshot,sort_keys=True)
        graph=[{'chain_id':8453,'address':address,'is_curve':True,'reserve_token':backing,
                'reserve_symbol':'RESERVE','price_in_reserve':'0.5','funded':True,'curve_reserve':'20',
                'source':'https://mint.club/token/base/'+address,'observed_at':observed,'block_number':'123'}
               for address,backing in [(child,parent),(parent,reserve)]]
        def paused(*args,**kwargs):
            wallet.atomic(self.folder/'reserve-graph.json',{'tokens':graph,'market_pending':True})
            raise wallet.MarketPause('Saved partial reserve work.')
        for quality,expected in [('estimated',1),('unreliable',None)]:
            with self.subTest(quality=quality),patch('curve_pricing.enrich',side_effect=paused),\
                 patch('token_images.refresh_catalog',return_value={}),patch.object(wallet,'event'):
                price={'chain_id':8453,'address':reserve,'usd':4 if quality=='estimated' else None,
                       'basis':'DEX market','quality':quality,'liquidity_usd':10000,'observed_at':observed}
                market=wallet.refresh_metadata(snapshot,{'tokens':[price]},self.folder)
            rows={p['address']:p for p in market['tokens']}
            self.assertEqual(rows[child]['usd'],expected)
            self.assertEqual(rows[child]['observed_at'],observed)
            self.assertEqual(market['reserve_price_status'],'partial')
        self.assertEqual(json.dumps(snapshot,sort_keys=True),original)

    def test_partial_200_preserves_candidates_without_claiming_complete(self):
        data={'data':{'tokens':[self.token()]},'error':{'partialErrors':[{'network':'base-mainnet','message':'timeout'}]}}
        with patch.object(wallet,'fetch',return_value=data):
            result=wallet.discover(self.address,self.network,self.folder)
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['tokens']),1)
        self.assertIn('partialErrors',result['error'])
        self.assertEqual(result['discovery_status'],'provider_error')

    def test_disabled_and_missing_credentials_record_the_actual_reason(self):
        for provider,secrets,expected in [('none',{},'disabled'),('alchemy',{},'missing_credential')]:
            with patch.object(wallet,'load_config',return_value={'discovery':{'provider':provider,'explorers':False,'public':False}}),patch.object(wallet.h,'secrets',return_value=secrets),patch.object(wallet,'fetch') as fetch:
                result=wallet.discover(self.address,self.network,self.folder)
            fetch.assert_not_called();self.assertFalse(result['complete'])
            self.assertEqual(result['discovery_status'],expected)
        with patch.object(wallet,'load_config',return_value={'discovery':{'provider':'alchemy','public':False,'explorers':False}}),patch.object(wallet.h,'secrets',side_effect=ValueError('Unreadable secret file')),patch.object(wallet,'fetch') as fetch:
            result=wallet.discover(self.address,self.network,self.folder)
        fetch.assert_not_called();self.assertEqual(result['discovery_status'],'missing_credential')

    def test_pagination_deduplicates_and_rejects_other_network_or_wallet(self):
        foreign=self.token();foreign['address']='0x0000000000000000000000000000000000000002'
        responses=[{'data':{'tokens':[self.token(),self.token(network='eth-mainnet'),foreign],'pageKey':'next'}},
                   {'data':{'tokens':[self.token(),self.token('0x0000000000000000000000000000000000000003')],'pageKey':None}}]
        with patch.object(wallet,'fetch',side_effect=responses) as fetch:
            result=wallet.discover(self.address,self.network,self.folder)
        self.assertTrue(result['complete']);self.assertEqual(len(result['tokens']),2)
        self.assertEqual(result['discovery_status'],'checked')
        self.assertEqual(fetch.call_args_list[1].args[1]['pageKey'],'next')
        persisted=json.loads((self.folder/'discovery-8453.json').read_text())
        self.assertNotIn('fixture-key',json.dumps(persisted))
        self.assertIsNone(persisted['pages'][0]['request'].get('pageKey'))

    def test_repeated_cursor_and_transport_failure_are_incomplete(self):
        with patch.object(wallet,'fetch',return_value={'data':{'tokens':[],'pageKey':'same'}}):
            result=wallet.discover(self.address,self.network,self.folder)
        self.assertFalse(result['complete']);self.assertIn('Repeated',result['error']['message'])
        with patch.object(wallet,'fetch',return_value={'transport_error':{'status':503,'message':'unavailable'}}):
            result=wallet.discover(self.address,self.network,self.folder)
        self.assertFalse(result['complete']);self.assertEqual(result['error']['status'],503)

    def test_registration_keeps_identity_tags_and_history(self):
        registry={'wallets':[],'tag_history':[]}
        wallet.register(registry,self.address,'Demo main')
        wallet.register(registry,self.address.lower(),'Secondary tag')
        wallet.register(registry,self.address,'Demo main')
        self.assertEqual(len(registry['wallets']),1)
        self.assertEqual(registry['wallets'][0]['address'],self.address)
        self.assertEqual(registry['wallets'][0]['tags'],['Demo main','Secondary tag'])
        self.assertEqual(len(registry['tag_history']),2)

    def test_malformed_provider_payloads_do_not_become_complete_empty_wallets(self):
        missing=self.token();missing.pop('tokenBalance')
        identities=[]
        for field in ('network','address'):
            for value in (None,17,{},''):
                token=self.token();token[field]=value;identities.append({'data':{'tokens':[token]}})
            token=self.token();token.pop(field);identities.append({'data':{'tokens':[token]}})
        for response in ({'data':{}},{'data':{'tokens':None}},{'data':{'tokens':[missing]}},['invalid'],{'data':{'tokens':[None]}},*identities):
            with patch.object(wallet,'fetch',return_value=response):result=wallet.discover(self.address,self.network,self.folder)
            self.assertFalse(result['complete']);self.assertEqual(result['discovery_status'],'provider_error');self.assertTrue(result['error'])

    def test_polygon_uses_the_portfolio_network_name(self):
        with patch.object(wallet,'fetch',return_value={'data':{'tokens':[]}}) as fetch:
            result=wallet.discover(self.address,{'chain_id':137},self.folder)
        self.assertTrue(result['complete']);self.assertEqual(fetch.call_args.args[1]['addresses'][0]['networks'],['matic-mainnet'])

    def test_supported_scope_changes_stop_before_analysis(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return b"  BOND: {\n    [base.id]: '0x0000000000000000000000000000000000000000',\n  },"
        with patch('urllib.request.urlopen',return_value=Response()):
            with self.assertRaisesRegex(ValueError,'scope changed'):
                wallet.source_check([{'chain_id':8453,'mintclub_bond_address':'0xc5a076cad94176c2996B32d8466Be1cE757FAa27'}],self.folder)

    def test_outside_dex_scope_reserve_preserves_unknown_observation(self):
        token={'chain_id':54176,'token_address':'0x'+'3'*40,'token_type':'ERC20'}
        with patch.object(wallet,'fetch') as fetch:
            row=wallet.dex_fetch(token,self.folder)
        fetch.assert_not_called();self.assertEqual(row['response'],[]);self.assertIsNone(row['observed_at'])
        import sys
        sys.path.insert(0,str(wallet.ASSETS/'viewer'))
        from model import dex_price
        self.assertIsNone(dex_price({**token,'dex_pools':[],'indexer_price_references':[]},row.get('observed_at')))

    def test_public_analysis_has_independent_native_price_and_image_evidence(self):
        import sys
        sys.path.insert(0,str(wallet.ASSETS/'viewer'))
        wallet.atomic(self.folder/'onchain-summary.json',{'chains':[{'chain_id':8453,'tokens':[],
            'native_balance':'1','observed_at':'2026-10-04T12:00:00Z','rpc_status':'available','registry_scan':{'complete':True,'checked':0,'registry_count':0}}]})
        metadata={'prices':{'ETH_USD':{'value':2000,'observed_at':'2026-10-04T12:00:00Z','source':'https://api.coingecko.com','asset_id':'ethereum'}},
            'images':{'ethereum':{'image_url':'https://coin-images.coingecko.com/eth.png'}},'evidence':{'source':'https://api.coingecko.com','response':[]}}
        def node(command,input_path,output_path):wallet.atomic(output_path,{'tokens':[],'market_pending':False})
        with patch.object(wallet,'run_node',side_effect=node),patch.object(wallet,'event'),\
             patch('native_assets.market_metadata',return_value=metadata) as native,\
             patch('curve_pricing.enrich',side_effect=lambda snapshot,market,folder,**kwargs:market),\
             patch('token_images.refresh_catalog',return_value={}) as images:
            result=wallet.finish({'address':self.address,'tags':['Fixture']},self.folder,[{**self.network,'name':'Base','mintclub_network':'base'}],
                [{'chain_id':8453,'complete':False,'source':None,'pages':[],'native':[]}])
        self.assertEqual(result['price_references']['ETH_USD']['value'],2000)
        self.assertEqual(json.loads((self.folder/'market-prices.json').read_text())['native_usd']['ETH']['asset_id'],'ethereum')
        self.assertEqual(images.call_args.kwargs['native_images'],metadata['images'])
        self.assertTrue((self.folder/'native-market.json').is_file())
        native.assert_called_once()
        with patch.object(wallet,'run_node',side_effect=node),patch.object(wallet,'event'),\
             patch('native_assets.market_metadata',return_value=metadata),\
             patch('curve_pricing.enrich',side_effect=lambda snapshot,market,folder,**kwargs:market),\
             patch('token_images.refresh_catalog',return_value={}):
            result=wallet.finish({'address':self.address,'tags':['Fixture']},self.folder,[{**self.network,'name':'Base','mintclub_network':'base'}],
                [{'chain_id':8453,'complete':True,'source':None,'pages':[],'native':[
                    {'tokenPrices':[{'currency':'usd','value':'2100','lastUpdatedAt':'2026-10-04T12:00:00Z'}]}]}])
        self.assertEqual(result['price_references']['ETH_USD']['value'],'2100')
        self.assertEqual(result['price_references']['ETH_USD']['source'],'Alchemy Portfolio Tokens By Wallet')

    def test_republished_holdings_price_links_to_the_cached_raw_observation(self):
        address='0x4200000000000000000000000000000000000006'
        observed='2026-10-14T05:06:00Z'
        token={'chain_id':8453,'network':'base','token_address':address,'token_type':'ERC20',
               'symbol':'WETH','name':'Wrapped Ether','wallet_balance':'1','wallet_balance_raw':str(10**18),
               'mintclub':None,'dex_pools':[],'dex_liquidity_found':False}
        pair={'chainId':'base','pairAddress':'0x'+'3'*40,'dexId':'uniswap',
              'baseToken':{'address':address,'symbol':'WETH'},'quoteToken':{'address':'0x'+'4'*40,'symbol':'QUOTE'},
              'liquidity':{'usd':10000,'base':2},'priceUsd':'2000','url':'https://example.com/pool'}
        wallet.atomic(self.folder/f'dex-8453-{address}.json',{'chain_id':8453,'token_address':address,
            'source':f'https://api.dexscreener.com/token-pairs/v1/base/{address}',
            'observed_at':observed,'response':[pair]})
        wallet.atomic(self.folder/'onchain-summary.json',{'chains':[{'chain_id':8453,'tokens':[token],
            'native_balance':'0','observed_at':observed,'rpc_status':'available',
            'registry_scan':{'complete':True,'checked':0,'registry_count':0}}]})
        def node(command,input_path,output_path):
            wallet.atomic(output_path,{'tokens':wallet.read(input_path)['tokens'],'market_pending':False})
        with patch.object(wallet,'run_node',side_effect=node),patch.object(wallet,'event'),\
             patch.object(wallet.h,'now',return_value='2026-10-14T05:20:00Z'),\
             patch('native_assets.market_metadata',return_value={'prices':{},'images':{},'evidence':None}),\
             patch('curve_pricing.enrich',side_effect=lambda snapshot,market,folder,**kwargs:market),\
             patch('token_images.refresh_catalog',return_value={}):
            result=wallet.finish({'address':self.address,'tags':['Fixture']},self.folder,
                [{**self.network,'name':'Base','mintclub_network':'base'}],
                [{'chain_id':8453,'complete':True,'source':None,'pages':[],'native':[]}],holdings_source='snapshots/same-wallet-holdings')
        prices=wallet.read(self.folder/'market-prices.json')
        self.assertFalse(prices['balance_refresh'])
        self.assertEqual(result['pipeline']['holdings_snapshot'],'snapshots/same-wallet-holdings')
        self.assertEqual(result['compiled_at'],'2026-10-14T05:20:00Z')
        self.assertEqual(prices['tokens'][0]['observed_at'],observed)
        self.assertEqual(prices['tokens'][0]['usd'],2000)

    def test_candidate_balance_errors_keep_successful_discovery_partial(self):
        wallet.atomic(self.folder/'onchain-summary.json',{'chains':[{'chain_id':8453,'tokens':[],
            'native_balance':'0','observed_at':'2026-10-04T12:00:00Z','rpc_status':'available',
            'registry_scan':{'complete':True,'checked':0,'registry_count':0},
            'balance_errors':[{'error':{'message':'PRIVATE-DIAGNOSTIC'}}]}]})
        def node(command,input_path,output_path):wallet.atomic(output_path,{'tokens':[],'market_pending':False})
        with patch.object(wallet,'run_node',side_effect=node),patch.object(wallet,'event'),\
             patch('native_assets.market_metadata',return_value={'prices':{},'images':{},'evidence':None}),\
             patch('curve_pricing.enrich',side_effect=lambda snapshot,market,folder,**kwargs:market),\
             patch('token_images.refresh_catalog',return_value={}):
            result=wallet.finish({'address':self.address,'tags':['Fixture']},self.folder,
                [{**self.network,'name':'Base','mintclub_network':'base'}],
                [{'chain_id':8453,'complete':True,'source':None,'pages':[],'native':[]}])
        self.assertEqual(result['coverage'][0]['candidate_balance_errors'],1)
        self.assertEqual(result['status'],'completed_with_coverage_gaps')
        self.assertNotIn('PRIVATE-DIAGNOSTIC',json.dumps(result))

    def test_market_budget_publishes_immutable_balances_without_deferring_completed_registry(self):
        folder=self.folder/'snapshots'/'job';entry={'address':self.address,'address_key':self.address.lower(),'tags':['Fixture']}
        wallet.atomic(self.folder/'wallets.json',{'wallets':[entry],'research_runs':[]})
        wallet.atomic(folder/'onchain-summary.json',{'chains':[{'chain_id':8453,'tokens':[],
            'native_balance':'1','observed_at':'2026-10-09T00:00:00Z','block_number':'101','rpc_status':'available',
            'registry_scan':{'complete':True,'checked':10,'registry_count':10,'phase':'checked'}}]})
        def node(command,input_path,output_path):wallet.atomic(output_path,{'tokens':[],'market_pending':True})
        network={**self.network,'name':'Base','mintclub_network':'base'}
        discovery=[{'chain_id':8453,'complete':True,'source':None,'pages':[],'native':[]}]
        with patch.object(wallet,'ROOT',self.folder),patch.object(wallet,'run_node',side_effect=node),patch.object(wallet,'event') as events,\
             patch('native_assets.market_metadata',return_value={'prices':{},'images':{},'evidence':None}) as native,patch('curve_pricing.enrich') as enrich,patch('token_images.refresh_catalog') as images:
            with self.assertRaises(wallet.MarketPause):wallet.finish(entry,folder,[network],discovery)
            first=folder/'market-initial-0001'/'results.json';original=first.read_bytes();result=json.loads(original)
            self.assertEqual(result['coverage'][0]['native_balance'],'1')
            self.assertEqual(result['coverage'][0]['native_block_number'],'101')
            self.assertTrue(result['coverage'][0]['mintclub_registry_scan']['complete'])
            self.assertEqual(result['coverage'][0]['mintclub_registry_scan']['phase'],'checked')
            self.assertTrue(result['pipeline']['market_pending'])
            self.assertEqual(result['status'],'completed_with_coverage_gaps')
            native.assert_called_once();enrich.assert_not_called();images.assert_not_called()
            self.assertEqual(events.call_args.args[0],'market_paused')
            with self.assertRaises(wallet.MarketPause):wallet.finish(entry,folder,[network],discovery)
            self.assertEqual(first.read_bytes(),original)
            self.assertTrue((folder/'market-initial-0002'/'results.json').exists())

    def test_funded_routes_and_output_prices_run_even_when_general_pools_are_pending(self):
        folder=self.folder/'snapshots'/'job';entry={'address':self.address,'address_key':self.address.lower(),'tags':['Fixture']}
        wallet.atomic(self.folder/'wallets.json',{'wallets':[entry],'research_runs':[]})
        reserve='0x4200000000000000000000000000000000000006'
        token={'chain_id':8453,'token_address':'0x'+'8'*40,'token_type':'ERC20','symbol':'SYNTHETIC',
            'wallet_balance':'1','wallet_balance_raw':'1','dex_pools':[],
            'mintclub':{'funded':True,'reserve_token':reserve}}
        wallet.atomic(folder/'onchain-summary.json',{'chains':[{'chain_id':8453,'tokens':[token],
            'native_balance':'0','observed_at':'2026-10-14T01:00:00Z','rpc_status':'available','registry_scan':{'complete':False}}]})
        calls=[];fetches=[]
        def node(command,input_path,output_path):
            calls.append((command,wallet.read(input_path)['market_budget_ms']))
            wallet.atomic(output_path,{'tokens':wallet.read(input_path)['tokens'],'market_pending':command=='dex'})
        def dex(t,folder,deadline,attempt_limit=None):
            fetches.append(t['token_address']);return {'response':[],'observed_at':'2026-10-14T01:00:00Z'}
        with patch.object(wallet,'ROOT',self.folder),patch.object(wallet,'run_node',side_effect=node),patch.object(wallet,'dex_fetch',side_effect=dex),\
             patch.object(wallet,'event'),patch.object(wallet,'report'),patch('native_assets.market_metadata',return_value={'prices':{},'images':{},'evidence':None}),\
             patch('curve_pricing.enrich',side_effect=lambda snapshot,market,folder,**kwargs:market) as enrich,patch('token_images.refresh_catalog'):
            with self.assertRaises(wallet.MarketPause):wallet.finish(entry,folder,[{**self.network,'name':'Base'}],[{'chain_id':8453,'complete':True,'source':None,'pages':[],'native':[]}])
        self.assertEqual([command for command,_ in calls],['liquidate','dex','liquidate'])
        self.assertLessEqual(calls[1][1],60000);self.assertIn(reserve,fetches)
        enrich.assert_called_once()


if __name__=='__main__':unittest.main()
