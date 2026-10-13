"""Cash-out threshold regressions, independent of spot holding valuation."""
from copy import deepcopy
import unittest
from cashout import annotate, classify

TOKEN='0x'+'1'*40
OUTPUT='0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'
HASH='0x'+'a'*64


class CashoutTests(unittest.TestCase):
    def setUp(self):
        self.quote={'status':'quoted','kind':'uniswap_v3_quoter','input_amount_raw':'100',
                    'holding_amount_raw':'100','output_amount':'1','output_address':OUTPUT,
                    'block_number':'7','block_hash':HASH,'observed_at':'2026-10-13T06:00:00Z',
                    'gas_included':False,'route_fees_included':True,'price_impact_included':True,
                    'transfer_tax_included':False}
        self.token={'chain_id':8453,'token_address':TOKEN,'wallet_balance_raw':'100',
                    'balance_block_number':'7','balance_block_hash':HASH,'wallet_balance':'100',
                    'dex_pools':[{'cashout_quote':self.quote}]}
        self.market={'tokens':[{'chain_id':8453,'address':OUTPUT,'usd':'1','quality':'estimated',
                              'basis':'DEX market','source':'https://example.com/price','observed_at':'2026-10-13T06:00:00Z'}]}

    def test_exact_threshold_is_inclusive_and_rounding_never_promotes_dust(self):
        result=classify(self.token,self.market)
        self.assertEqual(result['status'],'quoted_at_least_1_usd')
        self.assertFalse(result['execution_verified']);self.assertFalse(result['gas_included'])
        self.quote['output_amount']='0.999999999999999999999999999999999999999999'
        result=classify(self.token,self.market)
        self.assertEqual(result['status'],'recorded_quotes_below_1_usd');self.assertFalse(result['excluded'])

    def test_partial_input_can_qualify_but_spot_wallet_value_cannot(self):
        self.quote['input_amount_raw']='50'
        result=classify(self.token,self.market)
        self.assertTrue(result['quotes'][0]['partial_input']);self.assertEqual(result['status'],'quoted_at_least_1_usd')
        self.token['dex_pools']=[];self.token['indexer_price_references']=[{'currency':'usd','value':'1000000'}]
        self.market['tokens'].append({**self.market['tokens'][0],'address':TOKEN,'usd':'1000000'})
        result=classify(self.token,self.market)
        self.assertEqual(result['status'],'unknown');self.assertFalse(result['excluded'])

    def test_failure_or_unsupported_route_never_becomes_unpriced_or_zero(self):
        self.token['dex_pools']=[{'cashout_quote':{'status':'unknown','reason':'RPC failure'}}]
        result=classify(self.token,self.market)
        self.assertEqual(result['status'],'unknown');self.assertEqual(result['quotes'],[]);self.assertFalse(result['excluded'])

    def test_pin_holding_and_fee_mismatches_remain_unknown(self):
        for field,value in [('block_hash','0x'+'b'*64),('block_number','8'),('input_amount_raw','101'),
                            ('holding_amount_raw','101'),('gas_included',None),('route_fees_included',False),
                            ('price_impact_included',False),('output_amount','NaN')]:
            token=deepcopy(self.token);token['dex_pools'][0]['cashout_quote'][field]=value
            with self.subTest(field=field):
                result=classify(token,self.market);self.assertEqual(result['status'],'unknown');self.assertFalse(result['excluded'])

    def test_usd_output_identity_and_market_observation_are_required(self):
        for field,value in [('chain_id',1),('address',TOKEN),('quality','unreliable'),('basis','Curve spot'),
                            ('retained_from_previous',True),('observed_at',None)]:
            market=deepcopy(self.market);market['tokens'][0][field]=value
            with self.subTest(field=field):self.assertEqual(classify(self.token,market)['status'],'unknown')

    def test_priced_nonterminal_reserve_still_needs_its_own_liquidation_leg(self):
        output='0x'+'2'*40
        self.quote['output_address']=output
        self.market['tokens'][0]['address']=output
        self.assertEqual(classify(self.token,self.market)['status'],'unknown')

    def test_funded_mintclub_without_dex_qualifies_on_refund_not_next_mint_spot(self):
        self.token['dex_pools']=[]
        self.token['mintclub']={'wallet_full_burn':{'net_refund':'1','gas_included':False},
                               'reserve_token':OUTPUT,'reserve_balance':'5','funded':True,
                               'block_number':'7','block_hash':HASH,'observed_at':'2026-10-13T06:00:00Z',
                               'price_for_next_mint_in_reserve_token':'1000000'}
        self.assertEqual(classify(self.token,self.market)['status'],'quoted_at_least_1_usd')
        self.token['mintclub']['wallet_full_burn']['net_refund']='0.5'
        self.assertEqual(classify(self.token,self.market)['status'],'recorded_quotes_below_1_usd')
        self.token['mintclub']['wallet_full_burn']['net_refund']='6'
        self.assertEqual(classify(self.token,self.market)['status'],'unknown')
        self.token['mintclub']['wallet_full_burn']['net_refund']='1';self.token['mintclub']['wallet_full_burn_error']={'message':'failed'}
        self.assertEqual(classify(self.token,self.market)['status'],'unknown')

    def test_testnets_and_missing_coverage_cannot_be_classified_as_usd_eligible(self):
        snapshot={'coverage':[{'chain_id':8453,'environment':'testnet'}],'tokens':[self.token]}
        annotate(snapshot,self.market)
        self.assertEqual(snapshot['cashout_counts']['outside_usd_scope'],1)
        snapshot['coverage']=[];annotate(snapshot,self.market)
        self.assertEqual(self.token['cashout_eligibility']['status'],'outside_usd_scope')


if __name__=='__main__':unittest.main()
