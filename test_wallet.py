"""Failure, pagination and identity checks for the reusable wallet pipeline."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wallet


class WalletPipelineTests(unittest.TestCase):
    address='0x0000000000000000000000000000000000000011'
    network={'chain_id':8453,'environment':'mainnet'}

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.folder=Path(self.temp.name)
        self.secret=patch.object(wallet.h,'secrets',return_value={'ALCHEMY_CUSTOM_APY_KEY':'fixture-key'})
        self.secret.start()
        self.config=patch.object(wallet,'load_config',return_value={'discovery':{'provider':'alchemy','explorers':True}})
        self.config.start()

    def tearDown(self):
        self.secret.stop()
        self.config.stop()
        self.temp.cleanup()

    def token(self,address='0x0000000000000000000000000000000000000001',network='base-mainnet'):
        return {'address':self.address,'network':network,'tokenAddress':address,'tokenBalance':'0x1',
                'tokenMetadata':{'decimals':18,'symbol':'Fixture','name':'Fixture'},'tokenPrices':[]}

    def test_partial_200_preserves_candidates_without_claiming_complete(self):
        data={'data':{'tokens':[self.token()]},'error':{'partialErrors':[{'network':'base-mainnet','message':'timeout'}]}}
        with patch.object(wallet,'fetch',return_value=data):
            result=wallet.discover(self.address,self.network,self.folder)
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['tokens']),1)
        self.assertIn('partialErrors',result['error'])
        self.assertEqual(result['discovery_status'],'provider_error')

    def test_disabled_and_missing_credentials_record_the_actual_reason(self):
        for provider,secrets,expected in [('none',{},'disabled'),('alchemy',{},'missing_credential')]:
            with patch.object(wallet,'load_config',return_value={'discovery':{'provider':provider,'explorers':False}}),patch.object(wallet.h,'secrets',return_value=secrets),patch.object(wallet,'fetch') as fetch:
                result=wallet.discover(self.address,self.network,self.folder)
            fetch.assert_not_called();self.assertFalse(result['complete'])
            self.assertEqual(result['discovery_status'],expected)
        with patch.object(wallet.h,'secrets',side_effect=ValueError('Unreadable secret file')),patch.object(wallet,'fetch') as fetch:
            result=wallet.discover(self.address,self.network,self.folder)
        fetch.assert_not_called();self.assertEqual(result['discovery_status'],'missing_credential')

    def test_pagination_deduplicates_and_rejects_other_network_or_wallet(self):
        foreign=self.token();foreign['address']='0x0000000000000000000000000000000000000002'
        responses=[{'data':{'tokens':[self.token(),self.token(network='eth-mainnet'),foreign],'pageKey':'next'}},
                   {'data':{'tokens':[self.token(),self.token('0x0000000000000000000000000000000000000003')],'pageKey':None}}]
        with patch.object(wallet,'fetch',side_effect=responses) as fetch:
            result=wallet.discover(self.address,self.network,self.folder)
        self.assertTrue(result['complete']);self.assertEqual(len(result['tokens']),2)
        self.assertEqual(result['discovery_status'],'checked')
        self.assertEqual(fetch.call_args_list[1].args[1]['pageKey'],'next')
        persisted=json.loads((self.folder/'discovery-8453.json').read_text())
        self.assertNotIn('fixture-key',json.dumps(persisted))
        self.assertIsNone(persisted['pages'][0]['request'].get('pageKey'))

    def test_repeated_cursor_and_transport_failure_are_incomplete(self):
        with patch.object(wallet,'fetch',return_value={'data':{'tokens':[],'pageKey':'same'}}):
            result=wallet.discover(self.address,self.network,self.folder)
        self.assertFalse(result['complete']);self.assertIn('Repeated',result['error']['message'])
        with patch.object(wallet,'fetch',return_value={'transport_error':{'status':503,'message':'unavailable'}}):
            result=wallet.discover(self.address,self.network,self.folder)
        self.assertFalse(result['complete']);self.assertEqual(result['error']['status'],503)

    def test_registration_keeps_identity_tags_and_history(self):
        registry={'wallets':[],'tag_history':[]}
        wallet.register(registry,self.address,'Demo main')
        wallet.register(registry,self.address.lower(),'Secondary tag')
        wallet.register(registry,self.address,'Demo main')
        self.assertEqual(len(registry['wallets']),1)
        self.assertEqual(registry['wallets'][0]['address'],self.address)
        self.assertEqual(registry['wallets'][0]['tags'],['Demo main','Secondary tag'])
        self.assertEqual(len(registry['tag_history']),2)

    def test_supported_scope_changes_stop_before_analysis(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return b"  BOND: {\n    [base.id]: '0x0000000000000000000000000000000000000000',\n  },"
        with patch('urllib.request.urlopen',return_value=Response()):
            with self.assertRaisesRegex(ValueError,'scope changed'):
                wallet.source_check([{'chain_id':8453,'mintclub_bond_address':'0xc5a076cad94176c2996B32d8466Be1cE757FAa27'}],self.folder)

    def test_outside_dex_scope_reserve_preserves_unknown_observation(self):
        token={'chain_id':54176,'token_address':'0x'+'3'*40,'token_type':'ERC20'}
        with patch.object(wallet,'fetch') as fetch:
            row=wallet.dex_fetch(token,self.folder)
        fetch.assert_not_called();self.assertEqual(row['response'],[]);self.assertIsNone(row['observed_at'])
        import sys
        sys.path.insert(0,str(wallet.ASSETS/'viewer'))
        from model import dex_price
        self.assertIsNone(dex_price({**token,'dex_pools':[],'indexer_price_references':[]},row.get('observed_at')))

    def test_public_analysis_has_independent_native_price_and_image_evidence(self):
        import sys
        sys.path.insert(0,str(wallet.ASSETS/'viewer'))
        wallet.atomic(self.folder/'onchain-summary.json',{'chains':[{'chain_id':8453,'tokens':[],
            'native_balance':'1','observed_at':'2026-10-04T12:00:00Z','rpc_status':'available','registry_scan':{'complete':True,'checked':0,'registry_count':0}}]})
        metadata={'prices':{'ETH_USD':{'value':2000,'observed_at':'2026-10-04T12:00:00Z','source':'https://api.coingecko.com','asset_id':'ethereum'}},
            'images':{'ethereum':{'image_url':'https://coin-images.coingecko.com/eth.png'}},'evidence':{'source':'https://api.coingecko.com','response':[]}}
        def node(command,input_path,output_path):wallet.atomic(output_path,{'tokens':[]})
        with patch.object(wallet,'run_node',side_effect=node),patch.object(wallet,'event'),\
             patch('native_assets.market_metadata',return_value=metadata) as native,\
             patch('curve_pricing.enrich',side_effect=lambda snapshot,market,folder:market),\
             patch('token_images.refresh_catalog',return_value={}) as images:
            result=wallet.finish({'address':self.address,'tags':['Fixture']},self.folder,[{**self.network,'name':'Base','mintclub_network':'base'}],
                [{'chain_id':8453,'complete':False,'source':None,'pages':[],'native':[]}])
        self.assertEqual(result['price_references']['ETH_USD']['value'],2000)
        self.assertEqual(json.loads((self.folder/'market-prices.json').read_text())['native_usd']['ETH']['asset_id'],'ethereum')
        self.assertEqual(images.call_args.kwargs['native_images'],metadata['images'])
        self.assertTrue((self.folder/'native-market.json').is_file())
        native.assert_called_once()
        with patch.object(wallet,'run_node',side_effect=node),patch.object(wallet,'event'),\
             patch('native_assets.market_metadata',return_value=metadata),\
             patch('curve_pricing.enrich',side_effect=lambda snapshot,market,folder:market),\
             patch('token_images.refresh_catalog',return_value={}):
            result=wallet.finish({'address':self.address,'tags':['Fixture']},self.folder,[{**self.network,'name':'Base','mintclub_network':'base'}],
                [{'chain_id':8453,'complete':True,'source':None,'pages':[],'native':[
                    {'tokenPrices':[{'currency':'usd','value':'2100','lastUpdatedAt':'2026-10-04T12:00:00Z'}]}]}])
        self.assertEqual(result['price_references']['ETH_USD']['value'],'2100')
        self.assertEqual(result['price_references']['ETH_USD']['source'],'Alchemy Portfolio Tokens By Wallet')

    def test_candidate_balance_errors_keep_successful_discovery_partial(self):
        wallet.atomic(self.folder/'onchain-summary.json',{'chains':[{'chain_id':8453,'tokens':[],
            'native_balance':'0','observed_at':'2026-10-04T12:00:00Z','rpc_status':'available',
            'registry_scan':{'complete':True,'checked':0,'registry_count':0},
            'balance_errors':[{'error':{'message':'PRIVATE-DIAGNOSTIC'}}]}]})
        def node(command,input_path,output_path):wallet.atomic(output_path,{'tokens':[]})
        with patch.object(wallet,'run_node',side_effect=node),patch.object(wallet,'event'),\
             patch('native_assets.market_metadata',return_value={'prices':{},'images':{},'evidence':None}),\
             patch('curve_pricing.enrich',side_effect=lambda snapshot,market,folder:market),\
             patch('token_images.refresh_catalog',return_value={}):
            result=wallet.finish({'address':self.address,'tags':['Fixture']},self.folder,
                [{**self.network,'name':'Base','mintclub_network':'base'}],
                [{'chain_id':8453,'complete':True,'source':None,'pages':[],'native':[]}])
        self.assertEqual(result['coverage'][0]['candidate_balance_errors'],1)
        self.assertEqual(result['status'],'completed_with_coverage_gaps')
        self.assertNotIn('PRIVATE-DIAGNOSTIC',json.dumps(result))


if __name__=='__main__':unittest.main()
