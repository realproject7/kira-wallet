"""Financial aggregation and coverage semantics for the cross-wallet views."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from details import project_details, total_balance, coverage_status


class DetailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.chains = [{'id':8453,'name':'Base','environment':'mainnet','complete':True,'rpc_available':True},
                       {'id':1,'name':'Ethereum','environment':'mainnet','complete':False,'rpc_available':False},
                       {'id':84532,'name':'Base Sepolia','environment':'testnet','complete':True,'rpc_available':True}]

    def tearDown(self): self.temp.cleanup()

    def test_pending_research_is_not_an_rpc_outage(self):
        wallet={'analysed_at':'2026-10-09T00:00:00Z'}
        self.assertEqual(coverage_status(wallet,{'rpc_available':False,'rpc_pending':True}),'Research pending')
        self.assertEqual(coverage_status(wallet,{'rpc_available':False,'rpc_status':'pending'}),'Research pending')
        self.assertEqual(coverage_status(wallet,{'rpc_available':False,'rpc_status':'unavailable'}),'RPC unavailable')

    def test_failed_or_deferred_reads_cannot_make_an_empty_network_a_verified_zero(self):
        import json,subprocess
        for fields,expected in (({'candidate_balance_errors':2},'Incomplete on-chain checks'),
                                ({'registry_complete':False,'registry_errors':1},'Incomplete on-chain checks'),
                                ({'registry_complete':False,'registry_phase':'deferred'},'Research pending')):
            wallet=self.wallet('first',[]);wallet['chains'][0].update(fields)
            network=next(c for c in project_details([wallet],self.root)['networks'] if c['id']==8453)
            self.assertEqual(network['wallets'][0]['coverage'],expected)
            self.assertIsNone(network['wallets'][0]['value_usd']);self.assertIsNone(network['value_usd'])
            script="const ui=require('./viewer/static/workspace-model.js');const n=JSON.parse(require('fs').readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(ui.networkEmpty(n,0)));"
            empty=json.loads(subprocess.check_output(['node','-e',script],input=json.dumps(network).encode(),cwd=Path(__file__).resolve().parents[1]))
            self.assertTrue(empty['activity'])
            self.assertNotIn('completed checks found no positive holdings',empty['message'])

    def asset(self, chain=8453, balance='1', value=5, environment='mainnet'):
        address = '0x' + '1' * 40
        return {'id':f'{chain}:{address}','chain_id':chain,'address':address,
                'symbol':'SAME','name':'Same symbol','image_url':None,'is_native':False,
                'environment':environment,'balance':balance,'value_usd':value,
                'price':{'usd':5,'observed_at':'2026-10-03T01:00:00Z'},'links':[],
                'curve_reserve':{'amount':'1000000','symbol':'USDC'}}

    def wallet(self, key, assets):
        return {'key':key,'name':key,'address':'0x'+'2'*40,'tags':[key],
                'analysed_at':'2026-10-03T01:00:00Z','prices_at':'2026-10-03T01:00:00Z',
                'chains':deepcopy(self.chains),'assets':assets}

    def test_shared_token_sums_balances_and_values_without_shared_backing(self):
        first=self.wallet('first',[self.asset(balance='1.000000000000000001')])
        second=self.wallet('second',[self.asset(balance='2.000000000000000002',value=7)])
        # A wallet-wide refresh on a different chain must not date this network.
        first['prices_at']='2026-10-03T09:00:00Z'
        details=project_details([first,second],self.root)
        token=details['tokens'][0];network=next(c for c in details['networks'] if c['id']==8453)
        self.assertEqual(token['balance'],'3.000000000000000003')
        self.assertEqual(token['value_usd'],12)
        self.assertEqual(token['wallet_count'],2)
        self.assertEqual(network['value_usd'],12)
        self.assertEqual(network['unique_asset_count'],1)
        self.assertEqual(network['position_count'],2)
        self.assertEqual(network['price_times'],{'from':'2026-10-03T01:00:00Z','to':'2026-10-03T01:00:00Z'})
        self.assertEqual(len(token['wallets']),2)

    def test_same_contract_on_another_chain_is_a_separate_token(self):
        wallet=self.wallet('first',[self.asset(),self.asset(chain=1,value=None)])
        details=project_details([wallet],self.root)
        self.assertEqual(len(details['tokens']),2)
        ethereum=next(c for c in details['networks'] if c['id']==1)
        self.assertIsNone(ethereum['value_usd'])
        self.assertEqual(ethereum['wallets'][0]['coverage'],'RPC unavailable')

    def test_missing_and_awaiting_wallets_are_not_zero_token_balances(self):
        first=self.wallet('first',[self.asset(chain=1,value=None)])
        second=self.wallet('second',[])
        third=self.wallet('third',[]);third['analysed_at']=None;third['chains']=[]
        details=project_details([first,second,third],self.root)
        rows=details['tokens'][0]['wallets']
        self.assertIsNone(rows[1]['asset']);self.assertEqual(rows[1]['status'],'Unknown')
        self.assertIsNone(rows[2]['asset']);self.assertEqual(rows[2]['coverage'],'Awaiting analysis')
        network=next(c for c in details['networks'] if c['id']==1)
        self.assertIsNone(network['value_usd'])
        self.assertIsNone(network['wallets'][1]['value_usd'])
        empty=next(c for c in details['networks'] if c['id']==8453)
        self.assertEqual(empty['price_times'],{'from':None,'to':None})

    def test_testnet_value_is_excluded_even_if_a_fixture_has_a_price(self):
        wallet=self.wallet('first',[self.asset(),self.asset(chain=84532,value=1000000,environment='testnet')])
        details=project_details([wallet],self.root)
        testnet=next(c for c in details['networks'] if c['id']==84532)
        token=next(t for t in details['tokens'] if t['chain_id']==84532)
        self.assertIsNone(testnet['value_usd']);self.assertIsNone(token['value_usd'])
        self.assertEqual(token['balance'],'1')

    def test_total_balance_keeps_large_and_tiny_quantities(self):
        large='1234567890123456789012345678901234567890.123456789012345678'
        tiny='0.000000000000000001'
        result=total_balance([{'balance':large},{'balance':tiny}])
        self.assertEqual(result,'1234567890123456789012345678901234567890.123456789012345679')
        self.assertIsNone(total_balance([{'balance':'NaN'}]))


if __name__=='__main__': unittest.main()
