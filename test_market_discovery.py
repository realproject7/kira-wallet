"""Alternate market source failures, pagination and identity boundaries."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from market_discovery import discover, uniswap_query, uniswap_records
from market_records import collected_markets,merge_pools
from test_market_records import V3,V4

class MarketDiscoveryTests(unittest.TestCase):
    def test_official_pools_keep_ids_fees_and_native_members_without_creating_prices(self):
        address='0x'+'1'*40
        _,aliases=uniswap_query([{'chain_id':8453,'token_address':address}])
        def row(pool):return {'address':pool,'poolId':pool,'feeTier':180000,'totalLiquidity':{'currency':'USD','value':500},'token0':{'address':None,'symbol':'ETH'},'token1':{'address':address,'symbol':'RM'}}
        response={'data':{'t0_v2':[],'t0_v3':None,'t0_v4':[row(V4)]},'errors':[{'path':['t0_v3'],'errorType':'ExternalAPIError'}]}
        record,cursors=uniswap_records(response,aliases,'2026-10-19T00:00:00Z')
        self.assertEqual(record['query_status'][f'8453:{address}:v3'],'unavailable')
        pools=collected_markets([record],{8453:'base'},{(8453,address)})[0]['pools']
        self.assertEqual(pools[0]['pool'],V4);self.assertEqual(pools[0]['pool_kind'],'pool_id')
        self.assertEqual(pools[0]['fee_bps'],1800);self.assertIsNone(pools[0]['reported_price_usd'])
        bad={**row(V4),'token1':{'address':'0x'+'2'*40}}
        empty,_=uniswap_records({'data':{'t0_v4':[bad]}},aliases,None)
        self.assertEqual(empty['response'],[])

    def test_failed_source_keeps_prior_markets_and_never_proves_no_pools(self):
        address='0x'+'1'*40
        snapshot={'coverage':[{'chain_id':8453,'environment':'mainnet'}],'tokens':[{'chain_id':8453,'token_address':address,'token_type':'ERC20','mintclub':{'funded':True}}]}
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            from wallet import atomic
            old={'id':'8453:'+address,'pools':[{'pool':V3,'venue':'uniswap','version_labels':['v3'],'source_url':'https://example.com/pool'}]}
            atomic(folder/'supplemental-markets.json',{'markets':[old]})
            result=discover(snapshot,folder,fetch=lambda *a,**k:{'transport_error':{'status':403}},factories=False)
            self.assertEqual(result['markets'],[old]);self.assertEqual(result['status'],'partial')
            self.assertTrue(all(status=='unavailable' for status in result['query_status'].values()))

    def test_fresh_market_union_retains_old_prices_when_only_factory_metadata_arrives(self):
        old={'pool':V3,'venue':'uniswap','version_labels':['v3'],'reported_liquidity':{'usd':5000},'reported_price_usd':'2','observed_at':'2026-10-01','source_url':'https://example.com/pool'}
        factory={'pool':V3.lower(),'venue':'uniswap','version_labels':['v3'],'reported_liquidity':None,'observed_at':'2026-10-19','factory_discovery':{'block_number':'123'}}
        merged=merge_pools([old],[factory]);self.assertEqual(len(merged),1)
        self.assertEqual(merged[0]['observed_at'],'2026-10-01');self.assertEqual(merged[0]['reported_price_usd'],'2')
        self.assertEqual(merged[0]['factory_discovery'],{'block_number':'123'})
        self.assertEqual(len(merge_pools([old],[{**factory,'venue':'other'}])),2)

    def test_full_pages_continue_with_source_cursor_and_stop_on_no_progress(self):
        address='0x'+'1'*40;token={'chain_id':8453,'token_address':address,'token_type':'ERC20','mintclub':{'funded':True}}
        row={'poolId':V4,'token0':{'address':address,'symbol':'RM'},'token1':{'address':None,'symbol':'ETH'},'totalLiquidity':{'value':1,'currency':'USD'}}
        response={'data':{'t0_v2':[],'t0_v3':[],'t0_v4':[row]*50}}
        calls=[]
        def fetch(url,body,**kwargs):calls.append(body);return response
        with tempfile.TemporaryDirectory() as temp:
            result=discover({'tokens':[token],'coverage':[{'chain_id':8453,'environment':'mainnet'}]},Path(temp),fetch=fetch,factories=False)
        self.assertEqual(len(calls),2);self.assertIn('tvlCursor:1',calls[1]['query'])
        self.assertEqual(result['status'],'partial')
        self.assertEqual(len(result['markets'][0]['pools']),1)

if __name__=='__main__':unittest.main()
