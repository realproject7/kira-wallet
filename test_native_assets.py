"""Public native pricing must not depend on a wallet indexer or symbol search."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import contextlib
import io
import json
import os
import runpy
import sys
import tempfile
import unittest
from types import SimpleNamespace

from native_assets import market_metadata, native_identity


class NativeMarketTests(unittest.TestCase):
    observed = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)
    coverage = [dict(chain_id=chain, native_symbol=symbol, environment='mainnet', native_balance='1')
                for chain, symbol in ((8453, 'ETH'), (33139, 'APE'), (56, 'BNB'))]

    def row(self, asset='apecoin', symbol='ape', **extra):
        return {'id': asset, 'symbol': symbol, 'current_price': 2,
                'last_updated': self.observed.isoformat(),
                'image': 'https://coin-images.coingecko.com/fixture.png', **extra}

    def test_explicit_chain_identity_and_one_public_batch(self):
        rows = [self.row(), self.row('ethereum', 'eth'), self.row('binancecoin', 'bnb'),
                self.row('unrelated', 'ape', current_price=999)]
        with patch('research.fetch', return_value=rows) as fetch:
            result = market_metadata(self.coverage, observed=self.observed)
        self.assertEqual(set(result['prices']), {'ETH_USD', 'APE_USD', 'BNB_USD'})
        fetch.assert_called_once()
        self.assertIn('ids=apecoin%2Cbinancecoin%2Cethereum', fetch.call_args.args[0])
        self.assertNotIn('address', fetch.call_args.args[0])
        self.assertEqual(native_identity(33139, 'APE'), 'apecoin')
        self.assertIsNone(native_identity(1, 'APE'))
        self.assertIsNone(native_identity(33139, 'ETH'))

    def test_invalid_stale_future_and_unmatched_quotes_stay_unknown(self):
        rows = [self.row(last_updated=(self.observed-timedelta(hours=2)).isoformat()),
                self.row(last_updated=(self.observed+timedelta(hours=1)).isoformat()),
                self.row(current_price=float('nan')), self.row(current_price=-1),
                self.row(current_price=True), self.row(last_updated=None),
                self.row(symbol='unrelated'), self.row(symbol=7)]
        result = market_metadata(self.coverage, fetch=lambda _:rows, observed=self.observed)
        self.assertEqual(result['prices'], {})
        result = market_metadata(self.coverage, fetch=lambda _:{'transport_error': {'status':429}}, observed=self.observed)
        self.assertEqual(result['prices'], {})

    def test_malformed_identity_does_not_abort_other_native_records(self):
        rows=[self.row(id=[]),self.row(id={'coin':'apecoin'}),self.row()]
        result=market_metadata(self.coverage,fetch=lambda _:rows,observed=self.observed)
        self.assertEqual(set(result['prices']),{'APE_USD'})
        self.assertIsNone(native_identity([], 'APE'))
        self.assertIsNone(native_identity(True, 'ETH'))

    def test_testnets_and_unknown_chains_do_not_create_market_requests(self):
        coverage = [{**self.coverage[0], 'environment':'testnet'},
                    {**self.coverage[1], 'chain_id':999999}]
        with patch('research.fetch') as fetch:
            self.assertEqual(market_metadata(coverage)['prices'], {})
        fetch.assert_not_called()

    def run_price_job(self, rows, *, dex=None, previous=None, images_error=None, tokens=None, rpc_tokens=None):
        import research
        sys.path.insert(0, str(Path(__file__).parent/'viewer'))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();folder=root/'snapshots/fixture';folder.mkdir(parents=True)
            address='0x'+'1'*40
            snapshot={'wallet_address':address,'tokens':tokens or [],'coverage':self.coverage,'price_references':{}}
            original=json.dumps(snapshot);(folder/'results.json').write_text(original)
            if previous is not None:(folder/'market-prices.json').write_text(json.dumps(previous))
            (root/'wallets.json').write_text(json.dumps({'wallets':[{'address':address,'address_key':address,
                'tags':['Fixture'],'latest_snapshot':{'directory':'snapshots/fixture','result':'snapshots/fixture/results.json'}}]}))
            def fetch(source, *args, **kwargs):return rows if '/coins/markets?' in source else dex or []
            error=None;real_fdopen=os.fdopen
            with (root/'.analysis.lock').open('a') as lock,\
                 patch.object(research,'ROOT',root),patch.object(research,'fetch',side_effect=fetch),\
                 patch('subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps({'tokens':rpc_tokens or [],'errors':[]}))),\
                 patch('curve_pricing.enrich',side_effect=lambda snapshot,market,folder:market),\
                 patch('token_images.refresh_catalog',return_value={},side_effect=images_error) as images,\
                 patch.object(sys,'argv',['refresh_prices.py','--wallet','Fixture']),\
                 patch.dict(os.environ,{'KIRA_JOB_SNAPSHOT':'snapshots/job-fixture','KIRA_ANALYSIS_FD':'123456'}),\
                 patch('os.fdopen',side_effect=lambda fd,*args,**kwargs:lock if fd==123456 else real_fdopen(fd,*args,**kwargs)),contextlib.redirect_stdout(io.StringIO()):
                try:runpy.run_path(str(Path(__file__).parent/'viewer/refresh_prices.py'))
                except SystemExit as failure:error=str(failure)
            market=folder/'market-prices.json';overlay=root/'snapshots/job-fixture/prices.json'
            self.assertEqual((folder/'results.json').read_text(),original)
            return (json.loads(market.read_text()) if market.exists() else None,
                    json.loads(overlay.read_text()) if overlay.exists() else None,images.call_args,error)

    def fresh_rows(self):
        return [self.row(asset,symbol,last_updated=datetime.now(timezone.utc).isoformat())
                for asset,symbol in [('apecoin','ape'),('ethereum','eth'),('binancecoin','bnb')]]

    def test_price_job_repairs_native_quotes_without_changing_balances(self):
        rows=self.fresh_rows();market,overlay,images,error=self.run_price_job(rows)
        self.assertIsNone(error)
        self.assertEqual(set(market['native_usd']),{'ETH','APE','BNB'})
        self.assertEqual(market['native_usd']['APE']['asset_id'],'apecoin')
        self.assertEqual(images.kwargs['native_images']['apecoin']['image_url'],rows[0]['image'])
        self.assertEqual(overlay['job_result_status'],'completed')

    def test_existing_dex_eth_source_takes_priority(self):
        dex=[{'chainId':'base','baseToken':{'address':'0x4200000000000000000000000000000000000006'},
              'quoteToken':{'address':'0x'+'2'*40},'priceUsd':'3','liquidity':{'usd':1000,'base':100},
              'url':'https://dexscreener.com/base/fixture'}]
        market,overlay,_,error=self.run_price_job(self.fresh_rows(),dex=dex)
        self.assertIsNone(error)
        self.assertEqual(market['native_usd']['ETH']['usd'],3)
        self.assertEqual(market['native_usd']['ETH']['basis'],'DEX market')
        self.assertEqual(market['native_usd']['ETH']['source'],'https://dexscreener.com/base/fixture')
        self.assertEqual(market['native_usd']['APE']['usd'],2)
        self.assertEqual(overlay['job_result_status'],'completed')

    def test_provider_failure_keeps_previous_prices_and_timestamp(self):
        old={'native_usd':{'ETH':{'usd':1000,'observed_at':'2026-10-01T00:00:00Z'}}}
        market,overlay,_,error=self.run_price_job({'transport_error':{'status':429}},previous=old)
        self.assertIsNotNone(error)
        self.assertEqual(market,old)
        self.assertIsNone(overlay)

    def test_image_cache_failure_does_not_block_valid_price_publication(self):
        market,overlay,_,error=self.run_price_job(self.fresh_rows(),images_error=OSError('fixture'))
        self.assertIsNone(error)
        self.assertEqual(market['image_refresh_status'],'unavailable')
        self.assertEqual(overlay['job_result_status'],'completed')

    def test_partial_provider_success_preserves_older_token_quote(self):
        token={'chain_id':8453,'token_address':'0x'+'2'*40,'dex_pools':[],
               'mintclub':{'reserve_token':'0x4200000000000000000000000000000000000006','reserve_symbol':'WETH'}}
        old_price={'chain_id':8453,'address':token['token_address'],'usd':100,'basis':'Curve spot',
                   'quality':'estimated','observed_at':'2026-10-01T00:00:00Z'}
        old={'native_usd':{'ETH':{'usd':1000,'observed_at':old_price['observed_at']}},'tokens':[old_price]}
        rpc={'chain_id':8453,'address':token['token_address'],'price_in_weth':1,'basis':'Curve spot'}
        market,overlay,_,error=self.run_price_job(self.fresh_rows()[:1],previous=old,tokens=[token],rpc_tokens=[rpc])
        self.assertIsNone(error)
        preserved=next(p for p in market['tokens'] if p['address']==token['token_address'])
        self.assertEqual(preserved,{**old_price,'retained_from_previous':True})
        self.assertEqual(market['native_usd']['ETH'],old['native_usd']['ETH'])
        self.assertEqual(overlay['job_result_status'],'completed_with_coverage_gaps')
        self.assertEqual(market['retained_price_records'],1)

    def test_fresh_negative_evidence_invalidates_previous_estimate(self):
        address='0x'+'2'*40
        old={'tokens':[{'chain_id':8453,'address':address,'usd':100,'quality':'estimated'}]}
        for quality in ('unfunded','unreliable'):
            with self.subTest(quality=quality):
                rpc={'chain_id':8453,'address':address,'usd':None,'basis':'Curve spot','quality':quality}
                market,_,_,error=self.run_price_job(self.fresh_rows(),previous=old,rpc_tokens=[rpc])
                self.assertIsNone(error)
                self.assertIsNone(market['tokens'][0]['usd'])
                self.assertEqual(market['retained_price_records'],0)


    def test_actual_zero_reserve_rpc_shape_invalidates_old_curve_price(self):
        address='0x'+'2'*40
        token={'chain_id':8453,'token_address':address,'dex_pools':[],
               'mintclub':{'reserve_token':'0x4200000000000000000000000000000000000006','reserve_symbol':'WETH'}}
        old={'tokens':[{'chain_id':8453,'address':address,'usd':100,'quality':'estimated','basis':'Curve spot'}]}
        rpc={'chain_id':8453,'address':address,'basis':'Curve spot','curve_reserve':'0',
             'curve_price_in_reserve':'0.2','reserve_symbol':'WETH','block_number':'123','observed_at':'2026-10-04T12:00:00Z'}
        dex=[{'chainId':'base','baseToken':{'address':address},'quoteToken':{'address':'0x'+'3'*40},
              'priceUsd':'3','liquidity':{'usd':1000,'base':100},'url':'https://dexscreener.com/base/fixture'}]
        for pairs in ([],dex):
            with self.subTest(dex_available=bool(pairs)):
                market,_,_,error=self.run_price_job(self.fresh_rows(),previous=old,tokens=[token],rpc_tokens=[rpc],dex=pairs)
                self.assertIsNone(error)
                price=next(p for p in market['tokens'] if p['address']==address)
                self.assertEqual(market['retained_price_records'],0)
                if pairs:self.assertEqual(price['usd'],3);self.assertEqual(price['basis'],'DEX market')
                else:self.assertIsNone(price['usd']);self.assertEqual(price['quality'],'unfunded')



if __name__=='__main__':unittest.main()
