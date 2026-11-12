"""Recognized identities may use market references without inventing quotes."""
from copy import deepcopy
import unittest
from sell_summary import spot_sell_reference, summarize_sell_out
from kira_state import filter_assets


class ReferenceTests(unittest.TestCase):
    def native(self):
        return {'id':'1:native','environment':'mainnet','chain_id':1,'is_native':True,'symbol':'ETH','address':None,'value_usd':123,
                'price':{'usd':1230,'quality':'estimated','basis':'Market index','source':'https://example.com/native','observed_at':'2026-11-11T00:00:00Z'}}

    def test_native_reference_is_explicit_and_not_an_execution_quote(self):
        asset=self.native();ref=spot_sell_reference(asset)
        self.assertEqual(ref['value_usd'],123);self.assertFalse(ref['execution_verified'])
        asset['sell_out_reference']=ref;summary=summarize_sell_out([asset])
        self.assertEqual((summary['quoted_count'],summary['reference_count'],summary['missing_count']),(0,1,0))
        self.assertEqual(summary['basis'],'independent_quotes_and_market_references')

    def test_stablecoin_uses_the_saved_price_not_a_dollar_peg(self):
        asset=self.native();asset.update(id='1:usdt',is_native=False,symbol='Fake metadata',address='0xdac17f958d2ee523a2206206994597c13d831ec7',value_usd=97)
        self.assertEqual(spot_sell_reference(asset)['value_usd'],97)
        asset.update(address='0x'+'f'*40,symbol='USDT');self.assertIsNone(spot_sell_reference(asset))
        asset.update(address='0xdac17f958d2ee523a2206206994597c13d831ec7',chain_id=8453);self.assertIsNone(spot_sell_reference(asset))

    def test_unsafe_or_retained_observations_stay_missing(self):
        for override in [{'environment':'testnet'},{'archived':True},{'quantity_retained':True},{'chain_id':999},
                         {'address':'0x'+'1'*40},{'symbol':'USDT'},{'value_usd':None}]:
            asset={**self.native(),**override};self.assertIsNone(spot_sell_reference(asset))
        for override in [{'source':None},{'observed_at':None},{'retained_from_previous':True},{'quality':'unreliable'},{'basis':'Curve spot'}]:
            asset=self.native();asset['price'].update(override);self.assertIsNone(spot_sell_reference(asset))

    def test_quote_zero_takes_priority_and_sorting_precedes_pagination(self):
        native=self.native();native['sell_out_reference']=spot_sell_reference(native);native['sell_out']={'value_usd':0}
        result=summarize_sell_out([native]);self.assertEqual((result['value_usd'],result['reference_count']),(0,0))
        rows=[{**self.native(),'id':name,'value_usd':spot,'sell_out_summary':{'value_usd':sale}}
              for name,spot,sale in [('high-spot',1000,2),('missing',500,None),('high-sale',20,100),('zero',10,0)]]
        self.assertEqual([r['id'] for r in filter_assets(rows,sort='sell_out')],['high-sale','high-spot','zero','missing'])
