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

    def test_unreliable_pool_prices_are_excluded(self):
        w=model.project_wallet(self.entry,self.snapshot,self.root)
        nato=next(t for t in w['assets'] if t['symbol']=='NATO')
        self.assertIsNone(nato['value_usd']);self.assertEqual(nato['price']['quality'],'unreliable')
        china=next(t for t in w['assets'] if t['symbol']=='🇨🇳')
        self.assertIsNone(china['value_usd']);self.assertEqual(china['price']['quality'],'unfunded')
        self.assertGreater(w['known_value_usd'],3000);self.assertLess(w['known_value_usd'],5000)

    def test_curve_price_uses_the_reserve_asset_price(self):
        w=model.project_wallet(self.entry,self.snapshot,self.root)
        chicken=next(t for t in w['assets'] if t['symbol']=='CHICKEN')
        leg=next(t for t in w['assets'] if t['symbol']=='LEG')
        token=next(t for t in self.snapshot['tokens'] if t['symbol']=='LEG')
        self.assertAlmostEqual(leg['price']['usd'],float(token['mintclub']['price_for_next_mint_in_reserve_token'])*chicken['price']['usd'])
        self.assertAlmostEqual(w['known_value_usd'],sum(t['value_usd'] or 0 for t in w['assets']))

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

    def test_images_use_api_and_reserve_contract_identity(self):
        address='0x0000000000000000000000000000000000000001'
        url='https://coin-images.coingecko.com/fixture.png'
        catalog={'tokens':{f'8453:{address}':{'image_url':url}}}
        self.assertEqual(token_images.image_for(catalog,8453,address),url)
        self.assertIsNone(token_images.image_for(catalog,1,address))
        self.assertIn('/tokens/logo?chainId=8453&address=',token_images.image_for(catalog,8453,address,mint=True))
        self.assertIsNone(token_images.safe_image('https://tokens.1inch.io.evil.example/logo.png'))
        self.assertIsNone(token_images.safe_image('http://tokens.1inch.io/logo.png'))
        self.assertIsNone(token_images.safe_image('https://secret@mint.club/logo.png'))
        self.assertIsNone(token_images.mint_logo(8453,'not-an-address'))
        self.assertEqual(token_images.image_for({'tokens':{f'8453:{address}':{'image_url':'https://tokens.1inch.io/old.png'}}},8453,address),
            f'https://fc.hunt.town/tokens/logo/8453/{address}/image')
        (self.root/'cache').mkdir()
        (self.root/'cache/token-images.json').write_text(json.dumps(catalog))
        self.assertEqual(token_images.read_catalog(self.root),catalog)

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
        (self.directory/'market-prices.json').write_text(json.dumps({'tokens':[{'chain_id':1,'address':hex_token['token_address'],'usd':7,'basis':'DEX market','quality':'estimated'}]}))
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
