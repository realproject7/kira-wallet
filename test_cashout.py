"""Cash-out threshold regressions, independent of spot holding valuation."""
from copy import deepcopy
import unittest
from cashout import annotate, classify

TOKEN='0x'+'1'*40
OUTPUT='0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'
HASH='0x'+'a'*64


class CashoutTests(unittest.TestCase):
    def test_historical_v3_quotes_require_consumption_evidence_for_full_sellout(self):
        for evidence in (None,True,False):
            with self.subTest(evidence=evidence):
                self.quote.pop('input_amount_is_maximum',None)
                if evidence is not None:self.quote['input_amount_is_maximum']=evidence
                result=classify(self.token,self.market)
                self.assertEqual(result['status'],'quoted_at_least_1_usd')
                self.assertEqual(result['quotes'][0]['partial_input'],evidence is not False)

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
                              'basis':'DEX market','liquidity_usd':1000,'source':'https://example.com/price','observed_at':'2026-10-13T06:00:00Z'}]}

    def test_output_price_uses_the_same_liquidity_floor_as_portfolio_values(self):
        from market_records import checked_price
        for liquidity in (None, 0.02, 999, 1000):
            with self.subTest(liquidity=liquidity):
                row=self.market['tokens'][0];row['liquidity_usd']=liquidity
                result=classify(self.token,self.market)
                self.assertEqual(bool(result['quotes']),checked_price(row)['usd'] is not None)
                self.assertEqual(result['status'],'quoted_at_least_1_usd' if liquidity==1000 else 'unknown')
        self.market['tokens'][0].update(basis='Market index',liquidity_usd=None)
        self.assertEqual(classify(self.token,self.market)['status'],'quoted_at_least_1_usd')

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

    def test_nested_cashout_requires_every_amount_pin_fee_and_funded_leg(self):
        reserve='0x'+'2'*40
        def leg(input,output,amount,out,decimals=0):
            return {'status':'quoted','kind':'mintclub_burn','input_address':input,'input_amount_raw':amount,'holding_amount_raw':'200' if input==reserve else '100',
                    'output_address':output,'output_amount_raw':out,'output_decimals':decimals,
                    'output_amount':'1' if decimals==6 else out,'block_number':'7','block_hash':HASH,
                    'observed_at':'2026-10-13T06:00:00Z','funded':True,'reserve_balance_raw':'9999999',
                    'route_fees_included':True,'price_impact_included':True,'gas_included':False}
        path={**self.quote,'kind':'liquidation_path','output_amount_raw':'1000000','output_decimals':6,
              'legs':[leg(TOKEN,reserve,'100','200'),leg(reserve,OUTPUT,'150','1000000',6)]}
        self.token['dex_pools']=[];self.token['liquidation_routes']=[path]
        result=classify(self.token,self.market)
        self.assertEqual(result['status'],'quoted_at_least_1_usd')
        self.assertTrue(result['quotes'][0]['partial_input'])
        complete=deepcopy(self.token)
        second=complete['liquidation_routes'][0]['legs'][1]
        second.update(input_amount_raw='200',kind='uniswap_v3_quoter',pool='0x'+'3'*40)
        for evidence in (None,True,False):
            second.pop('input_amount_is_maximum',None)
            if evidence is not None:second['input_amount_is_maximum']=evidence
            result=classify(complete,self.market)
            self.assertEqual(result['status'],'quoted_at_least_1_usd')
            self.assertEqual(result['quotes'][0]['partial_input'],evidence is not False)
        for field,value in [('input_amount_raw','201'),('input_address',TOKEN),('funded',False),('block_hash','0x'+'b'*64),
                            ('output_amount','2'),('reserve_balance_raw','999999'),('route_fees_included',False)]:
            token=deepcopy(self.token);token['liquidation_routes'][0]['legs'][1][field]=value
            with self.subTest(field=field):self.assertEqual(classify(token,self.market)['status'],'unknown')
        self.token['liquidation_routes'][0]['output_amount_raw']='999999'
        self.assertEqual(classify(self.token,self.market)['status'],'unknown')


if __name__=='__main__':unittest.main()
