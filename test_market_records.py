"""Market identities and canonical links, independent from price eligibility."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wallet
sys.path.insert(0,str(Path(__file__).parent/'viewer'))
from model import project_wallet
from test_viewer import fixture_snapshot

# Public pool identities from the official Uniswap Pools pages. Wallets are synthetic.
V3='0x37428B026d346A0a938d900B5d29C2be3DE31086'
V4='0x22450156cceafc0e944916c26cb310ecbc56694d47720f32911ae00361ba2f8a'

class MarketRecordsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.folder=self.root/'snapshots/demo';self.folder.mkdir(parents=True)
        self.snapshot=fixture_snapshot();self.token=self.snapshot['tokens'][0]
        self.token.update(symbol='PLOT',token_type='ERC20')
        self.token['mintclub']['source_url']='https://mint.club/token/base/'+self.token['token_address']
        self.entry={'address':self.snapshot['wallet_address'],'address_key':self.snapshot['wallet_address'],
                    'tags':['Fixture'],'latest_snapshot':{'directory':'snapshots/demo'}}

    def project(self):
        return next(a for a in project_wallet(self.entry,self.snapshot,self.root)['assets'] if a['id']=='8453:'+self.token['token_address'])

    def test_canonical_plot_and_nft_links_do_not_rewrite_saved_evidence(self):
        for symbol,kind,path in [('PLOT','ERC20','token/base/PLOT'),('MINIBD','ERC1155','nft/base/MINIBD'),('A/B #?','ERC20','token/base/A%2FB%20%23%3F')]:
            self.token.update(symbol=symbol,token_type=kind)
            before=copy.deepcopy(self.snapshot);asset=self.project()
            self.assertEqual(asset['links'][0]['url'],'https://mint.club/'+path)
            self.assertEqual(asset['price']['source'],'https://mint.club/'+path)
            self.assertEqual(self.snapshot,before)

    def test_successful_price_batch_is_not_repeated_only_for_missing_artwork(self):
        from token_images import refresh_catalog
        from datetime import datetime,timezone
        address=self.token['token_address'];cache=self.root/'cache';cache.mkdir()
        (cache/'token-images.json').write_text(json.dumps({'tokens':{},'reserve_catalog_at':datetime.now(timezone.utc).isoformat()}))
        snapshot={'tokens':[{'chain_id':8453,'token_address':address}]}
        source='https://api.dexscreener.com/tokens/v1/base/'+address
        with patch('token_images.checksum_addresses',return_value={}),patch('token_images.fetch_metadata') as fetch:
            refresh_catalog([snapshot],self.root,market_metadata=[{'source':source,'response':[]}],fetch=fetch)
        fetch.assert_not_called()

    def pairs(self):
        return [{'chainId':'base','dexId':'uniswap','pairAddress':pool,'labels':[version],
                 'baseToken':{'address':'0x'+'2'*40,'symbol':'USDC'},
                 'quoteToken':{'address':self.token['token_address'],'symbol':'RM'},
                 'priceUsd':'1','liquidity':None,'url':'https://app.uniswap.org/explore/pools/base/'+pool}
                for pool,version in [(V3,'v3'),(V4,'v4')]]

    def test_basic_lookup_attaches_both_rm_pool_identifiers_on_quote_side(self):
        self.token.update(symbol='RM',mintclub=None)
        self.snapshot['tokens']=[self.token]
        with patch.object(wallet,'fetch',return_value=self.pairs()),patch.object(wallet,'event'),patch('token_images.refresh_catalog',return_value={}):
            market=wallet.refresh_metadata(self.snapshot,{'tokens':[]},self.folder,discover_prices=True)
        pools=next(m for m in market['markets'] if m['id']=='8453:'+self.token['token_address'])['pools']
        self.assertEqual({p['pool'].lower() for p in pools},{V3.lower(),V4})
        (self.folder/'market-prices.json').write_text(json.dumps(market))
        asset=self.project()
        self.assertEqual(len(asset['market_pools']),2)
        self.assertIsNone(asset['value_usd'],'Pool visibility must not price the quote asset as the base asset')

    def test_projection_retains_pool_versions_without_liquidity_or_price(self):
        self.token.update(symbol='RM',mintclub=None)
        pools=[wallet.pool_row(p,'2026-10-19T00:00:00Z') for p in self.pairs()]
        (self.folder/'market-prices.json').write_text(json.dumps({'markets':[{'id':'8453:'+self.token['token_address'],'pools':pools}]}))
        asset=self.project()
        self.assertEqual({p['pool'].lower() for p in asset['market_pools']},{V3.lower(),V4})
        self.assertEqual({tuple(p['version_labels']) for p in asset['market_pools']},{('v3',),('v4',)})
        self.assertIsNone(asset['value_usd'])

    def test_venue_destinations_preserve_source_evidence_and_full_v4_id(self):
        from market_records import market_url
        for identity,venue,expected in [
            (V3,'uniswap','https://app.uniswap.org/explore/pools/base/'+V3),
            (V4,'uniswap','https://app.uniswap.org/explore/pools/base/'+V4),
            (V3,'aerodrome','https://aerodrome.finance/pools?token0=0x'+'2'*40+'&token1='+self.token['token_address']+'&chain=8453&chain0=8453&chain1=8453')]:
            pool=wallet.pool_row(self.pairs()[0],'2026-10-19T00:00:00Z')
            pool.update(pool=identity,venue=venue,source_url='https://dexscreener.com/base/'+identity)
            before=copy.deepcopy(pool)
            self.assertEqual(market_url(8453,pool),expected)
            self.assertEqual(market_url(999999,pool),pool['source_url'])
            self.assertEqual(market_url(8453,{**pool,'pool':'bad/route'}),pool['source_url'])
            self.token['dex_pools']=[pool]
            asset=self.project();projected=asset['market_pools'][0]
            self.assertEqual(projected['url'],expected)
            self.assertEqual(projected['source_url'],pool['source_url'])
            self.assertEqual(pool,before)
        self.assertEqual(market_url(8453,{**pool,'venue':'unknown'}),pool['source_url'])
        self.assertEqual(market_url(8453,{**pool,'paired_tokens':[]}),pool['source_url'])

if __name__=='__main__':unittest.main()
