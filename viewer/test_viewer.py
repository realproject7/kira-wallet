"""Checks for valuation correctness, identity, live file updates and HTTP boundaries."""
from copy import deepcopy
from decimal import Decimal
from http.server import ThreadingHTTPServer
from pathlib import Path
import json
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error
import model
import server
import token_images

class ViewerTests(unittest.TestCase):
    def test_tiny_market_cannot_inflate_current_or_legacy_cached_totals(self):
        token=self.snapshot['tokens'][0]
        token.update(chain_id=1,symbol='CAI',wallet_balance='2',mintclub=None,dex_pools=[],indexer_price_references=[])
        self.snapshot['tokens']=[token];self.snapshot['coverage']=[c for c in self.snapshot['coverage'] if c['chain_id']==1];self.snapshot['price_references']={}
        price={'chain_id':1,'address':token['token_address'],'usd':1481349.43,'quality':'estimated','basis':'DEX market','source':'https://example.org/tiny-pool','observed_at':'2026-10-16T00:00:00Z'}
        pair={'chainId':'ethereum','pairAddress':'0x'+'3'*40,'dexId':'uniswap',
              'baseToken':{'address':token['token_address']},'quoteToken':{'address':'0x'+'4'*40},
              'priceUsd':'1481349.43','liquidity':{'usd':0.02,'base':0.000000009842},'url':price['source']}
        market=self.directory/'market-prices.json';market.write_text(json.dumps({'tokens':[price]}))
        (self.directory/'token-market-metadata.json').write_text(json.dumps([{'response':[pair],'observed_at':price['observed_at']}]))
        before=market.read_bytes()
        for row in (price,{**price,'liquidity_usd':0.02}):
            market.write_text(json.dumps({'tokens':[row]}))
            projected=model.project_wallet(self.entry,self.snapshot,self.root)
            asset=projected['assets'][0]
            self.assertEqual(asset['balance'],'2');self.assertIsNone(asset['value_usd'])
            self.assertEqual(asset['price']['quality'],'unreliable')
            self.assertIsNone(projected['known_value_usd'])
        market.write_bytes(before)
        token['dex_pools']=[{'paired_tokens':[pair['baseToken'],pair['quoteToken']],
            'reported_price_usd':pair['priceUsd'],'reported_liquidity':pair['liquidity'],'source_url':price['source']}]
        token['indexer_price_references']=[{'currency':'usd','value':'1481349.43'}]
        self.assertIsNone(model.dex_price(token,None)['usd'],'A rejected thin pool cannot fall back to the same indexed price.')
        self.assertEqual(market.read_bytes(),before)

    def test_alchemy_artwork_keeps_chain_identity_and_does_not_need_a_catalog_fetch(self):
        token=self.snapshot['tokens'][0]
        for image in ('https://static.alchemyapi.io/images/assets/fixture.png','https://s2.coinmarketcap.com/static/img/coins/64x64/fixture.png'):
            token['indexer_image_url']=image
            projected=model.project_wallet(self.entry,self.snapshot,self.root)
            self.assertEqual(next(a for a in projected['assets'] if a['address']==token['token_address'])['image_url'],image)
        token['indexer_image_url']='https://static.alchemyapi.io.evil.test/image.png'
        projected=model.project_wallet(self.entry,self.snapshot,self.root)
        self.assertNotEqual(next(a for a in projected['assets'] if a['address']==token['token_address'])['image_url'],token['indexer_image_url'])

    def test_initial_balances_wait_for_price_checks_before_entering_the_total(self):
        self.snapshot['pipeline']={'phase':'initial'}
        projected=model.project_wallet(self.entry,self.snapshot,self.root)
        self.assertTrue(all(a['value_usd'] is None for a in projected['assets'] if not a['is_native']))

    def test_optional_sell_work_does_not_invalidate_saved_holdings_coverage(self):
        self.snapshot['pipeline']={'phase':'sell','market_pending':True}
        self.snapshot['tokens'][0]['dex_verification_error']={'message':'A sale estimate is unavailable.'}
        before=json.dumps(self.snapshot,sort_keys=True)
        projected=model.project_wallet(self.entry,self.snapshot,self.root)
        self.assertTrue(projected['sell_analysis_pending'])
        self.assertTrue(all(not c['market_pending'] and c['market_errors']==0 for c in projected['chains']))
        self.assertEqual(sum(c['sell_analysis_errors'] for c in projected['chains']),1)
        self.assertEqual(json.dumps(self.snapshot,sort_keys=True),before)
        self.snapshot['pipeline']={'market_pending':True}
        legacy=model.project_wallet(self.entry,self.snapshot,self.root)
        self.assertTrue(all(c['market_pending'] for c in legacy['chains']))
        self.assertEqual(sum(c['market_errors'] for c in legacy['chains']),1)

    def test_failed_all_network_read_is_not_displayed_as_unstarted_work(self):
        self.snapshot['pipeline']={'phase':'holdings'}
        chain=self.snapshot['coverage'][0];chain['rpc_status']='pending'
        before=json.dumps(self.snapshot,sort_keys=True)
        evidence=self.directory/f"chain-{chain['chain_id']}.json"
        evidence.write_text(json.dumps({'wallet':self.entry['address_key'],'status':'unavailable'}))
        projected=model.project_wallet(self.entry,self.snapshot,self.root)
        row=next(c for c in projected['chains'] if c['id']==chain['chain_id'])
        self.assertEqual(row['rpc_status'],'unavailable');self.assertFalse(row['rpc_pending'])
        self.assertEqual(projected['lookup_mode'],'all_networks')
        self.assertEqual(json.dumps(self.snapshot,sort_keys=True),before)
        evidence.write_text(json.dumps({'wallet':'0x'+'2'*40,'status':'unavailable'}))
        projected=model.project_wallet(self.entry,self.snapshot,self.root)
        self.assertTrue(next(c for c in projected['chains'] if c['id']==chain['chain_id'])['rpc_pending'])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.snapshot=fixture_snapshot()
        address=self.snapshot['wallet_address']
        self.registry={'wallets':[{'address':address,'address_key':address,'tags':['Demo main'],
            'latest_snapshot':{'directory':'snapshots/demo','result':'snapshots/demo/results.json'}}]}
        self.entry=self.registry['wallets'][0]
        self.directory=self.root/self.entry['latest_snapshot']['directory'];self.directory.mkdir(parents=True)
        (self.root/'wallets.json').write_text(json.dumps(self.registry))
        (self.directory/'results.json').write_text(json.dumps(self.snapshot))
    def tearDown(self):self.temp.cleanup()

    def test_cached_dex_price_keeps_the_selected_source_clock_when_republished(self):
        address='0x'+'2'*40
        token={'token_address':address,'dex_pools':[
            {'paired_tokens':[{'address':address},{'address':'0x'+'3'*40}],
             'reported_price_usd':'2','reported_liquidity':{'usd':100,'base':20},
             'source_url':'https://example.com/pool','observed_at':'2026-10-14T05:06:00Z'}]}
        first=model.dex_price(token,'2026-10-14T05:10:00Z')
        second=model.dex_price(token,'2026-10-14T05:20:00Z')
        self.assertEqual(first,second)
        self.assertEqual(second['observed_at'],'2026-10-14T05:06:00Z')
        token['dex_pools'][0]['observed_at']='2026-10-14T05:21:00Z'
        self.assertEqual(model.dex_price(token,None)['observed_at'],'2026-10-14T05:21:00Z')

    def test_projection_does_not_invent_a_dex_observation_when_source_time_is_missing(self):
        token=self.snapshot['tokens'][0]
        token['mintclub']=None
        token['indexer_price_references']=[]
        token['dex_pools']=[{
            'pool':'0x'+'3'*40,'venue':'uniswap','paired_tokens':[
                {'address':token['token_address'],'symbol':token['symbol']},
                {'address':'0x'+'4'*40,'symbol':'QUOTE'}],
            'reported_price_usd':'2','reported_liquidity':{'usd':100,'base':20},
            'source_url':'https://example.com/pool'}]
        projected=model.project_wallet(self.entry,self.snapshot,self.root)
        asset=next(a for a in projected['assets'] if a['address']==token['token_address'].lower())
        self.assertIsNone(asset['price']['observed_at'])
        self.assertIsNone(asset['market_pools'][0]['observed_at'])

    def test_native_zero_observations_survive_without_becoming_holdings(self):
        self.snapshot['tokens']=[]
        zero,held=self.snapshot['coverage']
        zero.update(native_balance='0',native_observed_at='2026-10-05T01:00:00Z',native_block_number='101')
        held.update(native_balance='0.25',native_observed_at='2026-10-05T01:01:00Z',native_block_number='202')
        self.snapshot['coverage'].append({**zero,'chain_id':999,'name':'Unknown native',
            'rpc_status':'unavailable','native_balance':'0'})
        self.snapshot['price_references']['ETH_USD']['source']='https://private.invalid/SECRET-MARKER'
        self.snapshot['price_references']['DEBUG']={'value':'SECRET-MARKER'}
        wallet=model.project_wallet(self.entry,self.snapshot,self.root)
        self.assertEqual(len(wallet['assets']),1)
        self.assertEqual(wallet['assets'][0]['balance_observed_at'],'2026-10-05T01:01:00Z')
        self.assertEqual(wallet['known_value_usd'],500)
        self.assertEqual(wallet['chains'][0]['native_balance'],'0')
        self.assertEqual(wallet['chains'][0]['native_block_number'],'101')
        self.assertIsNone(wallet['chains'][2]['native_balance'])
        self.assertEqual(wallet['snapshot_price_references']['ETH_USD']['value'],'2000')
        self.assertNotIn('SECRET-MARKER',json.dumps(wallet['snapshot_price_references']))

    def test_discovery_reasons_and_registry_gaps_are_projected_without_raw_errors(self):
        first=self.snapshot['coverage'][0]
        first.update(discovery_status='disabled',general_erc20_discovery='incomplete',candidate_balance_errors=9,mintclub_registry_scan={
            'complete':False,'registry_errors':12,'balance_errors':3,'error_examples':[{'error':{'message':'SECRET-MARKER'}}]})
        self.snapshot['coverage'][1]['discovery_status']='SECRET-MARKER'
        wallet=model.project_wallet(self.entry,self.snapshot,self.root)
        self.assertEqual(wallet['chains'][0]['discovery_status'],'disabled')
        self.assertFalse(wallet['chains'][0]['registry_complete'])
        self.assertEqual(wallet['chains'][0]['registry_errors'],12)
        self.assertEqual(wallet['chains'][0]['balance_errors'],3)
        self.assertEqual(wallet['chains'][0]['candidate_balance_errors'],9)
        self.assertEqual(wallet['chains'][1]['discovery_status'],'incomplete')
        self.assertNotIn('SECRET-MARKER',json.dumps(wallet))

    def test_source_completion_and_unresolved_ranges_are_projected_independently(self):
        first=self.snapshot['coverage'][0]
        first.update(discovery_provider='multiple',discovery_status='source_limited',general_erc20_discovery='incomplete',
                     history_window={'startblock':0,'endblock':100,'pending_ranges':0,'blocked_ranges':1,'debug':'SECRET-MARKER'},
                     discovery_sources=[{'provider':'etherscan_keyless','complete':False,'discovery_status':'source_limited','error':'SECRET-MARKER'},
                                        {'provider':'routescan','complete':True,'discovery_status':'checked'},
                                        {'provider':'SECRET-MARKER','complete':True}])
        self.snapshot['coverage'][1]['discovery_sources']=None
        projected=model.project_wallet(self.entry,self.snapshot,self.root)
        chain=projected['chains'][0]
        self.assertFalse(chain['complete']);self.assertEqual(chain['discovery_status'],'source_limited')
        self.assertEqual(chain['history_window']['blocked_ranges'],1)
        self.assertEqual(len(chain['discovery_sources']),2);self.assertTrue(chain['discovery_sources'][1]['complete'])
        self.assertEqual(projected['chains'][1]['discovery_sources'],[])
        self.assertNotIn('SECRET-MARKER',json.dumps(projected))

    def test_legacy_balance_failure_count_is_safe_without_rewriting_snapshot(self):
        first=self.snapshot['coverage'][0]
        first['notes']=['4 candidate token balances could not be read.','SECRET-MARKER']
        for malformed in (None,-1,'SECRET-MARKER',True):
            with self.subTest(value=malformed):
                first['candidate_balance_errors']=malformed
                wallet=model.project_wallet(self.entry,self.snapshot,self.root)
                self.assertEqual(wallet['chains'][0]['candidate_balance_errors'],4)
                self.assertNotIn('SECRET-MARKER',json.dumps(wallet))

    def test_unreliable_pool_prices_are_excluded(self):
        w=model.project_wallet(self.entry,self.snapshot,self.root)
        nato=next(t for t in w['assets'] if t['symbol']=='NATO')
        self.assertIsNone(nato['value_usd']);self.assertEqual(nato['price']['quality'],'unreliable')
        china=next(t for t in w['assets'] if t['symbol']=='🇨🇳')
        self.assertIsNone(china['value_usd']);self.assertEqual(china['price']['quality'],'unfunded')
        self.assertGreater(w['known_value_usd'],3000);self.assertLess(w['known_value_usd'],5000)

    def test_shared_pool_uses_market_time_instead_of_balance_time(self):
        from details import project_details
        first=model.project_wallet(self.entry,self.snapshot,self.root)
        second=deepcopy(first);second['key']='second';second['address']='0x'+'2'*40
        for wallet,balance_time,market_time,liquidity in (
                (first,'2026-10-03T00:00:00Z','2026-10-05T00:00:00Z',200),
                (second,'2026-10-05T00:00:00Z','2026-10-03T00:00:00Z',100)):
            asset=wallet['assets'][0];asset['balance_observed_at']=balance_time
            asset['market_pools']=[{'url':'https://example.com/shared','observed_at':market_time,
                                   'liquidity_usd':liquidity}]
        token=next(t for t in project_details([first,second],self.root)['tokens']
                   if t['id']==first['assets'][0]['id'])
        self.assertEqual(len(token['market_pools']),1)
        self.assertEqual(token['market_pools'][0]['liquidity_usd'],200)
        second['assets'][0]['market_pools'][0]['observed_at']=None
        token=next(t for t in project_details([second,first],self.root)['tokens']
                   if t['id']==first['assets'][0]['id'])
        self.assertEqual(token['market_pools'][0]['liquidity_usd'],200)

    def test_pool_symbols_are_strings_and_empty_artwork_lookups_are_cached(self):
        raw=next(t for t in self.snapshot['tokens'] if t['symbol']=='NATO')
        raw['dex_pools'][0]['paired_tokens'][0]['symbol']=123
        asset=next(a for a in model.project_wallet(self.entry,self.snapshot,self.root)['assets'] if a['symbol']=='NATO')
        self.assertEqual(asset['market_pools'][0]['pair'][0]['symbol'],'?')
        address='0x'+'2'*40;calls=[]
        def fetch(url):calls.append(url);return []
        snapshots=[{'tokens':[{'chain_id':81457,'token_address':address}]}]
        token_images.refresh_catalog(snapshots,self.root,fetch=fetch)
        token_images.refresh_catalog(snapshots,self.root,fetch=fetch)
        self.assertEqual(len([u for u in calls if '/tokens/v1/blast/' in u]),1)

    def test_curve_price_uses_the_reserve_asset_price(self):
        w=model.project_wallet(self.entry,self.snapshot,self.root)
        chicken=next(t for t in w['assets'] if t['symbol']=='CHICKEN')
        leg=next(t for t in w['assets'] if t['symbol']=='LEG')
        token=next(t for t in self.snapshot['tokens'] if t['symbol']=='LEG')
        self.assertAlmostEqual(leg['price']['usd'],float(token['mintclub']['price_for_next_mint_in_reserve_token'])*chicken['price']['usd'])
        self.assertAlmostEqual(w['known_value_usd'],sum(t['value_usd'] or 0 for t in w['assets']))

    def quoted_token(self):
        token=next(t for t in self.snapshot['tokens'] if t['symbol']=='CHICKEN')
        token['balance_block_number']=123
        token['mintclub'].update({'block_number':123,'wallet_full_burn':{'net_refund':'0.02','gas_included':False}})
        return token

    def test_exit_proceeds_use_full_burn_not_spot_price(self):
        self.quoted_token()
        asset=next(t for t in model.project_wallet(self.entry,self.snapshot,self.root)['assets'] if t['symbol']=='CHICKEN')
        self.assertEqual(asset['value_usd'],2000)
        self.assertEqual(asset['exit_quote']['output_amount'],'0.02')
        self.assertEqual(asset['exit_quote']['output_address'],'0x4200000000000000000000000000000000000006')
        self.assertEqual(asset['exit_quote']['input_amount'],'1')
        self.assertTrue(asset['exit_quote']['royalty_included'])
        self.assertFalse(asset['exit_quote']['gas_included'])

    def test_exit_quote_requires_matching_balance_block_and_backing(self):
        token=self.quoted_token()
        token['balance_block_number']=124
        self.assertIsNone(model.exit_quote(token))
        token['balance_block_number']=123
        token['mintclub']['wallet_full_burn']['net_refund']='11'
        self.assertIsNone(model.exit_quote(token))
        token['mintclub']['wallet_full_burn']['net_refund']='NaN'
        self.assertIsNone(model.exit_quote(token))

    def test_exit_quote_keeps_zero_and_contract_identity(self):
        token=self.quoted_token()
        token['mintclub']['wallet_full_burn']['net_refund']='0'
        token['mintclub']['reserve_symbol']='USDC'
        token['mintclub']['reserve_token']='0x'+'9'*40
        quote=model.exit_quote(token)
        self.assertEqual(quote['output_amount'],'0')
        self.assertEqual(quote['output_address'],'0x'+'9'*40)
        self.assertNotIn('usd',quote)
        token['mintclub']['block_number']='123'
        token['balance_block_number']='123'
        self.assertEqual(model.exit_quote(token)['block_number'],'123')
        token['mintclub']['wallet_full_burn']['net_refund']='1e999999999'
        self.assertIsNone(model.exit_quote(token))

    def test_price_refresh_does_not_refresh_exit_quote(self):
        self.quoted_token()
        before=next(t for t in model.project_wallet(self.entry,self.snapshot,self.root)['assets'] if t['symbol']=='CHICKEN')
        (self.directory/'market-prices.json').write_text(json.dumps({'observed_at':'2026-10-04T06:00:00Z','tokens':[{'chain_id':8453,'address':before['address'],'usd':999,'basis':'Market index'}]}))
        after=next(t for t in model.project_wallet(self.entry,self.snapshot,self.root)['assets'] if t['symbol']=='CHICKEN')
        self.assertNotEqual(before['value_usd'],after['value_usd'])
        self.assertEqual(before['exit_quote'],after['exit_quote'])

    def test_testnet_balances_do_not_inflate_the_total(self):
        before=model.project_wallet(self.entry,self.snapshot,self.root)['known_value_usd']
        self.snapshot['coverage'].append({'chain_id':999,'name':'Fixture testnet','environment':'testnet','native_symbol':'ETH','native_balance':'1000','general_erc20_discovery':'indexer_checked','rpc_status':'available'})
        after=model.project_wallet(self.entry,self.snapshot,self.root)
        self.assertEqual(before,after['known_value_usd'])
        self.assertIsNone(next(a for a in after['assets'] if a['chain_id']==999)['value_usd'])

    def test_reserve_symbol_does_not_assign_an_unrelated_contract_price(self):
        chicken=next(t for t in self.snapshot['tokens'] if t['symbol']=='CHICKEN')
        chicken['mintclub']['reserve_token']='0x0000000000000000000000000000000000000004'
        w=model.project_wallet(self.entry,self.snapshot,self.root)
        self.assertIsNone(next(t for t in w['assets'] if t['symbol']=='CHICKEN')['value_usd'])

    def test_price_cache_and_registry_edits_change_the_state(self):
        a,_,etag1=model.load_state(self.root)
        (self.directory/'market-prices.json').write_text(json.dumps({'observed_at':'2026-10-03T06:00:00Z','native_usd':{'ETH':{'usd':3000}},'tokens':[]}))
        b,_,etag2=model.load_state(self.root)
        self.assertNotEqual(etag1,etag2);self.assertGreater(b['wallets'][0]['known_value_usd'],a['wallets'][0]['known_value_usd'])
        self.registry['wallets'][0]['tags'].append('Fixture tag')
        (self.root/'wallets.json').write_text(json.dumps(self.registry))
        c,_,etag3=model.load_state(self.root)
        self.assertNotEqual(etag2,etag3);self.assertIn('Fixture tag',c['wallets'][0]['tags'])

    def test_snapshot_path_and_identity_are_checked(self):
        with self.assertRaises(ValueError):model.within(self.root,'../.rpc.env')
        self.snapshot['wallet_address']='0x0000000000000000000000000000000000000000'
        (self.directory/'results.json').write_text(json.dumps(self.snapshot))
        with self.assertRaises(ValueError):model.load_state(self.root)

    def test_new_registered_wallet_is_included_without_viewer_edits(self):
        # Ephemeral fixture only. No entry is added to the operator's registry.
        address='0x0000000000000000000000000000000000000001'
        self.registry['wallets'].append({'address':address,'address_key':address,'tags':['Fixture wallet'],'latest_snapshot':None})
        (self.root/'wallets.json').write_text(json.dumps(self.registry))
        state,_,_=model.load_state(self.root)
        self.assertEqual(len(state['wallets']),2)
        self.assertEqual(state['wallets'][1]['name'],'Fixture wallet')
        self.assertEqual(state['wallets'][1]['status'],'awaiting_analysis')
        self.assertEqual(state['dashboard']['wallet_count'],2)
        self.assertEqual(state['dashboard']['analysed_wallet_count'],1)

    def test_dashboard_sums_positions_and_deduplicates_asset_identities(self):
        def asset(chain,address,value,environment='mainnet'):
            return {'id':f'{chain}:{address}','chain_id':chain,'symbol':'Fixture','name':'Fixture',
                'image_url':None,'environment':environment,'value_usd':value,
                'curve_reserve':{'amount':'1000000','symbol':'ETH'}}
        common=asset(8453,'same-contract',5)
        chains=[{'id':8453,'name':'Base'},{'id':1,'name':'Ethereum'},{'id':84532,'name':'Base Sepolia'}]
        first={'key':'first','analysed_at':'2026-10-03T01:00:00Z','prices_at':'2026-10-03T01:00:00Z',
            'chains':chains,'assets':[common,asset(1,'same-contract',None),asset(84532,'test-contract',9999,'testnet')]}
        second={**first,'key':'second','assets':[{**common,'value_usd':7}]}
        summary=model.dashboard([first,second])
        self.assertEqual(summary['known_value_usd'],12)
        self.assertEqual(summary['position_count'],3)
        self.assertEqual(summary['unique_asset_count'],2)
        self.assertEqual(summary['chain_count'],2)
        self.assertEqual(summary['unpriced_count'],1)
        self.assertEqual(summary['largest_holdings'][0]['wallet_count'],2)
        self.assertEqual(summary['largest_holdings'][0]['value_usd'],12)
        self.assertIsNone(next(c for c in summary['networks'] if c['id']==1)['value_usd'])
        self.assertIsNone(model.dashboard([])['known_value_usd'])

    def test_canonical_artwork_precedes_a_synthetic_reserve_fallback(self):
        address='0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
        key=token_images.identity(8453,address)
        catalog={'tokens':{key:{'image_url':token_images.reserve_logo(8453,address)}}}
        expected='https://static.alchemyapi.io/images/assets/3408.png'
        self.assertEqual(token_images.image_for({},8453,address),expected)
        self.assertEqual(token_images.image_for(catalog,8453,address),expected)
        self.assertIsNone(token_images.image_for(catalog,1,address))
        direct='https://coin-images.coingecko.com/updated-usdc.png'
        catalog['tokens'][key]['image_url']=direct
        self.assertEqual(token_images.image_for(catalog,8453,address),direct)

    def test_images_use_api_and_reserve_contract_identity(self):
        address='0x0000000000000000000000000000000000000001'
        url='https://coin-images.coingecko.com/fixture.png'
        catalog={'tokens':{f'8453:{address}':{'image_url':url}}}
        self.assertEqual(token_images.image_for(catalog,8453,address),url)
        self.assertIsNone(token_images.image_for(catalog,1,address))
        self.assertEqual(token_images.image_for(catalog,8453,address,mint=True),
                         url)
        self.assertEqual(token_images.image_for({},8453,address,mint=True),f'https://fc.hunt.town/tokens/logo/8453/{address}/image')
        self.assertIsNone(token_images.safe_image('https://tokens.1inch.io.evil.example/logo.png'))
        self.assertIsNone(token_images.safe_image('http://tokens.1inch.io/logo.png'))
        self.assertIsNone(token_images.safe_image('https://secret@mint.club/logo.png'))
        self.assertIsNone(token_images.mint_logo(8453,'not-an-address'))
        self.assertEqual(token_images.image_for({'tokens':{f'8453:{address}':{'image_url':'https://tokens.1inch.io/old.png'}}},8453,address),
            f'https://fc.hunt.town/tokens/logo/8453/{address}/image')
        (self.root/'cache').mkdir()
        (self.root/'cache/token-images.json').write_text(json.dumps(catalog))
        self.assertEqual(token_images.read_catalog(self.root),catalog)

    def test_native_artwork_uses_currency_identity_without_network_calls(self):
        catalog={'native':{'apecoin':{'image_url':'https://coin-images.coingecko.com/ape.png'}}}
        with patch.object(token_images,'fetch_metadata') as fetch:
            self.assertEqual(token_images.image_for(catalog,33139,native_symbol='APE'),'https://coin-images.coingecko.com/ape.png')
            self.assertIn('ethereum@2x.png',token_images.image_for(catalog,8453,native_symbol='ETH'))
            self.assertIn('bnb@2x.png',token_images.image_for(catalog,56,native_symbol='BNB'))
            self.assertIsNone(token_images.image_for(catalog,1,native_symbol='APE'))
            self.assertIsNone(token_images.image_for(catalog,33139,'0x'+'1'*40))
            fetch.assert_not_called()

    def test_mint_metadata_uses_checksum_with_lowercase_catalog_identity(self):
        address='0x52908400098527886e0f7030069857d2e4169ee7'
        checksum='0x52908400098527886E0F7030069857D2E4169EE7'
        reserve='0x'+'2'*40
        source=f'https://mint.club/api/tokens/details/8453/{checksum}'
        requests=[]
        def fetch(url):
            requests.append(url)
            if url==source:return {'chainId':8453,'tokenAddress':checksum,
                'reserveToken':{'chainId':8453,'tokenAddress':reserve,'logo':'https://mint.club/reserve.png'}}
            return []
        token_images.refresh_catalog([{'tokens':[{'chain_id':8453,'token_address':address,'mintclub':{'reserve_token':reserve}}]}],self.root,fetch=fetch)
        catalog=token_images.read_catalog(self.root)
        self.assertIn(source,requests)
        self.assertIn('8453:'+address,catalog['mint_details'])
        self.assertEqual(token_images.image_for(catalog,8453,reserve),'https://mint.club/reserve.png')

    def test_contract_scoped_lp_and_dex_artwork_preserves_cache_on_failure(self):
        address='0x'+'1'*40;other='0x'+'2'*40
        image='https://cdn.dexscreener.com/cms/images/fixture'
        snapshots=[{'tokens':[{'chain_id':4663,'token_address':address},
                              {'chain_id':81457,'token_address':other}]}]
        calls=[]
        def fetch(source):
            calls.append(source)
            if source==token_images.LP_CATALOG:
                return {'items':[{'chain':{'id':1},'token':{'address':address,'imageUrl':image}},
                                 {'chain':{'id':4663},'token':{'address':address,'imageUrl':image}}]}
            if '/tokens/v1/blast/' in source:
                return [{'chainId':'base','baseToken':{'address':other},'info':{'imageUrl':image}},
                        {'chainId':'blast','baseToken':{'address':other},'info':{'imageUrl':'https://evil.example/logo.png'}}]
            return None
        token_images.refresh_catalog(snapshots,self.root,fetch=fetch)
        catalog=token_images.read_catalog(self.root)
        self.assertEqual(token_images.image_for(catalog,4663,address),image)
        self.assertIsNone(token_images.image_for(catalog,1,address))
        self.assertIsNone(token_images.image_for(catalog,81457,other))
        self.assertTrue(any('/tokens/v1/blast/' in source for source in calls))
        token_images.refresh_catalog(snapshots,self.root,force=True,fetch=lambda _:None)
        self.assertEqual(token_images.image_for(token_images.read_catalog(self.root),4663,address),image)
        self.assertIsNone(token_images.safe_image('https://cdn.dexscreener.com.evil.example/image'))
        self.assertIsNotNone(token_images.image_for({},81457,'0xb1a5700fa2358173fe465e6ea4ff52e36e88e2ad'))
        self.assertIsNone(token_images.image_for({},1,'0xb1a5700fa2358173fe465e6ea4ff52e36e88e2ad'))

    def test_native_usd_projection_rejects_unknown_and_mismatched_chains(self):
        self.snapshot['tokens']=[]
        self.snapshot['price_references']={'APE_USD':{'value':2}}
        self.snapshot['coverage']=[{'chain_id':cid,'name':'Synthetic '+str(cid),'environment':'mainnet',
            'native_symbol':'APE','native_balance':'100','general_erc20_discovery':'incomplete','rpc_status':'available'}
            for cid in (33139,999999,1)]
        wallet=model.project_wallet(self.entry,self.snapshot,self.root)
        self.assertEqual(wallet['known_value_usd'],200)
        for asset in wallet['assets']:
            if asset['chain_id']==33139:self.assertEqual(asset['value_usd'],200)
            else:self.assertIsNone(asset['value_usd']);self.assertIsNone(asset['price'])

    def test_unpriced_wallet_and_network_totals_are_unknown(self):
        self.snapshot['tokens']=[];self.snapshot['price_references']={}
        wallet=model.project_wallet(self.entry,self.snapshot,self.root)
        self.assertTrue(wallet['assets'])
        self.assertTrue(all(asset['value_usd'] is None for asset in wallet['assets']))
        self.assertIsNone(wallet['known_value_usd'])
        self.assertTrue(all(chain['value_usd'] is None for chain in wallet['chains']))

    def test_retained_curve_quote_is_not_rederived_with_a_new_reserve_price(self):
        token=next(t for t in self.snapshot['tokens'] if t.get('mintclub'))
        old={'chain_id':token['chain_id'],'address':token['token_address'],'usd':100,'basis':'Curve spot',
             'quality':'estimated','observed_at':'2026-10-01T00:00:00Z','retained_from_previous':True}
        (self.directory/'market-prices.json').write_text(json.dumps({'native_usd':{'ETH':{'usd':9999}},'tokens':[old]}))
        wallet=model.project_wallet(self.entry,self.snapshot,self.root)
        asset=next(a for a in wallet['assets'] if a['address']==token['token_address'])
        self.assertEqual(asset['price'],old)

    def test_fresh_negative_price_evidence_overrides_old_funded_snapshot(self):
        token=next(t for t in self.snapshot['tokens'] if t.get('mintclub'))
        self.assertTrue(token['mintclub']['funded'])
        for quality in ('unfunded','unreliable'):
            with self.subTest(quality=quality):
                current={'chain_id':token['chain_id'],'address':token['token_address'],'usd':None,
                         'basis':'Curve spot','quality':quality,'observed_at':'2026-10-04T12:00:00Z'}
                (self.directory/'market-prices.json').write_text(json.dumps({'tokens':[current]}))
                wallet=model.project_wallet(self.entry,self.snapshot,self.root)
                asset=next(a for a in wallet['assets'] if a['address']==token['token_address'])
                self.assertIsNone(asset['value_usd']);self.assertEqual(asset['price'],current)

    def test_failed_image_metadata_refresh_preserves_existing_catalog(self):
        address='0x0000000000000000000000000000000000000001'
        url='https://coin-images.coingecko.com/fixture.png'
        cache=self.root/'cache/token-images.json';cache.parent.mkdir()
        cache.write_text(json.dumps({'tokens':{f'8453:{address}':{'image_url':url}}}))
        wrong={'chainId':1,'tokenAddress':address,'reserveToken':{'chainId':8453,'tokenAddress':address,'logo':url}}
        snapshot={'tokens':[{'chain_id':8453,'token_address':address,'mintclub':{'reserve_token':address}}]}
        result=token_images.refresh_catalog([snapshot],self.root,force=True,fetch=lambda source:wrong if '/details/' in source else None)
        self.assertEqual(result['provider_errors'],4)
        catalog=token_images.read_catalog(self.root)
        self.assertEqual(token_images.image_for(catalog,8453,address),url)
        self.assertNotIn(f'8453:{address}',catalog['mint_details'])

    def test_recorded_market_artwork_survives_provider_failure_without_duplicate_lookup(self):
        address='0x'+'1'*40;other='0x'+'2'*40
        image='https://cdn.dexscreener.com/cms/images/recorded'
        observed='2026-10-17T01:00:00+00:00'
        snapshot={'tokens':[{'chain_id':56,'token_address':address,'mintclub':None}]}
        pairs=[{'chainId':'bsc','baseToken':{'address':address},'info':{'imageUrl':image}},
               {'chainId':'ethereum','baseToken':{'address':address},'info':{'imageUrl':image}},
               {'chainId':'bsc','baseToken':{'address':other},'info':{'imageUrl':image}}]
        calls=[]
        def failed(source):
            calls.append(source)
            raise OSError('Optional metadata provider unavailable.')
        from datetime import datetime,timezone
        with patch('token_images.datetime') as clock:
            clock.now.return_value=datetime(2026,10,17,1,1,tzinfo=timezone.utc)
            clock.fromisoformat.side_effect=datetime.fromisoformat
            result=token_images.refresh_catalog([snapshot],self.root,fetch=failed,market_metadata=[
                {'source':'https://api.dexscreener.com/tokens/v1/bsc/'+address,'observed_at':observed,'response':pairs}])
        catalog=token_images.read_catalog(self.root)
        self.assertEqual(token_images.image_for(catalog,56,address),image)
        self.assertEqual(catalog['tokens']['56:'+address]['observed_at'],observed)
        self.assertIsNone(token_images.image_for(catalog,1,address))
        self.assertIsNone(token_images.image_for(catalog,56,other))
        self.assertFalse(any('/tokens/v1/' in source for source in calls))
        self.assertGreater(result['provider_errors'],0)

    def test_image_metadata_updates_etag_without_changing_balances_or_values(self):
        before,_,etag_before=model.load_state(self.root)
        token=next(t for t in self.snapshot['tokens'] if t['symbol']=='HEX')
        key=f"{token['chain_id']}:{token['token_address'].lower()}"
        url='https://coin-images.coingecko.com/fixture.png'
        path=self.root/'cache/token-images.json';path.parent.mkdir()
        path.write_text(json.dumps({'tokens':{key:{'image_url':url}}}))
        after,_,etag_after=model.load_state(self.root)
        self.assertNotEqual(etag_before,etag_after)
        self.assertEqual(before['dashboard']['known_value_usd'],after['dashboard']['known_value_usd'])
        self.assertEqual(next(t for t in after['wallets'][0]['assets'] if t['id']==key)['image_url'],url)

    def test_price_records_are_separate_per_chain(self):
        hex_token=next(t for t in self.snapshot['tokens'] if t['symbol']=='HEX')
        (self.directory/'market-prices.json').write_text(json.dumps({'tokens':[{'chain_id':1,'address':hex_token['token_address'],'usd':7,'basis':'DEX market','quality':'estimated','liquidity_usd':10000}]}))
        w=model.project_wallet(self.entry,self.snapshot,self.root)
        self.assertEqual(next(t for t in w['assets'] if t['symbol']=='HEX')['value_usd'],7)

    def test_http_etag_and_private_files(self):
        with patch.object(server,'ROOT',self.root), patch.object(server,'load_state',lambda:model.load_state(self.root)), patch.object(server,'last_good',None):
            app=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            thread=threading.Thread(target=app.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{app.server_port}'
            try:
                with urllib.request.urlopen(base+'/api/state') as r:
                    self.assertEqual(r.status,200);etag=r.headers['ETag'];self.assertIn('wallets',json.load(r))
                    self.assertIn('https://mint.club',r.headers['Content-Security-Policy'])
                    self.assertIn("connect-src 'self'",r.headers['Content-Security-Policy'])
                    self.assertIn("img-src 'self' data:",r.headers['Content-Security-Policy'])
                    self.assertIn("script-src 'self';",r.headers['Content-Security-Policy'])
                with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(urllib.request.Request(base+'/api/state',headers={'If-None-Match':etag}))
                self.assertEqual(e.exception.code,304)
                e.exception.close()
                for path in ['/.rpc.env','/../.rpc.env','/wallets.json','/api/report/unknown']:
                    with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(base+path)
                    self.assertEqual(e.exception.code,404)
                    e.exception.close()
                with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(urllib.request.Request(base+'/api/state',data=b'{}'))
                self.assertEqual(e.exception.code,501)
                e.exception.close()
                for name in ('mintclub.png','uniswap.svg','aerodrome.svg'):
                    with urllib.request.urlopen(base+'/venues/'+name) as r:
                        self.assertEqual(r.status,200);self.assertGreater(len(r.read()),100)
                for name in ('etherscan.png',):
                    with urllib.request.urlopen(base+'/explorers/'+name) as r:
                        self.assertEqual(r.headers['Content-Type'],'image/png')
                        self.assertTrue(r.read().startswith(b'\x89PNG'))
                with urllib.request.urlopen(base+'/ows-logo.svg') as r:
                    self.assertEqual(r.headers['Content-Type'],'image/svg+xml')
                    self.assertIn(b'<svg',r.read())
            finally:app.shutdown();app.server_close();thread.join()

def fixture_snapshot():
    """Synthetic positions. Never load the operator portfolio into release tests."""
    stamp='2026-10-03T00:00:00Z';weth='0x4200000000000000000000000000000000000006'
    def token(index,symbol,chain=8453,balance='1'):
        return {'chain_id':chain,'token_address':'0x'+f'{index:040x}','symbol':symbol,'name':symbol,
            'wallet_balance':balance,'mintclub':None,'dex_pools':[],'indexer_price_references':[]}
    def curve(reserve,symbol,price='1',funded=True):
        return {'reserve_token':reserve,'reserve_symbol':symbol,'price_for_next_mint_in_reserve_token':price,
            'reserve_balance':'10','funded':funded,'observed_at':stamp,'source_url':'https://mint.club/token/base/fixture'}
    chicken=token(3,'CHICKEN');chicken['mintclub']=curve(weth,'WETH')
    leg=token(4,'LEG',balance='2');leg['mintclub']=curve(chicken['token_address'],'CHICKEN','0.25')
    china=token(5,'🇨🇳');china['mintclub']=curve(weth,'WETH',funded=False)
    nato=token(6,'NATO',chain=1);nato['dex_pools']=[{'paired_tokens':[{'address':nato['token_address']},{'address':weth}],
        'reported_price_usd':'100','reported_liquidity':{'usd':10000,'base':100},'venue':'Uniswap',
        'source_url':'https://example.com/pool'}]
    hex_token=token(7,'HEX',chain=1);hex_token['indexer_price_references']=[{'currency':'usd','value':'0.5'}]
    return {'wallet_address':'0x'+'1'*40,'compiled_at':stamp,'status':'completed_with_coverage_gaps','counts':{},
        'tokens':[chicken,leg,china,nato,hex_token],'price_references':{'ETH_USD':{'value':'2000','observed_at':stamp}},
        'coverage':[{'chain_id':chain,'name':name,'environment':'mainnet','native_symbol':'ETH',
            'native_balance':'0.25' if chain==8453 else '0','general_erc20_discovery':'indexer_checked','rpc_status':'available'}
            for chain,name in [(8453,'Base'),(1,'Ethereum')]]}

if __name__=='__main__':unittest.main()
