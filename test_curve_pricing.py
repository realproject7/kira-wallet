"""External reserve, network identity and cycle regressions."""
import unittest
import json
from pathlib import Path
import tempfile
import time
from unittest.mock import patch
from curve_pricing import resolve


class CurvePricingTests(unittest.TestCase):
    def test_index_prices_validate_exact_identity_and_bound_batches(self):
        from curve_pricing import index_prices
        identities=[(8453,'0x'+format(i+1,'040x')) for i in range(26)]
        def fetch(url,body,**kwargs):
            self.assertLessEqual(len(body['addresses']),25)
            valid=[{**row,'prices':[{'currency':'usd','value':'2','lastUpdatedAt':'2026-10-25T01:00:00Z'}]} for row in body['addresses']]
            return {'data':[None,{'network':[],'address':identities[0][1]},
                {'network':'eth-mainnet','address':identities[0][1],'prices':[{'currency':'usd','value':'999'}]},*valid]}
        with tempfile.TemporaryDirectory() as directory,patch('research.secrets',return_value={'ALCHEMY_CUSTOM_APY_KEY':'synthetic-key'}),patch('wallet.fetch',side_effect=fetch) as provider:
            result=index_prices(identities,Path(directory))
            self.assertEqual(provider.call_count,2);self.assertEqual(result['status'],'checked')
            self.assertEqual(len(result['tokens']),26)
            self.assertTrue(all(p['chain_id']==8453 and p['usd']==2 and p['observed_at']=='2026-10-25T01:00:00Z' for p in result['tokens']))
            self.assertEqual(index_prices(identities,Path(directory)),result)
            self.assertEqual(provider.call_count,2)

    def test_index_provider_failure_and_invalid_values_remain_unknown(self):
        from curve_pricing import index_prices
        address='0x'+'1'*40
        for response in ([],{'transport_error':{'status':429}},{'data':[{'network':'base-mainnet','address':address,
            'prices':[{'currency':'usd','value':v} for v in ('NaN','Infinity','-1','invalid',True)]}]}):
            with self.subTest(response=response),tempfile.TemporaryDirectory() as directory,patch('research.secrets',return_value={'ALCHEMY_CUSTOM_APY_KEY':'synthetic-key'}),patch('wallet.fetch',return_value=response):
                self.assertEqual(index_prices([(8453,address)],Path(directory)),{'tokens':[],'status':'partial'})

    def test_reserve_enrichment_preserves_dex_prices_and_explicit_rejections(self):
        from curve_pricing import enrich
        address='0x'+'1'*40
        for price in ({'usd':2,'basis':'DEX market','quality':'estimated'},
                      {'usd':None,'basis':'Insufficient market liquidity','quality':'unreliable'}):
            with self.subTest(price=price),tempfile.TemporaryDirectory() as directory:
                folder=Path(directory)
                (folder/'reserve-graph.json').write_text(json.dumps({'tokens':[{'chain_id':8453,'address':address,'is_curve':False}]}))
                row={'chain_id':8453,'address':address,**price}
                with patch('wallet.run_node'),patch('curve_pricing.index_prices',return_value={'tokens':[],'status':'checked'}) as index,patch('wallet.dex_fetch',side_effect=AssertionError('Already checked')):
                    result=enrich({'wallet_address':'0x'+'2'*40,'tokens':[]},{'tokens':[row]},folder)
                self.assertEqual(index.call_args.args[0],[])
                self.assertEqual(result['tokens'],[row])

    def test_retained_reserve_does_not_acquire_a_fresh_curve_timestamp(self):
        graph=[self.curve('child','reserve')]
        parent={'chain_id':8453,'address':'reserve','usd':2,'basis':'Market index','quality':'estimated',
                'observed_at':'2026-10-01T00:00:00Z','retained_from_previous':True}
        child=next(p for p in resolve(graph,[parent]) if p['address']=='child')
        self.assertEqual(child['usd'],1);self.assertTrue(child['retained_from_previous'])
        self.assertEqual(child['observed_at'],parent['observed_at'])

    def test_bounded_reserve_engine_publishes_before_parent_termination(self):
        import curve_pricing
        import wallet
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            # Emulate a bounded helper plus startup/serialization overhead.
            (folder/'pipeline-onchain.cjs').write_text("const fs=require('fs');const input=JSON.parse(fs.readFileSync(process.argv[3]));setTimeout(()=>fs.writeFileSync(process.argv[4],JSON.stringify({tokens:[],market_pending:true})),input.market_budget_ms+250);")
            with patch.object(wallet,'ASSETS',folder),patch.object(wallet.h,'secrets',return_value={}):
                with self.assertRaises(wallet.MarketPause):
                    curve_pricing.enrich({'wallet_address':'0x'+'1'*40,'tokens':[]},{'tokens':[]},folder,deadline=time.monotonic()+2)
            self.assertTrue((folder/'reserve-graph.json').exists())
            self.assertTrue(json.loads((folder/'reserve-graph.json').read_text())['market_pending'])

    def curve(self,address,parent,chain=8453,price='0.5',funded=True):
        return {'chain_id':chain,'address':address,'is_curve':True,'reserve_token':parent,'reserve_symbol':'Reserve',
                'price_in_reserve':price,'curve_reserve':'100' if funded else '0','funded':funded,'source':'https://mint.club/token/base/'+address,
                'observed_at':'2026-10-03T06:00:00Z','block_number':'123'}

    def test_external_reserve_curve_is_priced_without_wallet_holding(self):
        graph=[self.curve('child','parent'),self.curve('parent','weth',price='0.01'),{'chain_id':8453,'address':'weth','is_curve':False}]
        prices=[{'chain_id':8453,'address':'weth','usd':2000,'basis':'Market index','quality':'estimated'}]
        result={r['address']:r for r in resolve(graph,prices)}
        self.assertEqual(result['child']['usd'],10)
        self.assertEqual(result['child']['price_path'],['child','parent','weth'])

    def test_wrong_network_price_and_cycles_remain_unknown(self):
        graph=[self.curve('a','b'),self.curve('b','a')]
        self.assertEqual(resolve(graph,[]),[])
        graph=[self.curve('child','reserve')]
        self.assertEqual(resolve(graph,[{'chain_id':1,'address':'reserve','usd':100}]),[])

    def test_rejected_reserve_price_cannot_survive_through_a_cached_curve(self):
        graph=[self.curve('child','parent'),self.curve('parent','bad'),{'chain_id':8453,'address':'bad','is_curve':False}]
        prices=[{'chain_id':8453,'address':'bad','usd':None,'quality':'unreliable'},
                {'chain_id':8453,'address':'parent','usd':1000000,'basis':'Curve spot','quality':'estimated'}]
        result={r['address']:r for r in resolve(graph,prices)}
        self.assertIsNone(result['child']['usd']);self.assertEqual(result['child']['quality'],'unreliable')
        self.assertIsNone(result['parent']['usd'])
        independent={'chain_id':8453,'address':'child','usd':2,'basis':'DEX market','quality':'estimated'}
        self.assertEqual(next(r for r in resolve(graph,prices+[independent]) if r['address']=='child')['usd'],2)

    def test_supported_market_price_is_kept_and_unfunded_curve_is_unknown(self):
        graph=[self.curve('market','reserve'),self.curve('empty','reserve',funded=False)]
        prices=[{'chain_id':8453,'address':'market','usd':3,'basis':'DEX market','quality':'estimated'},
                {'chain_id':8453,'address':'reserve','usd':2,'basis':'Market index','quality':'estimated'}]
        result={r['address']:r for r in resolve(graph,prices)}
        self.assertEqual(result['market']['usd'],3)
        self.assertIsNone(result['empty']['usd'])
        self.assertEqual(result['empty']['quality'],'unfunded')

    def test_unfunded_ancestor_invalidates_cached_descendants_but_not_dex_prices(self):
        graph=[self.curve('leaf','child'),self.curve('child','parent'),
               self.curve('parent','weth',funded=False),
               {'chain_id':8453,'address':'weth','is_curve':False}]
        prices=[{'chain_id':8453,'address':address,'usd':100,'basis':'Curve spot','quality':'estimated'}
                for address in ('leaf','child')]
        prices.append({'chain_id':8453,'address':'weth','usd':2000,'basis':'Market index','quality':'estimated'})
        result={r['address']:r for r in resolve(graph,prices)}
        for address in ('leaf','child','parent'):
            self.assertIsNone(result[address]['usd'])
            self.assertEqual(result[address]['quality'],'unfunded')
        for address in ('child','parent'):
            independent={'chain_id':8453,'address':address,'usd':2,'basis':'DEX market','quality':'estimated'}
            result={r['address']:r for r in resolve(graph,prices+[independent])}
            self.assertEqual(result[address]['usd'],2)
            self.assertIsNotNone(result['leaf']['usd'])

    def test_fresh_unfunded_graph_invalidates_curve_quote_but_keeps_dex_quote(self):
        graph=[self.curve('asset','reserve',funded=False)]
        for basis in ('Curve spot','DEX market'):
            with self.subTest(basis=basis):
                result=resolve(graph,[{'chain_id':8453,'address':'asset','usd':100,'basis':basis,'quality':'estimated'}])[0]
                if basis=='DEX market':self.assertEqual(result['usd'],100)
                else:
                    self.assertIsNone(result['usd']);self.assertEqual(result['quality'],'unfunded')
                    self.assertEqual(result['observed_at'],graph[0]['observed_at'])

    def test_saved_unfunded_ancestor_invalidates_partial_graph_and_retained_prices(self):
        from wallet import retain_price_evidence
        graph=[self.curve('leaf','child'),self.curve('child','parent')]
        prices=[{'chain_id':8453,'address':address,'usd':100,'basis':'Curve spot','quality':'estimated',
                 'observed_at':'2026-10-02T00:00:00Z'} for address in ('leaf','child')]
        invalid={'chain_id':8453,'address':'parent','usd':None,'basis':'Curve spot','quality':'unfunded'}
        for ancestor in ([],[{'chain_id':8453,'address':'parent','error':'unavailable'}]):
            with self.subTest(ancestor=ancestor):
                resolved=resolve(graph+ancestor,prices+[invalid])
                retained=retain_price_evidence({'tokens':resolved},{'tokens':prices})
                result={r['address']:r for r in retained['tokens']}
                for address in ('leaf','child'):
                    self.assertIsNone(result[address]['usd'])
                    self.assertEqual(result[address]['quality'],'unfunded')
                independent={**prices[1],'basis':'DEX market','usd':2}
                result={r['address']:r for r in resolve(graph+ancestor,prices+[invalid,independent])}
                self.assertEqual(result['child']['usd'],2)
                self.assertIsNotNone(result['leaf']['usd'])


if __name__=='__main__':unittest.main()
