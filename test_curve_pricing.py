"""External reserve, network identity and cycle regressions."""
import unittest
import json
from pathlib import Path
import tempfile
import time
from unittest.mock import patch
from curve_pricing import resolve


class CurvePricingTests(unittest.TestCase):
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


if __name__=='__main__':unittest.main()
