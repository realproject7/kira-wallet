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

    def test_pagination_deduplicates_and_rejects_other_network_or_wallet(self):
        foreign=self.token();foreign['address']='0x0000000000000000000000000000000000000002'
        responses=[{'data':{'tokens':[self.token(),self.token(network='eth-mainnet'),foreign],'pageKey':'next'}},
                   {'data':{'tokens':[self.token(),self.token('0x0000000000000000000000000000000000000003')],'pageKey':None}}]
        with patch.object(wallet,'fetch',side_effect=responses) as fetch:
            result=wallet.discover(self.address,self.network,self.folder)
        self.assertTrue(result['complete']);self.assertEqual(len(result['tokens']),2)
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


if __name__=='__main__':unittest.main()
