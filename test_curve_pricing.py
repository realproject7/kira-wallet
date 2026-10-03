"""External reserve, network identity and cycle regressions."""
import unittest
from curve_pricing import resolve


class CurvePricingTests(unittest.TestCase):
    def curve(self,address,parent,chain=8453,price='0.5',funded=True):
        return {'chain_id':chain,'address':address,'is_curve':True,'reserve_token':parent,'reserve_symbol':'Reserve',
                'price_in_reserve':price,'curve_reserve':'100','funded':funded,'source':'https://mint.club/token/base/'+address,
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

    def test_supported_market_price_is_kept_and_unfunded_curve_is_unknown(self):
        graph=[self.curve('market','reserve'),self.curve('empty','reserve',funded=False)]
        prices=[{'chain_id':8453,'address':'market','usd':3,'basis':'DEX market','quality':'estimated'},
                {'chain_id':8453,'address':'reserve','usd':2,'basis':'Market index','quality':'estimated'}]
        result={r['address']:r for r in resolve(graph,prices)}
        self.assertEqual(result['market']['usd'],3)
        self.assertNotIn('empty',result)


if __name__=='__main__':unittest.main()
